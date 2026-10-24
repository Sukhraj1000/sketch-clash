"""Explicit local settings. Secret values are excluded from representations and logs."""
from dataclasses import dataclass, field
from pathlib import Path
from datetime import datetime, timezone
import os
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]

@dataclass(frozen=True)
class Settings:
    gemini_api_key: str = field(default='', repr=False)
    gemini_model: str = 'gemini-4-argon'
    mongodb_uri: str = field(default='', repr=False)
    mongodb_database: str = 'sketch_clash'
    world_id: str = 'shared-demo'
    repository: str = 'mongodb'
    max_upload_bytes: int = 5 * 1024 * 1024
    max_image_pixels: int = 24_000_000
    inference_max_edge: int = 1600
    api_timeout_seconds: int = 60
    evidence_timeout_seconds: int = 30
    recognition_concurrency: int = 2
    repair_attempts: int = 2
    transport_retries: int = 1
    yolo_model: str = 'yolo11n.pt'
    yolo_enabled: bool = True
    ocr_enabled: bool = True
    embedding_model: str = ''
    embedding_dimensions: int = 768
    vector_index: str = 'character_types_vector'
    frontend_origin: str = 'http://127.0.0.1:5173'
    # Zero removes the old artificial daily ceiling. Provider project quotas still apply.
    colony_requests_per_day: int = 0
    colony_proposal_model: str = 'gemini-4-argon'
    colony_reply_model: str = 'gemini-3.8-flash'
    colony_session_interval_seconds: int = 120
    gemini_provider_concurrency: int = 1
    gemini_requests_per_minute: int = 4
    gemini_requests_per_day: int = 200
    gemini_max_pending: int = 8
    ai_paused: bool = False
    gemini_key_source: str = 'explicit_settings'
    settings_loaded_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    @classmethod
    def load(cls) -> 'Settings':
        key_source = 'inherited_environment' if 'GEMINI_API_KEY' in os.environ else '.env.local'
        load_dotenv(PROJECT_ROOT / '.env.local', override=False)
        def boolean(key: str, default: str = 'true') -> bool:
            return os.getenv(key, default).lower() in {'1', 'true', 'yes'}
        return cls(
            gemini_api_key=os.getenv('GEMINI_API_KEY', ''),
            gemini_key_source=key_source,
            ai_paused=boolean('SKETCH_AI_PAUSED', 'false'),
            gemini_model=os.getenv('GEMINI_MODEL', 'gemini-4-argon'),
            mongodb_uri=os.getenv('MONGODB_URI', ''),
            mongodb_database=os.getenv('MONGODB_DATABASE', 'sketch_clash'),
            world_id=os.getenv('SKETCH_WORLD_ID', 'shared-demo'),
            repository=os.getenv('SKETCH_REPOSITORY', 'mongodb'),
            max_upload_bytes=int(os.getenv('MAX_UPLOAD_BYTES', str(5 * 1024 * 1024))),
            max_image_pixels=int(os.getenv('MAX_IMAGE_PIXELS', '24000000')),
            inference_max_edge=int(os.getenv('INFERENCE_MAX_EDGE', '1600')),
            api_timeout_seconds=int(os.getenv('GEMINI_TIMEOUT_SECONDS', '60')),
            evidence_timeout_seconds=int(os.getenv('EVIDENCE_TIMEOUT_SECONDS', '30')),
            recognition_concurrency=int(os.getenv('RECOGNITION_CONCURRENCY', '2')),
            yolo_model=os.getenv('YOLO_MODEL', 'yolo11n.pt'),
            yolo_enabled=boolean('YOLO_ENABLED'),
            ocr_enabled=boolean('OCR_ENABLED'),
            embedding_model=os.getenv('EMBEDDING_MODEL', ''),
            embedding_dimensions=int(os.getenv('EMBEDDING_DIMENSIONS', '768')),
            vector_index=os.getenv('MONGODB_VECTOR_INDEX', 'character_types_vector'),
            frontend_origin=os.getenv('FRONTEND_ORIGIN', 'http://127.0.0.1:5173'),
            colony_requests_per_day=max(0, int(os.getenv('COLONY_REQUESTS_PER_DAY', '0'))),
            colony_proposal_model=os.getenv('COLONY_PROPOSAL_MODEL', 'gemini-4-argon'),
            colony_reply_model=os.getenv('COLONY_REPLY_MODEL', 'gemini-3.8-flash'),
            colony_session_interval_seconds=max(15, int(os.getenv('COLONY_SESSION_INTERVAL_SECONDS', '120'))),
            gemini_provider_concurrency=max(1, min(8, int(os.getenv('GEMINI_PROVIDER_CONCURRENCY', '1')))),
            gemini_requests_per_minute=max(1, int(os.getenv('GEMINI_REQUESTS_PER_MINUTE', '4'))),
            gemini_requests_per_day=max(1, int(os.getenv('GEMINI_REQUESTS_PER_DAY', '200'))),
            gemini_max_pending=max(1, int(os.getenv('GEMINI_MAX_PENDING', '8'))),
        )
