"""Independent actor turns against the real colony ledger; provider calls are fixtures."""
import json
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.colonies import ColoniesStore
from app.colony_planner import ColonyPlanner
from app.config import Settings
from app.main import create_app
from app.repository import MemoryRepository
from test_provider_queue import queue_with_advancing_clock


class Clock:
    def __init__(self):
        self.value = datetime(2026, 10, 24, 12, tzinfo=timezone.utc)

    def __call__(self):
        return self.value.isoformat()

    def seconds(self):
        return self.value.timestamp()

    def advance(self, seconds):
        self.value += timedelta(seconds=seconds)


class Provider:
    def __init__(self):
        self.calls = []
        self.decision = {'action': 'water', 'reason': 'Replenish our cistern stock.'}
        self.aio = SimpleNamespace(interactions=SimpleNamespace(create=self.create))

    async def create(self, **kwargs):
        self.calls.append(deepcopy(kwargs))
        return SimpleNamespace(output_text=json.dumps(self.decision), model_dump=lambda **kw: {
            'usage': {'total_tokens': 197}, 'model_version': 'fixture-only'})


def completed_battle(repo, identifier, winner, loser):
    fighters = []
    for slot, name in enumerate((winner, loser)):
        fighters.append({'player_slot': slot, 'canonical_type_id': name, 'object_type': name,
            'display_name': f'Fixture {name.title()}', 'image_ref': f'private-fixture-photo-{name}',
            'visual_spec': {'template_id': 'generic', 'palette': ['#FF3344']}, 'archetype': 'balanced'})
    repo.transaction(lambda tx: tx.put('battles', {'_id': identifier, 'id': identifier,
        'world_id': repo.world_id, 'status': 'completed', 'winner_slot': 0,
        'completed_at': repo.clock(), 'fighters': fighters}))


@pytest.fixture
def colony():
    clock = Clock()
    settings = Settings(repository='memory', world_id='fixture-colony-integration',
                        gemini_api_key='fixture-only', colony_requests_per_day=24)
    repo = MemoryRepository(settings, clock)
    completed_battle(repo, 'fixture-battle-one', 'bottle', 'pencil')
    store = ColoniesStore(repo)
    store.initialize()
    provider = Provider()
    worker = ColonyPlanner(repo, store, settings, client=provider, clock=clock.seconds,
                           provider_queue=queue_with_advancing_clock(clock.seconds, clock.advance))
    return repo, store, provider, clock, worker


def side(store, name):
    return next(item for item in store.snapshot()['colonies'] if item['id'] == name)


def actor(store, colony_id, object_type):
    return next(item for item in side(store, colony_id)['island']['agents'] if item['object_type'] == object_type)


@pytest.mark.asyncio
async def test_real_actor_context_and_execution_are_isolated_and_replay_safe(colony):
    repo, store, provider, clock, worker = colony
    bottle = actor(store, 'winners', 'bottle')
    pencil = actor(store, 'losers', 'pencil')
    winner_before = side(store, 'winners')['island']
    loser_before = deepcopy(side(store, 'losers'))
    run = worker.request('actual-bottle-turn', 'winners', bottle['id'])
    await worker.run(run['id'])
    assert worker.status()['last_status'] == 'completed'
    context = json.loads(provider.calls[0]['input'])
    assert context['actor']['id'] == bottle['id']
    assert context['actor']['action_yields']['water']['water'] == 4
    assert pencil['id'] not in provider.calls[0]['input']
    assert 'private-fixture-photo' not in provider.calls[0]['input']
    assert 'estimated_value_gbp' not in provider.calls[0]['input']
    accepted = actor(store, 'winners', 'bottle')
    assert accepted['task'] == bottle['task']  # A decision cannot rewrite work in flight.
    assert side(store, 'winners')['island']['resources'] == winner_before['resources']
    assert side(store, 'losers') == loser_before
    assert accepted['pending_decision_action'] == 'water'
    record = next(row for row in repo._data['colonyDecisions'].values() if row['run_id'] == run['id'])
    clock.advance(40)
    store.advance()
    receipts = [row for row in repo._data['islandEvents'].values() if row.get('decision_id') == record['id']]
    assert len(receipts) == 1 and receipts[0]['resource_delta']['water'] > 0
    assert receipts[0]['world_id'] == store.islands['winners'].world_id
    assert receipts[0]['decision_origin'] == 'model'
    before_replay = deepcopy(repo._data)
    assert worker.request('actual-bottle-turn', 'winners', bottle['id'])['status'] == 'completed'
    await worker.run(run['id'])
    store.apply_decision('winners', bottle['id'], record['decision'], run['id'])
    assert repo._data == before_replay
    assert len(provider.calls) == 1


