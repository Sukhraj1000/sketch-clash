"""An active research island cannot starve its eligible neighbour's council."""
import pytest

from app.colony_planner import population_fingerprint
from test_colony_planner import fixture


def record_population(repo, colonies, worker, **updates):
    def seed(tx):
        state = worker._state(tx, True)
        state.update(updates)
        for colony in colonies.snapshot()['colonies']:
            state['population_fingerprints'][colony['id']] = population_fingerprint(colony)
            state['milestone_fingerprints'][colony['id']] = worker._milestone_fingerprint(colony)
        tx.put('colonyPlanner', state)
    repo.transaction(seed)


@pytest.mark.asyncio
async def test_repeated_completion_wakeups_alternate_eligible_islands_on_slow(fixture):
    repo, colonies, provider, clock, worker = fixture
    original = colonies.snapshot
    completed = 0

    def snapshot():
        value = original()
        value['colonies'][1]['island']['projects'] = [{'id': 'new-assembly', 'level': completed}]
        return value

    colonies.snapshot = snapshot
    worker.queue.set_pacing('slow')
    record_population(repo, colonies, worker, last_colony_id='losers')
    chosen = []
    for index in range(4):
        # Loser research keeps changing; Winner Island has no new milestone and
        # used to be excluded from the milestone-only preference on every turn.
        completed += 1
        clock.add(worker.interval + 6)
        worker._check_population()
        state = repo.read(worker._state)
        expected = 'winners' if index % 2 == 0 else 'losers'
        assert state['preferred_colony_id'] == expected
        run = worker.request('completion-' + str(index), automatic=True,
                             colony_id=state['preferred_colony_id'], trigger=state['next_trigger'])
        chosen.append(run['colony_id'])
        await worker.run(run['id'])

    assert chosen == ['winners', 'losers', 'winners', 'losers']
    assert len(provider.calls) == 4
    assert worker.queue.pacing_mode == 'slow'
    assert worker.queue.background_min_dispatch_interval_seconds == 60


@pytest.mark.parametrize('trigger', ['project_or_experiment_completed', 'population_changed'])
def test_stale_automatic_preference_cannot_override_fair_turn_at_request_time(fixture, trigger):
    repo, colonies, provider, _, worker = fixture
    record_population(repo, colonies, worker, last_colony_id='losers')
    # Cover the race between the observation and request transactions, including
    # repeated arrivals. The prior council already heard this island first.
    run = worker.request('stale-priority-' + trigger, colony_id='losers', automatic=True, trigger=trigger)
    assert run['colony_id'] == 'winners'
    assert worker.sessions()[0]['trigger'] == 'review_progress'
    assert provider.calls == []


@pytest.mark.parametrize('unavailable', ['paused', 'cooling'])
def test_only_available_island_can_continue_without_waiting_for_its_neighbour(fixture, unavailable):
    repo, colonies, provider, clock, worker = fixture
    original = colonies.snapshot

    def snapshot():
        value = original()
        value['colonies'][0]['island']['paused'] = unavailable == 'paused'
        return value

    colonies.snapshot = snapshot
    record_population(repo, colonies, worker, last_colony_id='losers',
        validation_backoff={'winners': {'until': clock() + 300}} if unavailable == 'cooling' else {})
    run = worker.request('available-' + unavailable, colony_id='losers', automatic=True)
    assert run['colony_id'] == 'losers'
    assert provider.calls == []


def test_explicit_manual_council_keeps_the_requested_island(fixture):
    repo, colonies, provider, _, worker = fixture
    record_population(repo, colonies, worker, last_colony_id='losers')
    run = worker.request('manual-same-island', colony_id='losers')
    assert run['colony_id'] == 'losers'
    assert provider.calls == []
