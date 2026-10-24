"""Cleanup only the exact disposable database allocated by the calling fixture."""
import re

from pymongo.errors import OperationFailure


def cleanup_owned_mongo_fixture(repo, database):
    """Support an app role that can drop collections but not databases.

    The fixture supplies its freshly generated UUID name, never an inventory or
    prefix search. Retrying an earlier failed cleanup requires confirmation of
    ownership of that exact UUID; a matching prefix is not sufficient.
    """
    try:
        if (not re.fullmatch(r'sketch_test_[0-9a-f]{32}', database) or
                repo.db.name != database or repo.settings.mongodb_database != database):
            raise ValueError('Cleanup requires the exact disposable database allocated by this fixture.')
        try:
            repo.client.drop_database(database)
        except OperationFailure as exc:
            if exc.code != 13:
                raise
            # Never broaden Atlas permissions or retry a different namespace.
            for collection in repo.db.list_collection_names():
                repo.db.drop_collection(collection)
        if repo.db.list_collection_names():
            raise RuntimeError('Disposable MongoDB fixture still contains collections after cleanup.')
    finally:
        repo.close()