@pytest.mark.asyncio
async def test_cross_colony_report_evidence_is_rejected_without_stock_or_board_mutation(colony):
    repo, store, provider, clock, worker = colony
    clock.advance(40)
    store.advance()
    bottle = actor(store, 'winners', 'bottle')
    pencil = actor(store, 'losers', 'pencil')
    foreign = next(row for row in repo._data['islandEvents'].values()
                   if row.get('character_id') == pencil['character_id'] and 'sequence' in row)
    provider.decision = {'reason': 'Claim a receipt from the wrong colony.',
                         'message': {'kind': 'report', 'receipt_id': foreign['id'], 'text': 'I completed this.'}}
    before = deepcopy(side(store, 'winners'))
    run = worker.request('foreign-report', 'winners', bottle['id'])
    await worker.run(run['id'])
    assert worker.status()['last_status'] == 'rejected'
    assert foreign['id'] not in provider.calls[0]['input']
    assert side(store, 'winners') == before
    assert not repo._data.get('colonyDecisions')
    assert worker.status()['requests_today'] == 1


@pytest.mark.asyncio
async def test_late_decision_never_executes_before_its_acceptance(colony):
    repo, store, provider, clock, worker = colony
    bottle = actor(store, 'winners', 'bottle')
    clock.advance(61)  # Simulate a delayed local tick while the actor context is prepared.
    run = worker.request('after-worker-delay', 'winners', bottle['id'])
    await worker.run(run['id'])
    assert worker.status()['last_status'] == 'completed'
    record = next(row for row in repo._data['colonyDecisions'].values() if row['run_id'] == run['id'])
    accepted_at = datetime.fromisoformat(record['created_at'])
    store.advance()
    current = actor(store, 'winners', 'bottle')['task']
    if current.get('decision_id') == record['id']:
        assert datetime.fromisoformat(current['started_at']) >= accepted_at
    receipts = [row for row in repo._data.get('islandEvents', {}).values() if row.get('decision_id') == record['id']]
    assert not receipts  # No time passed after the newly accepted decision.
    clock.advance(40)
    store.advance()
    receipts = [row for row in repo._data['islandEvents'].values() if row.get('decision_id') == record['id']]
    assert len(receipts) == 1
    assert datetime.fromisoformat(receipts[0]['at']) > accepted_at


@pytest.mark.asyncio
async def test_model_request_offer_and_report_are_backed_by_actual_contribution(colony):
    repo, store, provider, clock, worker = colony
    completed_battle(repo, 'fixture-battle-two', 'pencil', 'mug')
    store.initialize()
    bottle = actor(store, 'winners', 'bottle')
    pencil = actor(store, 'winners', 'pencil')
    # Hold the supplier outside automatic matching so this fixture exercises a
    # model-origin offer, rather than racing the separate deterministic helper.
    store.command({'colony_id': 'winners', 'kind': 'assign', 'character_id': bottle['character_id'],
                   'assignment': 'rest', 'idempotency_key': 'hold-supplier-for-fixture'})
    provider.decision = {'reason': 'Ask our container to replenish water.', 'message': {
        'kind': 'request', 'resource': 'water', 'quantity': 4, 'project_id': 'garden'}}
    request_run = worker.request('request-water', 'winners', pencil['id'])
    await worker.run(request_run['id'])
    assert worker.status()['last_status'] == 'completed'
    request = next(row for row in repo._data['colonyBoard'].values()
                   if row['kind'] == 'request' and row['origin'] == 'model')
    assert request['status'] == 'open'
    clock.advance(61)
    store.command({'colony_id': 'winners', 'kind': 'assign', 'character_id': bottle['character_id'],
                   'assignment': 'auto', 'idempotency_key': 'release-supplier-for-fixture'})
    provider.decision = {'action': 'water', 'reason': 'Answer the pencil with water.',
                        'claim_request_id': request['id'],
                        'message': {'kind': 'offer', 'request_id': request['id']}}
    claim_run = worker.request('offer-water', 'winners', bottle['id'])
    await worker.run(claim_run['id'])
    assert repo._data['colonyReasoning'][claim_run['id']]['status'] == 'completed'
    assert worker.status()['active_run']['agent_id'] == pencil['id']
    accepted = repo._data['colonyBoard'][request['id']]
    assert accepted['status'] == 'claimed' and not accepted['receipt_ids']
    assert not repo._data.get('colonyContributions')
    clock.advance(40)
    store.advance()
    fulfilled = repo._data['colonyBoard'][request['id']]
    assert fulfilled['status'] == 'fulfilled' and fulfilled['remaining'] == 0
    contributions = [row for row in repo._data['colonyContributions'].values() if row['request_id'] == request['id']]
    assert sum(row['quantity'] for row in contributions) == 4
    receipt = repo._data['islandEvents'][contributions[0]['receipt_id']]
    assert receipt['character_id'] == bottle['character_id']
    assert receipt['decision_origin'] == 'model' and receipt['resource_delta']['water'] >= 4
    assert contributions[0]['created_at'] >= repo._data['colonyReasoning'][claim_run['id']]['received_at']
    clock.advance(21)
    # The peer answers inside this same council before the supplier reports its
    # actual receipt. No manual request is needed to schedule the next speaker.
    provider.decision = {'message': {'kind': 'question', 'text': 'Did the water reach our shared stock?'}}
    peer_run = worker.status()['active_run']
    assert peer_run['agent_id'] == pencil['id']
    await worker.run(peer_run['id']); clock.advance(3)
    provider.decision = {'message': {'kind': 'report', 'receipt_id': receipt['id'],
                                     'text': 'I also built an imaginary castle.'}}
    report_run = worker.status()['active_run']
    assert report_run['agent_id'] == bottle['id']
    await worker.run(report_run['id'])
    assert repo._data['colonyReasoning'][report_run['id']]['status'] == 'completed'
    report = next(row for row in repo._data['colonyBoard'].values()
                  if row['kind'] == 'report' and row['origin'] == 'model')
    assert report['verified'] and report['text'] == receipt['description']
    assert report['receipt_ids'] == [receipt['id']]
    assert 'castle' not in report['text']
    clock.advance(3)
    provider.decision = {'message': {'kind': 'reflection', 'text': 'The committed delivery supplies our builders.'}}
    await worker.run(worker.status()['active_run']['id'])
    assert not worker.status()['active_run']
    assert len(provider.calls) == worker.status()['requests_today'] == 5


