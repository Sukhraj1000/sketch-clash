"""No network: validate test cleanup scope, authorization fallback and closing."""
from types import SimpleNamespace

import pytest
from pymongo.errors import OperationFailure

from backend.tests.mongo_fixture_cleanup import cleanup_owned_mongo_fixture


DATABASE = 'sketch_test_' + '1' * 32


class FixtureRepo:
    def __init__(self, database=DATABASE, drop_code=None, collection_code=None):
        self.settings = SimpleNamespace(mongodb_database=database)
        self.db = SimpleNamespace(name=database, list_collection_names=self.names,
                                  drop_collection=self.drop_collection)
        self.client = SimpleNamespace(drop_database=self.drop_database)
        self.collections = ['battles', 'worldCharacters', 'media']
        self.calls = []
        self.closed = False
        self.drop_code = drop_code
        self.collection_code = collection_code

    def names(self):
        self.calls.append(('list', self.db.name))
        return list(self.collections)

    def drop_database(self, database):
        self.calls.append(('database', database))
        if self.drop_code:
            raise OperationFailure('Controlled error.', code=self.drop_code)
        self.collections.clear()

    def drop_collection(self, collection):
        self.calls.append(('collection', self.db.name, collection))
        if self.collection_code:
            raise OperationFailure('Controlled collection error.', code=self.collection_code)
        self.collections.remove(collection)

    def close(self):
        self.closed = True


def test_authorized_database_drop_verifies_cleanup_and_closes():
    repo = FixtureRepo()
    cleanup_owned_mongo_fixture(repo, DATABASE)
    assert repo.calls == [('database', DATABASE), ('list', DATABASE)]
    assert not repo.collections and repo.closed


def test_code_13_falls_back_only_within_its_exact_database():
    repo = FixtureRepo(drop_code=13)
    cleanup_owned_mongo_fixture(repo, DATABASE)
    assert repo.calls == [('database', DATABASE), ('list', DATABASE),
        ('collection', DATABASE, 'battles'), ('collection', DATABASE, 'worldCharacters'),
        ('collection', DATABASE, 'media'), ('list', DATABASE)]
    assert not repo.collections and repo.closed


@pytest.mark.parametrize('code', [18, 50, 91])
def test_other_failures_never_trigger_destructive_fallback_and_always_close(code):
    repo = FixtureRepo(drop_code=code)
    with pytest.raises(OperationFailure) as exc:
        cleanup_owned_mongo_fixture(repo, DATABASE)
    assert exc.value.code == code
    assert repo.calls == [('database', DATABASE)] and repo.closed
    assert len(repo.collections) == 3


@pytest.mark.parametrize('database,db_name,settings_name', [
    ('sketch_clash', 'sketch_clash', 'sketch_clash'),
    ('sketch_test_', 'sketch_test_', 'sketch_test_'),
    (DATABASE, 'sketch_clash', DATABASE),
    (DATABASE, DATABASE, 'sketch_clash'),
])
def test_live_or_mismatched_namespace_is_never_touched(database, db_name, settings_name):
    repo = FixtureRepo(database)
    repo.db.name = db_name
    repo.settings.mongodb_database = settings_name
    with pytest.raises(ValueError):
        cleanup_owned_mongo_fixture(repo, database)
    assert repo.calls == [] and repo.closed


def test_collection_denial_remains_a_failure_and_closes():
    repo = FixtureRepo(drop_code=13, collection_code=13)
    with pytest.raises(OperationFailure):
        cleanup_owned_mongo_fixture(repo, DATABASE)
    assert repo.closed and repo.collections


def test_remaining_collections_cannot_be_reported_as_success():
    repo = FixtureRepo(drop_code=13)
    repo.db.drop_collection = lambda name: None
    with pytest.raises(RuntimeError, match='still contains collections'):
        cleanup_owned_mongo_fixture(repo, DATABASE)
    assert repo.closed
