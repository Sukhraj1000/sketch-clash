"""Real Atlas vector retrieval with explicit unavailable states and no ownership effects."""
from __future__ import annotations

import asyncio
from collections import OrderedDict
from dataclasses import dataclass
from hashlib import sha256
import math
import inspect
from typing import Any
from .provider_queue import AI_PAUSE_REASON, require_ai_enabled

EMBEDDING_SCHEMA_VERSION = "1"


@dataclass(frozen=True)
class RetrievalConfig:
    model: str = "gemini-embedding-2"
    dimensions: int = 768
    index: str = "character_types_vector"
    timeout_seconds: float = 20


def normalized_text(text: str) -> str:
    return " ".join(text.split())[:1200]


def embedding_input(text: str, *, document: bool = False, title: str = "none", model: str = "gemini-embedding-2") -> tuple[str, dict]:
    """Versioned matching query/document preprocessing per Google's embedding guide."""
    text = normalized_text(text)
    if model == "gemini-embedding-2":
        return (f"title: {normalized_text(title)} | text: {text}" if document else f"task: search result | query: {text}"), {}
    if model == "gemini-embedding-001":
        return text, {"task_type": "RETRIEVAL_DOCUMENT" if document else "RETRIEVAL_QUERY"}
    raise ValueError("Only documented Gemini embedding models are supported.")


def vector_index_definition(dimensions: int = 768) -> dict:
    return {"fields": [{"type": "vector", "path": "embedding", "numDimensions": dimensions, "similarity": "cosine"},
                       *[{"type": "filter", "path": path} for path in ("approved", "embedding_model", "embedding_schema_version", "embedding_dimensions")]]}


class AtlasRetriever:
    def __init__(self, collection: Any = None, client: Any = None, config: RetrievalConfig | None = None, *, settings=None,
                 provider_category='embedding'):
        self.collection, self.client = collection, client
        if provider_category not in ('embedding', 'island_embedding', 'evaluation_embedding'):
            raise ValueError('Unknown embedding request category.')
        self.provider_category = provider_category
        self.settings = settings
        self.config = config or RetrievalConfig()
        self.provider_queue = None
        self._cache: OrderedDict[str, list[float]] = OrderedDict()
        self._lock = asyncio.Semaphore(1)

    async def embed(self, text: str, *, document: bool = False, title: str = "none") -> list[float]:
        require_ai_enabled(self.settings)
        if self.provider_queue: self.provider_queue.require_enabled()
        if self.client is None:
            raise RuntimeError("Gemini embedding access is not configured.")
        prepared, options = embedding_input(text, document=document, title=title, model=self.config.model)
        cache_key = sha256(f"{self.config.model}:{self.config.dimensions}:{EMBEDDING_SCHEMA_VERSION}:{document}:{prepared}".encode()).hexdigest()
        if cache_key in self._cache:
            self._cache.move_to_end(cache_key)
            return self._cache[cache_key][:]
        async with self._lock:
            async def invoke():
                return await asyncio.wait_for(self.client.aio.models.embed_content(model=self.config.model, contents=prepared,
                    config={"output_dimensionality": self.config.dimensions, **options}), timeout=self.config.timeout_seconds)
            response = await self.provider_queue.run(self.config.model, invoke, category=self.provider_category,
                prepare=getattr(self.client, 'check_admission', None)) if self.provider_queue else await invoke()
        vector = [float(x) for x in response.embeddings[0].values]
        if len(vector) != self.config.dimensions or not all(math.isfinite(x) for x in vector):
            raise ValueError("Embedding output dimensions or values did not match the index contract.")
        norm = math.sqrt(sum(x*x for x in vector))
        if not norm:
            raise ValueError("Embedding returned a zero vector.")
        vector = [x/norm for x in vector]
        self._cache[cache_key] = vector
        while len(self._cache) > 128:
            self._cache.popitem(last=False)
        return vector[:]

    async def search(self, description: str) -> dict:
        if getattr(self.settings, 'ai_paused', False) or (self.provider_queue and self.provider_queue.paused):
            return {'status': 'ai_paused', 'detail': AI_PAUSE_REASON, 'candidates': []}
        if self.collection is None:
            return {"status": "unavailable", "detail": "MongoDB Atlas is not configured.", "candidates": []}
        if self.client is None or not self.config.model:
            return {"status": "unavailable", "detail": "Set EMBEDDING_MODEL and GEMINI_API_KEY, then seed the vector index.", "candidates": []}
        try:
            vector = await self.embed(description)
            pipeline = [{"$vectorSearch": {"index": self.config.index, "path": "embedding", "queryVector": vector,
                "numCandidates": 60, "limit": 3, "filter": {"approved": True, "embedding_model": self.config.model,
                    "embedding_dimensions": self.config.dimensions, "embedding_schema_version": EMBEDDING_SCHEMA_VERSION}}},
                {"$project": {"_id": 0, "canonical_type_id": 1, "canonical_key": 1, "display_name": 1, "description": 1,
                              "template_id": 1, "score": {"$meta": "vectorSearchScore"}}}]
            async def read_records():
                if inspect.iscoroutinefunction(self.collection.aggregate):
                    cursor = await self.collection.aggregate(pipeline, maxTimeMS=int(self.config.timeout_seconds * 1000))
                    return await cursor.to_list(length=3)
                def query_sync():
                    return list(self.collection.aggregate(pipeline, maxTimeMS=int(self.config.timeout_seconds * 1000)))
                return await asyncio.to_thread(query_sync)
            records = await asyncio.wait_for(read_records(), timeout=self.config.timeout_seconds)
            return {"status": "completed" if records else "empty", "candidates": records,
                    "model": self.config.model, "schema_version": EMBEDDING_SCHEMA_VERSION,
                    "detail": "Semantic similarity only; these records do not establish identity or world ownership."}
        except Exception as exc:
            return {"status": "unavailable", "candidates": [], "error_category": type(exc).__name__,
                    "detail": "Semantic retrieval unavailable. Check embedding model access and the Atlas vector index; exact lookup still works."}

    async def seed(self, records: list[dict]) -> int:
        """Explicit setup operation, never invoked by loading a world or recognizing a capture."""
        if self.collection is None:
            raise RuntimeError("MongoDB Atlas is not configured.")
        count = 0
        for record in records:
            vector = await self.embed(record["description"], document=True, title=record["display_name"])
            query = {"canonical_key": record["canonical_key"]}
            update = {"$set": {**record, "embedding": vector, "embedding_model": self.config.model,
                "embedding_dimensions": self.config.dimensions, "embedding_schema_version": EMBEDDING_SCHEMA_VERSION}}
            if inspect.iscoroutinefunction(self.collection.update_one):
                await self.collection.update_one(query, update, upsert=True)
            else:
                await asyncio.to_thread(self.collection.update_one, query, update, upsert=True)
            count += 1
        return count
