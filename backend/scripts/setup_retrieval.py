"""Seed approved descriptions/embeddings and create the Atlas Vector Search index explicitly."""
import asyncio
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.catalog import CharacterCatalog
from app.config import Settings
from app.retrieval import AtlasRetriever, RetrievalConfig, vector_index_definition

async def main():
    settings = Settings.load()
    if settings.ai_paused:
        print('AI requests are paused. Retrieval setup did not send embeddings or change indexes.')
        return 1
    if not settings.mongodb_uri or not settings.gemini_api_key or not settings.embedding_model:
        print('Set MONGODB_URI, GEMINI_API_KEY and EMBEDDING_MODEL in .env.local first. No changes were made.')
        return 1
    from pymongo import AsyncMongoClient
    from pymongo.operations import SearchIndexModel
    from google import genai
    mongo = AsyncMongoClient(settings.mongodb_uri, serverSelectionTimeoutMS=5000)
    client = genai.Client(api_key=settings.gemini_api_key, http_options={'timeout': 20000, 'retry_options': {'attempts': 1}})
    try:
        await mongo.admin.command('ping')
        collection = mongo[settings.mongodb_database].characterTypes
        await collection.create_index('canonical_key', unique=True)
        retriever = AtlasRetriever(collection=collection, client=client, config=RetrievalConfig(
            model=settings.embedding_model, dimensions=settings.embedding_dimensions, index=settings.vector_index), settings=settings)
        count = await retriever.seed(CharacterCatalog.seed_records())
        existing = await (await collection.list_search_indexes()).to_list(length=100)
        names = {entry.get('name') for entry in existing}
        if settings.vector_index not in names:
            await collection.create_search_index(SearchIndexModel(name=settings.vector_index, type='vectorSearch',
                definition=vector_index_definition(settings.embedding_dimensions)))
        print(f'Seeded {count} approved character descriptions. Vector index: {settings.vector_index}.')
        print('Atlas builds indexes asynchronously. Check the index is READY in Atlas before verifying retrieval.')
        return 0
    except Exception as exc:
        print(f'Retrieval setup failed ({type(exc).__name__}). Check Atlas access, embedding access and index permissions. No credentials were logged.')
        return 1
    finally:
        await client.aio.aclose()
        client.close()
        await mongo.close()

if __name__ == '__main__':
    raise SystemExit(asyncio.run(main()))
