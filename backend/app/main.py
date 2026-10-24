"""Local FastAPI boundary. Run only on 127.0.0.1; credentials never reach the browser."""
from __future__ import annotations
import asyncio
from contextlib import asynccontextmanager
import inspect
import logging
import re
import time
from typing import Literal
import uuid

from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, ConfigDict, ValidationError

from .config import Settings
from .contracts import Battle, ConfirmCapture, CreateBattle, Crop, Observation, SelectCapture, StartBattle, FeedbackSubmission, CorrectionRequest
from .images import ImageError
from .repository import Repository, StoreError, create_repository
from .service import BattleService

logger = logging.getLogger('sketch_clash.api')

class CharacterState(BaseModel):
    model_config = ConfigDict(extra='forbid')
    activity: Literal['wander', 'rest']


def create_app(settings: Settings | None = None, repository: Repository | None = None, recognizer=None) -> FastAPI:
    settings = settings or Settings.load()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.settings = settings
        from .quality_api import OperatorGate
        app.state.operator_gate = OperatorGate()
        app.state.quality = None
        app.state.quality_worker = None
        app.state.island = None
        app.state.island_runtime = None
        app.state.island_planner = None
        app.state.colonies = None
        app.state.colony_runtime = None
        app.state.colony_planner = None
        app.state.observatory = None
        app.state.arena = None
        from .provider_queue import ProviderQueue
        app.state.provider_queue = ProviderQueue(settings.gemini_provider_concurrency, paused=settings.ai_paused)
        app.state.repository = repository
        app.state.store_error = None
        if app.state.repository is None:
            try:
                app.state.repository = await asyncio.to_thread(create_repository, settings)
            except StoreError as exc:
                app.state.store_error = exc
        if recognizer is not None:
            app.state.recognizer = recognizer
        else:
            from .recognition import RecognitionService
            from .catalog import CharacterCatalog
            catalog = CharacterCatalog()
            if app.state.repository is not None and hasattr(app.state.repository, 'db'):
                # Catalogue setup is explicit startup work, never a world read side effect.
                catalog = CharacterCatalog(collection=app.state.repository.db.characterTypes)
                def seed_catalog():
                    for record in catalog.seed_records():
                        catalog.collection.update_one({'canonical_key': record['canonical_key']}, {'$setOnInsert': record}, upsert=True)
                await asyncio.to_thread(seed_catalog)
            app.state.recognizer = RecognitionService(settings, catalog=catalog)
            from .retrieval import AtlasRetriever, RetrievalConfig
            catalog.retriever = AtlasRetriever(collection=catalog.collection, client=app.state.recognizer.client,
                config=RetrievalConfig(model=settings.embedding_model, dimensions=settings.embedding_dimensions, index=settings.vector_index), settings=settings)
        app.state.service = BattleService(settings, app.state.repository, app.state.recognizer) if app.state.repository else None
        if hasattr(app.state.recognizer, 'provider_queue'):
            app.state.recognizer.provider_queue = app.state.provider_queue
        retriever = getattr(getattr(app.state.recognizer, 'catalog', None), 'retriever', None)
        if retriever:
            retriever.provider_queue = app.state.provider_queue
        if app.state.repository:
            try:
                from .arena import ArenaStore
                app.state.arena = ArenaStore(app.state.repository)
                await asyncio.to_thread(app.state.arena.ensure_indexes)
            except Exception as exc:
                logger.warning('arena_startup_unavailable category=%s', type(exc).__name__)
                app.state.arena = None
        if app.state.repository:
            from .observability import Observatory
            app.state.observatory = Observatory(app.state.repository)
            await app.state.observatory.start()
        if app.state.repository:
            try:
                from .quality import QualityStore
                from .quality_jobs import QualityWorker
                app.state.quality = QualityStore(app.state.repository)
                app.state.quality.catalog_settings = settings
                await asyncio.to_thread(app.state.quality.ensure_indexes)
                app.state.quality_worker = QualityWorker(app.state.quality, settings)
                app.state.quality_worker.provider_queue = app.state.provider_queue
                await app.state.quality_worker.start()
                from .quality_references import ApprovedReferences
                app.state.references = ApprovedReferences(app.state.repository, settings)
                app.state.references.provider_queue = app.state.provider_queue
                app.state.service.reference_provider = app.state.references.retrieve
            except Exception as exc:
                logger.warning('quality_startup_unavailable category=%s', type(exc).__name__)
                if app.state.quality_worker is None: app.state.quality = None
                # Optional quality services never break a valid live round.
        if app.state.repository:
            try:
                from .island import IslandStore
                from .island_api import IslandRuntime
                from .island_planner import IslandPlanner
                app.state.island = IslandStore(app.state.repository)
                await asyncio.to_thread(app.state.island.ensure_indexes)
                app.state.island_runtime = IslandRuntime(app.state.island)
                await app.state.island_runtime.start()
                app.state.island_planner = IslandPlanner(app.state.repository, app.state.island, settings)
                app.state.island_planner.provider_queue = app.state.provider_queue
                await asyncio.to_thread(app.state.island_planner.ensure_indexes)
                await app.state.island_planner.start()
            except Exception as exc:
                logger.warning('island_startup_unavailable category=%s', type(exc).__name__)
                if app.state.island_planner:
                    await app.state.island_planner.close()
                    app.state.island_planner = None
                if not app.state.island_runtime or not app.state.island_runtime.task:
                    app.state.island_runtime = None
                    app.state.island = None
        if app.state.repository:
            try:
                from .colonies import ColoniesStore
                from .island_api import IslandRuntime
                from .colony_planner import ColonyPlanner
                app.state.colonies = ColoniesStore(app.state.repository)
                await asyncio.to_thread(app.state.colonies.ensure_indexes)
                app.state.colony_runtime = IslandRuntime(app.state.colonies)
                await app.state.colony_runtime.start()
            except Exception as exc:
                logger.warning('colonies_startup_unavailable category=%s', type(exc).__name__)
                if app.state.colony_runtime:
                    await app.state.colony_runtime.close()
                    app.state.colony_runtime = None
                app.state.colonies = None
        if app.state.colonies:
            try:
                from .retrieval import AtlasRetriever, RetrievalConfig
                memory_embedder = AtlasRetriever(client=getattr(app.state.recognizer, 'client', None),
                    config=RetrievalConfig(model=settings.embedding_model or 'gemini-embedding-2', dimensions=settings.embedding_dimensions), settings=settings)
                memory_embedder.provider_queue = app.state.provider_queue
                app.state.colony_planner = ColonyPlanner(app.state.repository, app.state.colonies, settings,
                                                        legacy_planner=app.state.island_planner, provider_queue=app.state.provider_queue,
                                                        memory_embedder=memory_embedder)
                await asyncio.to_thread(app.state.colony_planner.ensure_indexes)
                await app.state.colony_planner.start()
            except Exception as exc:
                logger.warning('colony_planner_startup_unavailable category=%s', type(exc).__name__)
                if app.state.colony_planner:
                    await app.state.colony_planner.close()
                app.state.colony_planner = None
                # Optional reasoning must not disable persistent local work.
        yield
        if app.state.colony_planner: await app.state.colony_planner.close()
        if app.state.colony_runtime: await app.state.colony_runtime.close()
        if app.state.island_planner: await app.state.island_planner.close()
        if app.state.island_runtime: await app.state.island_runtime.close()
        if app.state.quality_worker:
            await app.state.quality_worker.close()
        if getattr(app.state, 'references', None):
            close_references = getattr(app.state.references, 'close', None)
            if close_references:
                value = close_references()
                if inspect.isawaitable(value): await value
        close_recognizer = getattr(app.state.recognizer, 'close', None)
        if close_recognizer:
            result = close_recognizer()
            if inspect.isawaitable(result):
                await result
        if app.state.repository:
            if app.state.observatory:
                await app.state.observatory.close()
            await asyncio.to_thread(app.state.repository.close)

    app = FastAPI(title='Sketch Clash local API', version='2.0.0', lifespan=lifespan)
    from .observability import instrument_app, register_observatory_routes
    instrument_app(app)
    register_observatory_routes(app)
    from .provider_diagnostics import register_provider_diagnostics
    register_provider_diagnostics(app)
    from .arena import register_arena_routes
    register_arena_routes(app)
    app.add_middleware(CORSMiddleware, allow_origins=[settings.frontend_origin, 'http://localhost:5173'],
                       allow_methods=['GET', 'POST', 'PATCH', 'DELETE'], allow_headers=['Content-Type', 'X-Request-ID'], allow_credentials=True)

    @app.middleware('http')
    async def request_context(request: Request, call_next):
        request_id = request.headers.get('x-request-id', '')
        if not re.fullmatch(r'[A-Za-z0-9_-]{1,100}', request_id):
            request_id = uuid.uuid4().hex
        request.state.request_id = request_id
        origin = request.headers.get('origin')
        allowed_origins = {settings.frontend_origin, 'http://localhost:5173', str(request.base_url).rstrip('/')}
        if origin and origin not in allowed_origins and request.method not in ('GET', 'HEAD', 'OPTIONS'):
            return JSONResponse({'error': {'code': 'origin_not_allowed', 'message': 'Use the local Sketch Clash app for this action.', 'request_id': request_id}}, status_code=403)
        length = request.headers.get('content-length')
        if length and length.isdigit() and int(length) > settings.max_upload_bytes + 65536:
            return JSONResponse({'error': {'code': 'image_too_large', 'message': 'Choose an image smaller than 5 MiB.', 'request_id': request_id}}, status_code=413)
        start = time.monotonic()
        response = await call_next(request)
        response.headers['X-Request-ID'] = request_id
        response.headers['X-Content-Type-Options'] = 'nosniff'
        logger.info('request_id=%s method=%s path=%s status=%s duration_ms=%d', request_id, request.method,
                    request.url.path, response.status_code, round((time.monotonic() - start) * 1000))
        return response

    @app.exception_handler(StoreError)
    async def store_error(request: Request, exc: StoreError):
        return JSONResponse({'error': {'code': exc.code, 'message': str(exc), 'request_id': request.state.request_id}}, status_code=exc.status)

    @app.exception_handler(ImageError)
    async def image_error(request: Request, exc: ImageError):
        return JSONResponse({'error': {'code': 'invalid_image', 'message': str(exc), 'request_id': request.state.request_id}}, status_code=422)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError):
        # Do not echo multipart payloads, model output, credentials or raw image bytes.
        return JSONResponse({'error': {'code': 'invalid_request', 'message': 'The request contains invalid or unsupported fields.',
                                       'request_id': request.state.request_id}}, status_code=422)

    def repo() -> Repository:
        if app.state.repository is None:
            raise app.state.store_error or StoreError('Persistence is unavailable.', 503, 'persistence_unavailable')
        return app.state.repository

    @app.get('/api/health')
    async def health():
        available = app.state.repository is not None
        from .provider_queue import AI_PAUSE_REASON
        ai_status = 'paused' if settings.ai_paused else ('configured' if settings.gemini_api_key else 'unconfigured')
        return {'status': 'ready' if available else 'configuration_required',
                'ai_paused': settings.ai_paused, 'ai_status': ai_status,
                'ai_pause_reason': AI_PAUSE_REASON if settings.ai_paused else None,
                'persistence': app.state.repository.persistence if available else 'unavailable',
                'persistent': available and app.state.repository.persistence == 'mongodb',
                'gemini': {'configured': bool(settings.gemini_api_key), 'model': settings.gemini_model,
                           'status': ai_status, 'paused': settings.ai_paused,
                           'pause_reason': AI_PAUSE_REASON if settings.ai_paused else None},
                'world_id': settings.world_id,
                'evidence': app.state.recognizer.evidence.status() if hasattr(app.state.recognizer, 'evidence') else {'fixture': True},
                'semantic_retrieval': {'configured': bool(settings.embedding_model and settings.mongodb_uri), 'model': settings.embedding_model or None, 'index': settings.vector_index, 'paused': settings.ai_paused},
                'quality': {'available': app.state.quality is not None, 'operator_required': True, 'ai_paused': settings.ai_paused},
                'island': {'available': app.state.island is not None, 'runtime': 'local_backend', 'state_store': app.state.repository.persistence if available else 'unavailable'},
                'colonies': {'available': app.state.colonies is not None, 'runtime': 'local_backend'},
                'message': str(app.state.store_error) if app.state.store_error else ('Development memory mode: records disappear on restart.' if settings.repository == 'memory' else None)}

    @app.post('/api/battles', response_model=Battle)
    async def create(body: CreateBattle):
        return await asyncio.to_thread(repo().create_battle, body.request_id)

    @app.get('/api/battles/{battle_id}', response_model=Battle)
    async def get_battle(battle_id: str):
        return await asyncio.to_thread(repo().get_battle, battle_id)

    @app.post('/api/battles/{battle_id}/captures', response_model=Observation)
    async def capture(battle_id: str, image: UploadFile = File(...), capture_id: str = Form(...),
                      slot: int = Form(...), source: Literal['camera', 'upload'] = Form(...), crop: str | None = Form(None)):
        repo()
        if slot not in (0, 1) or not re.fullmatch(r'[A-Za-z0-9_:-]{1,100}', capture_id):
            raise StoreError('Invalid player slot or capture ID.', 422, 'invalid_request')
        try:
            selected_crop = Crop.model_validate_json(crop) if crop else None
        except (ValidationError, ValueError):
            raise StoreError('The selected crop is invalid.', 422, 'invalid_crop')
        data = await image.read(settings.max_upload_bytes + 1)
        await image.close()
        try:
            return await app.state.service.submit_capture(battle_id, capture_id, slot, source, data,
                                                          image.content_type or '', selected_crop)
        except (StoreError, ImageError):
            raise
        except Exception as exc:
            logger.warning('recognition_failed battle_id=%s capture_id=%s category=%s model=%s', battle_id, capture_id, type(exc).__name__, settings.gemini_model)
            raise StoreError('Object recognition could not finish. Retry the same photograph or choose another one.', 502, 'recognition_failed') from exc

    @app.post('/api/battles/{battle_id}/captures/{capture_id}/select', response_model=Observation)
    async def select(battle_id: str, capture_id: str, body: SelectCapture):
        repo()
        try:
            return await app.state.service.select_capture(battle_id, capture_id, body.crop)
        except (StoreError, ImageError):
            raise
        except Exception as exc:
            logger.warning('selection_failed battle_id=%s capture_id=%s category=%s', battle_id, capture_id, type(exc).__name__)
            raise StoreError('The selected object could not be checked. Retry this selection.', 502, 'recognition_failed') from exc

    @app.get('/api/battles/{battle_id}/captures/{capture_id}', response_model=Observation)
    async def capture_observation(battle_id: str, capture_id: str):
        capture = await asyncio.to_thread(repo().get_capture, battle_id, capture_id)
        if not capture.get('observation'):
            raise StoreError('This capture is still being prepared.', 409, 'capture_processing')
        return await app.state.service._recover_observation(battle_id, capture)

    @app.post('/api/battles/{battle_id}/captures/{capture_id}/feedback')
    async def feedback(battle_id: str, capture_id: str, body: FeedbackSubmission):
        return await asyncio.to_thread(repo().submit_feedback, battle_id, capture_id, body.model_dump())

    @app.post('/api/battles/{battle_id}/captures/{capture_id}/correct', response_model=Observation)
    async def correct(battle_id: str, capture_id: str, body: CorrectionRequest):
        repo()
        try:
            return await app.state.service.correct_capture(battle_id, capture_id, body.model_dump())
        except (StoreError, ImageError): raise
        except Exception as exc:
            logger.warning('correction_failed battle_id=%s category=%s', battle_id, type(exc).__name__)
            raise StoreError('Correction could not finish. Your original proposal is retained; retry when ready.', 502, 'correction_failed') from exc

    @app.post('/api/battles/{battle_id}/confirm', response_model=Battle)
    async def confirm(battle_id: str, body: ConfirmCapture):
        return await asyncio.to_thread(repo().confirm_capture, battle_id, body.player_slot, body.capture_id)

    @app.post('/api/battles/{battle_id}/start', response_model=Battle)
    async def start(battle_id: str, body: StartBattle):
        return await asyncio.to_thread(repo().start_battle, battle_id, body.playback_mode)

    @app.post('/api/battles/{battle_id}/finalize', response_model=Battle)
    async def finalize(battle_id: str):
        return await asyncio.to_thread(repo().finalize_battle, battle_id)

    @app.post('/api/battles/{battle_id}/cancel', response_model=Battle)
    async def cancel(battle_id: str):
        return await asyncio.to_thread(repo().cancel_battle, battle_id)

    @app.get('/api/world')
    async def world():
        return await asyncio.to_thread(repo().world)

    @app.get('/api/world/characters/{character_id}/history')
    async def history(character_id: str):
        return await asyncio.to_thread(repo().history, character_id)

    @app.patch('/api/world/characters/{character_id}')
    async def character_state(character_id: str, body: CharacterState):
        return await asyncio.to_thread(repo().update_character, character_id, body.activity)

    @app.get('/api/media/{media_id}')
    async def media(media_id: str):
        if not re.fullmatch(r'[a-f0-9]{64}', media_id):
            raise StoreError('Image not found.', 404, 'not_found')
        item = await asyncio.to_thread(repo().get_media, media_id)
        return Response(bytes(item['data']), media_type=item['mime_type'],
                        headers={'Cache-Control': 'private, max-age=31536000, immutable', 'ETag': f'"{media_id}"'})
    from .quality_api import register_quality_routes
    register_quality_routes(app)
    from .island_api import register_island_routes
    register_island_routes(app)
    from .colony_api import register_colony_routes
    register_colony_routes(app)
    return app

app = create_app()