def route_fixture():
    settings = Settings(repository='memory', world_id='fixture-colony-http', gemini_api_key='')
    repo = MemoryRepository(settings, Clock())
    completed_battle(repo, 'fixture-route-battle', 'bottle', 'pencil')
    return settings, repo


def test_colony_http_reads_do_not_enroll_start_tick_or_spend():
    settings, repo = route_fixture()
    with TestClient(create_app(settings, repo, object())) as client:
        before = deepcopy(repo._data)
        for _ in range(3):
            response = client.get('/api/colonies')
            assert response.status_code == 200
            result = response.json()
            assert result['enabled'] is False
            assert result['planner']['requests_today'] == 0
            assert result['runtime']['worker_active'] is True
            assert all(not item['island']['enabled'] and not item['characters'] for item in result['colonies'])
        assert repo._data == before
        denied = client.post('/api/colonies/think', json={
            'idempotency_key': 'no-key-no-call', 'colony_id': 'winners'})
        assert denied.status_code == 503
        assert repo._data == before


def test_colony_http_start_pause_replay_restart_and_input_authority():
    settings, repo = route_fixture()
    original = deepcopy(repo.world())
    with TestClient(create_app(settings, repo, object())) as client:
        start = client.post('/api/colonies/start', json={})
        assert start.status_code == 200
        state = start.json()
        assert state['enabled'] and state['planner']['requests_today'] == 0
        assert [len(item['characters']) for item in state['colonies']] == [1, 1]
        assert client.get('/api/island').json()['planner']['enabled'] is False
        before_repeat = deepcopy(repo._data)
        assert client.post('/api/colonies/start', json={}).status_code == 200
        assert repo._data == before_repeat
        command = {'idempotency_key': 'pause-winners-fixture', 'colony_id': 'winners', 'kind': 'pause'}
        paused = client.post('/api/colonies/command', json=command)
        assert paused.status_code == 200
        assert [item['island']['paused'] for item in paused.json()['colonies']] == [True, False]
        before_replay = deepcopy(repo._data)
        assert client.post('/api/colonies/command', json=command).status_code == 200
        assert repo._data == before_replay
        assert client.post('/api/colonies/command', json={**command, 'kind': 'resume'}).status_code == 409
        for extra in ({'resources': {'water': 9999}}, {'world_id': 'different'}, {'persona': {'role': 'Unrestricted'}}):
            assert client.post('/api/colonies/command', json={**command, **extra}).status_code == 422
        assert client.post('/api/colonies/command', json={**command, 'idempotency_key': 'evil-origin-fixture'},
                           headers={'Origin': 'https://untrusted.example'}).status_code == 403
        assert client.post('/api/colonies/planner', json={'enabled': False}).status_code == 200
        assert client.post('/api/colonies/start', json={}).json()['planner']['enabled'] is False
        assert client.get('/api/world').json() == original
    with TestClient(create_app(settings, repo, object())) as client:
        resumed = client.get('/api/colonies').json()
        assert resumed['enabled'] and resumed['planner']['enabled'] is False
        assert [item['island']['paused'] for item in resumed['colonies']] == [True, False]
        assert [len(item['characters']) for item in resumed['colonies']] == [1, 1]
        assert client.get('/api/world').json() == original


