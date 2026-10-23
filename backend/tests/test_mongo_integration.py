"""Opt-in REAL MongoDB transaction checks. Creates and deletes its own uniquely named test DB.

SKETCH_RUN_MONGO_TESTS=1 .venv/bin/python -m pytest backend/tests/test_mongo_integration.py -q
Uses configured .env.local MONGODB_URI, or SKETCH_TEST_MONGODB_URI for an isolated local replica set.
This suite does not exercise Atlas Vector Search, which requires its own ready Atlas index.
"""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from dataclasses import replace
import os
from uuid import uuid4

import pytest

from backend.app.config import Settings
from backend.app.repository import MongoRepository, StoreError
from backend.tests.test_lifecycle import Clock, ready

pytestmark = pytest.mark.skipif(os.getenv('SKETCH_RUN_MONGO_TESTS') != '1', reason='Real MongoDB test requires explicit SKETCH_RUN_MONGO_TESTS=1.')


@pytest.fixture
def mongo_state():
    settings = Settings.load()
    uri = os.getenv('SKETCH_TEST_MONGODB_URI', '') or settings.mongodb_uri
    if not uri:
        pytest.skip('No MongoDB URI configured. No fake database is substituted.')
    database = f'sketch_test_{uuid4().hex}'
    settings = replace(settings, mongodb_uri=uri, mongodb_database=database, repository='mongodb')
    clock = Clock()
    repo = MongoRepository(settings, clock)
    try:
        yield settings, repo, clock
    finally:
        # This exact random database was created by this fixture, never an application database.
        repo.client.drop_database(database)
        repo.close()


def test_real_mongo_concurrent_creation_finalization_and_saved_media(mongo_state):
    settings, repo, clock = mongo_state
    with ThreadPoolExecutor(max_workers=8) as workers:
        created = list(workers.map(lambda _: repo.create_battle('concurrent-request'), range(12)))
    assert len({b['id'] for b in created}) == 1
    assert repo.db.battles.count_documents({}) == 1
    battle = ready(repo, settings, 'concurrent-request', types=('mug', 'mug'))
    started = repo.start_battle(battle['id'], 'normal')
    assert repo.world()['characters'] == []
    with pytest.raises(StoreError):
        repo.finalize_battle(battle['id'])
    clock.advance()
    with ThreadPoolExecutor(max_workers=8) as workers:
        completed = list(workers.map(lambda _: repo.finalize_battle(battle['id']), range(20)))
    assert all(b == completed[0] for b in completed)
    assert repo.db.worldCharacters.count_documents({}) == 1
    assert repo.db.encounters.count_documents({}) == 1
    resident = repo.world()['characters'][0]
    assert resident['distinct_battle_count'] == 1
    assert resident['visual_spec'] == started['fighters'][0]['visual_spec']
    assert repo.get_media(resident['image_ref'].rsplit('/', 1)[1])['data']
    assert completed[0]['completion']['durable'] is True
    assert repo.history(resident['id'])['encounters'][0]['slots'][0]['player_slot'] == 0


def test_real_mongo_first_insert_wins_and_world_reads_never_mutate(mongo_state):
    settings, repo, clock = mongo_state
    battles = [ready(repo, settings, f'first-{index}', types=('mug', 'mug'), colours=(colour, colour))
               for index, colour in enumerate(('#FF0000', '#0000FF'))]
    for battle in battles:
        repo.start_battle(battle['id'], 'quick')
    clock.advance()
    with ThreadPoolExecutor(max_workers=2) as workers:
        completed = list(workers.map(lambda b: repo.finalize_battle(b['id']), battles))
    residents = repo.world()['characters']
    assert len(residents) == 1 and residents[0]['distinct_battle_count'] == 2
    assert sum(bool(b['completion']['new_resident_ids']) for b in completed) == 1
    origin = next(b for b in battles if b['id'] == residents[0]['first_battle_id'])
    assert residents[0]['visual_spec'] == origin['pending_fighters'][0]['visual_spec']
    before = {name: list(repo.db[name].find({})) for name in ('worldCharacters', 'battles', 'encounters', 'worlds')}
    assert repo.world()['characters'] == residents
    after = {name: list(repo.db[name].find({})) for name in before}
    assert before == after
    # A new repository process restores the same durable snapshots and images.
    restored = MongoRepository(settings, clock)
    try:
        assert restored.world()['characters'] == residents
        assert restored.get_battle(origin['id'])['events'] == repo.get_battle(origin['id'])['events']
    finally:
        restored.close()
