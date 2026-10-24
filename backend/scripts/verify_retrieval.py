"""One real embedding + Atlas vector query; unavailable prerequisites are failures, never fixtures."""
import asyncio
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import Settings
from app.retrieval import AtlasRetriever, RetrievalConfig

async def main():
    settings = Settings.load()
    if settings.ai_paused:
        print('AI requests are paused. No retrieval verification request was sent.')
        return 1
    if not settings.mongodb_uri or not settings.gemini_api_key or not settings.embedding_model:
        print('Semantic retrieval unavailable: configure MONGODB_URI, GEMINI_API_KEY and EMBEDDING_MODEL locally, then run setup:retrieval.')
        return 1
    from pymongo import AsyncMongoClient
    from google import genai
    mongo = AsyncMongoClient(settings.mongodb_uri, serverSelectionTimeoutMS=5000)
    client = genai.Client(api_key=settings.gemini_api_key, http_options={'timeout': 20000, 'retry_options': {'attempts': 1}})
    try:
        retrieval = AtlasRetriever(mongo[settings.mongodb_database].characterTypes, client, RetrievalConfig(
            model=settings.embedding_model, dimensions=settings.embedding_dimensions, index=settings.vector_index), settings=settings)
        query = ' '.join(sys.argv[1:]) or 'A small handled vessel with an open top for a hot drink'
        outcome = await retrieval.search(query)
        print(json.dumps(outcome, indent=2))
        return 0 if outcome['status'] == 'completed' and outcome['candidates'] else 1
    finally:
        await client.aio.aclose()
        client.close()
        await mongo.close()

if __name__ == '__main__':
    raise SystemExit(asyncio.run(main()))