def test_optional_colony_planner_startup_failure_keeps_local_colonies_available(monkeypatch):
    def fail_indexes(self):
        raise RuntimeError('Fixture optional planner failure')
    monkeypatch.setattr(ColonyPlanner, 'ensure_indexes', fail_indexes)
    settings, repo = route_fixture()
    with TestClient(create_app(settings, repo, object())) as client:
        response = client.post('/api/colonies/start', json={})
        assert response.status_code == 200
        result = response.json()
        assert result['enabled'] and result['runtime']['worker_active']
        assert result['planner']['last_status'] == 'unavailable'
        assert client.post('/api/colonies/think', json={
            'idempotency_key': 'planner-unavailable', 'colony_id': 'winners'}).status_code == 503


def test_api_manual_priority_can_return_to_autonomous_crew_without_changing_other_shore():
    settings, repo = route_fixture()
    with TestClient(create_app(settings, repo, object())) as client:
        assert client.post('/api/colonies/start', json={}).status_code == 200
        before = client.get('/api/colonies').json()
        other = next(c for c in before['colonies'] if c['id']=='losers')
        manual=client.post('/api/colonies/command',json={
            'idempotency_key':'manual-project-fixture','colony_id':'winners','kind':'priority','project_id':'beacon'})
        assert manual.status_code==200
        assert next(c for c in manual.json()['colonies'] if c['id']=='winners')['planning']['mode']=='manual'
        command={'idempotency_key':'return-crew-fixture','colony_id':'winners','kind':'council','mode':'crew'}
        result=client.post('/api/colonies/command',json=command)
        assert result.status_code==200
        winner=next(c for c in result.json()['colonies'] if c['id']=='winners')
        assert winner['planning']['mode']=='crew'
        assert winner['planning']['selected_project_id']!='beacon'
        assert next(c for c in result.json()['colonies'] if c['id']=='losers')==other
        data=deepcopy(repo._data)
        assert client.post('/api/colonies/command',json=command).status_code==200
        assert data==repo._data
        assert client.post('/api/colonies/command',json={**command,'mode':'anything'}).status_code==422


@pytest.mark.asyncio
async def test_model_project_proposal_is_readable_to_next_same_island_actor(colony):
    repo,store,provider,clock,worker=colony
    completed_battle(repo,'second-colony-battle','pencil','mug')
    store.initialize()
    bottle=actor(store,'winners','bottle')
    pencil=actor(store,'winners','pencil')
    provider.decision={'reason':'Use our water capability.', 'message':{
        'kind':'proposal','project_id':'garden','text':'I can collect water; let us finish the garden.'}}
    run=worker.request('propose-garden-fixture','winners',bottle['id'])
    await worker.run(run['id'])
    assert repo._data['colonyReasoning'][run['id']]['status']=='completed'
    assert worker.status()['active_run']['agent_id']==pencil['id']
    payload,encoded=worker._input({'colony_id':'winners','agent_id':pencil['id']})
    proposal=next(item for item in payload['project_discussion'] if item['actor_id']==bottle['id'])
    assert proposal['kind']=='proposal' and proposal['text']==provider.decision['message']['text']
    assert proposal['id'] in repo._data['colonyBoard']
    assert not store.observation('losers',actor(store,'losers','pencil')['id'])['project_discussion']
    clock.advance(61)
    provider.decision={'message':{'kind':'support','project_id':'garden','proposal_id':proposal['id'],
        'text':'Agreed. I can help with construction and gather materials.'}}
    run2=worker.status()['active_run']
    assert run2['agent_id']==pencil['id'] and run2['session_id']==run['session_id']
    await worker.run(run2['id'])
    assert repo._data['colonyReasoning'][run2['id']]['status']=='completed'
    # Both invited residents have now spoken and agreed on a feasible build;
    # the council should not buy two redundant turns before handing off work.
    assert not worker.status()['active_run']
    clock.advance(3); store.advance()
    council=side(store,'winners')['council'][-1]
    assert council['chosen_project_id']=='garden'
    assert len(council['model_message_ids'])==2
    assert len(provider.calls)==2
    assert worker.sessions('winners')[0]['status']=='agreed'
