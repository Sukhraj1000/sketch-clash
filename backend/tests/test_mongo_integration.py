"""Opt-in REAL MongoDB transaction checks. Creates and deletes its own uniquely named test DB.

SKETCH_RUN_MONGO_TESTS=1 .venv/bin/python -m pytest backend/tests/test_mongo_integration.py -q
Uses configured .env.local MONGODB_URI, or SKETCH_TEST_MONGODB_URI for an isolated local replica set.
This suite does not exercise Atlas Vector Search, which requires its own ready Atlas index.
Cleanup falls back to dropping this fixture's collections when the app role
does not allow dropDatabase; no broader permissions are required.
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
from backend.tests.mongo_fixture_cleanup import cleanup_owned_mongo_fixture

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
        cleanup_owned_mongo_fixture(repo, database)


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


def test_real_mongo_price_cache_restart_competing_leases_and_immutable_receipts(mongo_state):
    """Two API repositories share one lease and preserve each published receipt."""
    from threading import Barrier

    from backend.app.price_cache import PriceCache, POLICY, COLLECTION, SNAPSHOT_COLLECTION

    settings, repo, clock = mongo_state
    second = MongoRepository(settings, clock)
    try:
        first_cache, second_cache = PriceCache(repo), PriceCache(second)
        first_cache.ensure_indexes()
        second_cache.ensure_indexes()
        barrier = Barrier(2)
        def claim(item):
            cache, owner = item
            barrier.wait(timeout=5)
            return owner, cache.claim('ceramic mug', owner)
        with ThreadPoolExecutor(max_workers=2) as workers:
            results = list(workers.map(claim, [(first_cache, 'worker-a'), (second_cache, 'worker-b')]))
        assert sum(claimed for _, claimed in results) == 1
        owner = next(owner for owner, claimed in results if claimed)
        winner = first_cache if owner == 'worker-a' else second_cache
        receipt = {'amount_gbp': 8.0, 'currency': 'GBP', 'source': 'curated_retail',
                   'status': 'available', 'policy_version': POLICY, 'confidence': 'category_reference',
                   'label': 'Independent retail reference fixture', 'observed_at': clock(),
                   'listings': [{'title': 'Ceramic mug', 'amount_gbp': 8.0,
                                 'url': 'https://retailer.example/mug'}]}
        saved = winner.store('ceramic mug', owner, receipt, ttl_seconds=1)
        assert saved['cache']['persistence'] == 'mongodb'
        assert repo.db[COLLECTION].count_documents({}) == 1
        before = list(repo.db[SNAPSHOT_COLLECTION].find({}))
        assert len(before) == 1 and before[0]['id'] == saved['cache']['snapshot_id']

        # A genuinely new repository/client must recover the same quote receipt.
        second.close()
        second = MongoRepository(settings, clock)
        restarted = PriceCache(second)
        cached = restarted.get('CERAMIC_MUG')
        assert cached['amount_gbp'] == 8.0
        assert cached['cache']['hit'] is True
        assert cached['cache']['snapshot_id'] == saved['cache']['snapshot_id']
        assert not restarted.claim('ceramic mug', 'redundant-call')

        # Expired cache/leases must not let a late worker publish or clear the
        # second process's active refresh. Both old and new receipts are retained.
        clock.advance(1000)
        assert restarted.get('ceramic mug') is None
        assert first_cache.claim('ceramic mug', 'expired-worker', lease_seconds=1)
        clock.advance(1000)
        assert restarted.claim('ceramic mug', 'fresh-worker')
        assert first_cache.store('ceramic mug', 'expired-worker', receipt) is None
        assert not first_cache.fail('ceramic mug', 'expired-worker', 'provider_unavailable')
        changed = deepcopy(receipt)
        changed['amount_gbp'] = changed['listings'][0]['amount_gbp'] = 9.0
        changed['observed_at'] = clock()
        updated = restarted.store('ceramic mug', 'fresh-worker', changed)
        assert updated['cache']['snapshot_id'] != saved['cache']['snapshot_id']
        assert first_cache.get('ceramic mug')['amount_gbp'] == 9.0
        assert repo.db[SNAPSHOT_COLLECTION].count_documents({}) == 2
        assert repo.db[SNAPSHOT_COLLECTION].find_one({'_id': before[0]['_id']}) == before[0]
        assert not any('expireAfterSeconds' in item for item in repo.db[COLLECTION].list_indexes())
    finally:
        second.close()
