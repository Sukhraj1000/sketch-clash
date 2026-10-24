"""Provider fixtures verify actor isolation, durable decisions and shared spending ceilings."""
import asyncio
from copy import deepcopy
import json
from types import SimpleNamespace
import pytest
from app.config import Settings
from app.repository import MemoryRepository, StoreError
from app.colony_planner import ColonyPlanner, MODEL
from app.island_planner import utc_day
from test_provider_queue import queue_with_advancing_clock

class Clock:
    def __init__(self): self.value = 1792790000.0
    def __call__(self): return self.value
    def add(self, seconds=61): self.value += seconds

class Colonies:
    def __init__(self): self.applied={}; self.paused=False; self.failure=False
    def snapshot(self):
        return {'enabled':True,'colonies':[{'id':c,'name':c,'island':{'enabled':True,'paused':self.paused,
            'agents':[{'id':c+'-agent','character_id':c+'-character','display_name':c+' mug'}]}} for c in ('winners','losers')]}
    def observation(self, colony, actor):
        assert actor == colony+'-agent'
        return {'colony_id':colony,'actor':{'id':actor,'name':colony+' mug','allowed_actions':['carry','build','rest'],
            'capabilities':['carry'],'persona':{'motto':'Help our own island.'},'memory':[]},
            'resources':{'materials':2},'projects':[],'board':[], 'last_receipts':[]}
    def apply_decision(self, colony, actor, decision, run_id):
        if self.failure: self.failure=False; raise StoreError('Transient database failure.',503)
        if decision.get('action') not in ['carry','build','rest']:
            raise StoreError('This object cannot do that.',422,'capability_denied')
        self.applied.setdefault(run_id, {'colony':colony,'actor':actor,'decision':decision})
        return {'decision':{'id':run_id,'accepted':True},'snapshot':{'private':'must not duplicate'}}

class Provider:
    def __init__(self):
        self.calls=[]; self.error=None; self.action='carry'
        self.aio=SimpleNamespace(interactions=SimpleNamespace(create=self.create))
    async def create(self, **kwargs):
        self.calls.append(kwargs)
        if self.error: raise self.error
        text=json.dumps({'action':self.action,'reason':'Supply our builders.','message':None,'claim_request_id':None})
        return SimpleNamespace(output_text=text, model_dump=lambda **kw:{'usage':{'total_tokens':197},'model_version':'fixture'})

@pytest.fixture
def fixture():
    clock=Clock(); settings=Settings(repository='memory',gemini_api_key='fixture-only',colony_requests_per_day=24)
    repo=MemoryRepository(settings); colonies=Colonies(); provider=Provider()
    return repo,colonies,provider,clock,ColonyPlanner(repo,colonies,settings,client=provider,clock=clock,
        provider_queue=queue_with_advancing_clock(clock, clock.add))

@pytest.mark.asyncio
async def test_actor_context_is_separate_and_turn_replay_has_no_new_provider_call(fixture):
    repo,colonies,provider,clock,worker=fixture
    before=deepcopy(repo._data); assert worker.status()['requests_today']==0; assert before==repo._data
    run=worker.request('first','winners'); await worker.run(run['id'])
    assert worker.status()['last_status']=='completed'
    assert worker.status()['requests_today']==1 and worker.status()['reported_tokens']==197
    assert len(provider.calls)==1 and colonies.applied[run['id']]['actor']=='winners-agent'
    assert 'losers' not in provider.calls[0]['input']
    assert provider.calls[0]['model']==MODEL and provider.calls[0]['store'] is False
    assert provider.calls[0]['generation_config']=={'thinking_level':'medium','max_output_tokens':2048}
    assert 'fixture-only' not in json.dumps(provider.calls)
    assert worker.request('first','winners')['status']=='completed'
    await worker.run(run['id']); assert len(provider.calls)==1
    with pytest.raises(StoreError): worker.request('first','losers')
    clock.add(); other=worker.request('second'); await worker.run(other['id'])
    assert other['colony_id']=='losers'
    assert 'winners' not in provider.calls[1]['input']
    assert 'snapshot' not in worker.status()['runs'][0]['receipt']

@pytest.mark.asyncio
async def test_capabilities_rechecked_after_model_output(fixture):
    _,colonies,provider,_,worker=fixture; provider.action='water'
    run=worker.request('bad','winners'); await worker.run(run['id'])
    assert not colonies.applied
    assert worker.status()['last_status']=='rejected'
    assert not worker.status()['auto_blocked'] and worker.status()['requests_today']==1
    assert worker.status()['validation_backoff']['winners']['code']=='capability_denied'

@pytest.mark.asyncio
async def test_prior_legacy_usage_and_both_islands_share_one_daily_ceiling(fixture):
    repo,_,provider,clock,worker=fixture
    def seed(tx):
        state=worker.legacy._state(tx,True)
        state.update(day=utc_day(clock()),requests_today=23,reserved_tokens=23*7000)
        tx.put('islandPlanner',state)
    repo.transaction(seed)
    run=worker.request('last','winners'); await worker.run(run['id']); clock.add()
    with pytest.raises(StoreError) as exc: worker.request('overflow','losers')
    assert exc.value.code=='planner_daily_limit'
    assert len(provider.calls)==1 and worker.status()['remaining_requests']==0
    clock.add(86400)
    run=worker.request('tomorrow','losers'); await worker.run(run['id'])
    assert worker.status()['requests_today']==1

@pytest.mark.asyncio
async def test_unknown_provider_outcome_is_not_retried(fixture):
    _,colonies,provider,_,worker=fixture; provider.error=TimeoutError()
    run=worker.request('timeout','winners'); await worker.run(run['id']); await worker.run(run['id'])
    assert len(provider.calls)==1 and not colonies.applied
    assert worker.status()['last_status']=='uncertain'
    assert worker.status()['reserved_tokens']==7000 and worker.status()['auto_blocked']

@pytest.mark.asyncio
async def test_saved_decision_recovers_after_write_failure_without_provider_replay(fixture):
    _,colonies,provider,_,worker=fixture; colonies.failure=True
    run=worker.request('recover','winners'); await worker.run(run['id'])
    assert worker.status()['last_status']=='applying'
    await worker.run(run['id'])
    assert worker.status()['last_status']=='completed'
    assert len(provider.calls)==1 and len(colonies.applied)==1

@pytest.mark.asyncio
async def test_pause_or_switch_prevents_queued_provider_request(fixture):
    _,colonies,provider,_,worker=fixture
    run=worker.request('pause','winners'); colonies.paused=True
    await worker.run(run['id'])
    assert not provider.calls and worker.status()['requests_today']==0
    colonies.paused=False; worker.toggle(False)
    with pytest.raises(StoreError) as exc: worker.request('disabled','losers')
    assert exc.value.code=='planner_disabled'

@pytest.mark.asyncio
async def test_restart_marks_running_request_uncertain(fixture):
    repo,_,provider,_,worker=fixture
    run=worker.request('crash','winners')
    def mark(tx):
        state=tx.get('colonyReasoning',run['id']); state['status']='running'; tx.put('colonyReasoning',state)
    repo.transaction(mark)
    await worker.start(); await worker.close()
    assert worker.status()['last_status']=='uncertain' and not provider.calls

@pytest.mark.asyncio
async def test_stale_board_conflict_skips_turn_without_disabling_future_agents(fixture):
    _,colonies,provider,clock,worker=fixture
    original=colonies.apply_decision
    def stale(*args):
        raise StoreError('This request has already been claimed.',409,'request_unavailable')
    colonies.apply_decision=stale
    run=worker.request('stale','winners'); await worker.run(run['id'])
    assert worker.status()['last_status']=='rejected'
    assert not worker.status()['auto_blocked'] and len(provider.calls)==1
    assert worker.status()['active_run'] is None
    colonies.apply_decision=original; clock.add(901)
    next_run=worker.request('next-automatic',automatic=True)
    await worker.run(next_run['id'])
    assert next_run['colony_id']=='losers' and worker.status()['last_status']=='completed'

def test_concurrent_key_replay_checks_colony_inside_transaction(fixture):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    repo,_,_,_,worker=fixture
    original=repo.read; gate=Barrier(2)
    def synchronized_read(operation):
        result=original(operation)
        if result is None: gate.wait(timeout=5)
        return result
    repo.read=synchronized_read
    def request(side):
        try: return worker.request('same-concurrent-key',side)
        except StoreError as exc: return exc
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(request,('winners','losers')))
    assert sum(isinstance(result,StoreError) for result in results)==1
    assert next(result for result in results if isinstance(result,StoreError)).code=='request_conflict'
    for side,result in zip(('winners','losers'),results):
        if not isinstance(result,StoreError): assert result['colony_id']==side

@pytest.mark.asyncio
async def test_invalid_provider_proposal_keeps_bounded_diagnostic_without_fake_receipt(fixture):
    repo,colonies,provider,_,worker=fixture
    async def invalid(**kwargs):
        provider.calls.append(kwargs)
        return SimpleNamespace(output_text=json.dumps({'action':'carry','reason':'x'*241}),
            model_dump=lambda **kw:{'usage':{'total_tokens':100},'status':'completed'})
    provider.aio.interactions.create=invalid
    run=worker.request('invalid-schema','winners'); await worker.run(run['id'])
    saved=repo._data['colonyReasoning'][run['id']]
    assert saved['status']=='rejected' and not colonies.applied
    assert saved['validation_errors'][0]['field']=='reason'
    assert saved['proposal_text'] and saved['provider_status']=='completed'
    assert 'receipt' not in saved and worker.status()['requests_today']==1
    assert 'reason' in worker.status()['error']


def test_crowded_council_context_keeps_proposals_and_receipts_within_existing_budget(fixture):
    _,colonies,_,_,worker=fixture
    original=colonies.observation
    def crowded(side, actor):
        result=original(side,actor)
        result['planning']={'mode':'crew','selected_project_id':'garden','candidates':[{
            'project_id':'beacon','feasible':False,'missing_capabilities':['energy']}]}
        result['council']=[{'id':'council-1','at':'2026-10-24','chosen_project_id':'garden',
            'reason':'Energy cannot be supplied.','participants':[{'private_large_detail':'x'*30000}]}]
        result['project_discussion']=[{'id':f'proposal-{i}','actor_id':f'actor-{i}','actor_name':'Mug',
            'kind':'proposal','project_id':'garden','text':'Useful supply work. '*12,'origin':'model'} for i in range(40)]
        result['board']=[{'id':f'request-{i}','kind':'request','resource':'water','quantity':2,
            'text':'Need water. '*20,'evidence':{'irrelevant_detail':'x'*30000}} for i in range(12)]
        result['last_receipts']=[{'id':f'receipt-{i}','sequence':i,'resource_delta':{'water':2},
            'description':'Water supplied.','irrelevant_detail':'x'*30000} for i in range(4)]
        return result
    colonies.observation=crowded
    payload,encoded=worker._input({'colony_id':'winners','agent_id':'winners-agent'})
    from app.colony_planner import SYSTEM
    assert len(encoded)+len(SYSTEM)<=20000
    assert payload['council'][0]['chosen_project_id']=='garden'
    assert payload['project_discussion'][0]['id']=='proposal-0'
    assert payload['last_receipts'][0]['id']=='receipt-0'
    assert 'irrelevant_detail' not in encoded and 'private_large_detail' not in encoded
    assert len(payload['project_discussion'])>=4

class CouncilColonies(Colonies):
    def __init__(self):
        super().__init__(); self.extra = False; self.resolutions = []; self.provenances = []
    def snapshot(self):
        snapshot = super().snapshot()
        for colony in snapshot['colonies']:
            colony['island']['agents'] = [{'id': colony['id']+'-agent-'+str(i),
                'character_id': colony['id']+'-character-'+str(i), 'display_name': 'Object '+str(i),
                'allowed_actions': ['carry','build','rest'], 'capabilities': ['carry']} for i in range(3 + int(self.extra))]
        return snapshot
    def observation(self, colony, actor):
        return {'colony_id': colony, 'actor': {'id': actor, 'allowed_actions': ['carry','build','rest']},
            'resources': {'materials':2}, 'projects': [{'id':'garden'}], 'board': [], 'last_receipts': []}
    def apply_decision(self, colony, actor, decision, run_id, provenance=None):
        self.provenances.append(provenance)
        self.applied.setdefault(run_id, decision)
        return {'decision': {'id': run_id, 'message_ids': ['board-'+run_id]}}
    def resolve_council(self, session_id, colony_id, participant_ids, fingerprint):
        self.resolutions.append((session_id, colony_id, participant_ids))
        return {'status':'agreed','project_id':'garden','reason':'Two distinct residents supported the garden.'}


@pytest.mark.asyncio
async def test_separate_agents_read_actual_committed_replies_and_session_is_bounded():
    clock=Clock(); settings=Settings(repository='memory',gemini_api_key='fixture-only')
    repo=MemoryRepository(settings); colonies=CouncilColonies(); provider=Provider()
    async def reply(**kwargs):
        provider.calls.append(kwargs)
        payload=json.loads(kwargs['input']); conversation=payload['council_session']['conversation']
        if conversation:
            assert conversation[-1]['text'] == 'Build the garden, reply '+str(len(conversation)-1)
            assert conversation[-1]['id'].startswith('board-')
            assert conversation[-1]['actor_id'] != payload['actor']['id']
        decision={'message': {'kind':'proposal' if not conversation else 'support', 'project_id':'garden',
            'text':'Build the garden, reply '+str(len(conversation))}, 'reason':'Useful shared work.'}
        return SimpleNamespace(output_text=json.dumps(decision),model_dump=lambda **kw:{'usage':{'total_tokens':20}})
    provider.aio.interactions.create=reply
    worker=ColonyPlanner(repo,colonies,settings,client=provider,clock=clock,
        provider_queue=queue_with_advancing_clock(clock, clock.add))
    worker.request('council','winners')
    for _ in range(6):
        current=worker.status()['active_run']; assert current
        await worker.run(current['id'])
    status=worker.status()
    assert not status['active_run'] and len(provider.calls)==6
    assert status['sessions'][0]['status']=='agreed' and len(status['sessions'][0]['messages'])==6
    assert len({json.loads(c['input'])['actor']['id'] for c in provider.calls})==3
    assert provider.calls[0]['model']=='gemini-4-argon' and provider.calls[1]['model']=='gemini-3.8-flash'
    assert colonies.provenances[1]['reply_to_id']==status['sessions'][0]['messages'][0]['id']
    assert len(colonies.resolutions)==1
    assert status['max_requests_per_day']==0 and status['remaining_requests'] is None


@pytest.mark.asyncio
async def test_new_resident_invalidates_old_session_before_next_model_call():
    clock=Clock(); settings=Settings(repository='memory',gemini_api_key='fixture-only')
    repo=MemoryRepository(settings); colonies=CouncilColonies(); provider=Provider()
    worker=ColonyPlanner(repo,colonies,settings,client=provider,clock=clock,
        provider_queue=queue_with_advancing_clock(clock, clock.add))
    run=worker.request('before-arrival','winners'); colonies.extra=True
    await worker.run(run['id'])
    assert not provider.calls and not colonies.applied
    assert worker.sessions()[0]['status']=='stale'
    assert not worker.status()['auto_blocked']
    clock.add(3); worker._check_population()
    replacement=worker.request('after-arrival','winners',automatic=True,trigger='population_changed')
    assert replacement['id'] != run['id']
    assert worker.sessions()[0]['population_fingerprint'] != worker.sessions()[1]['population_fingerprint']


@pytest.mark.asyncio
async def test_definite_429_is_retried_with_diagnostics_without_duplicate_publication(fixture):
    repo,colonies,provider,clock,worker=fixture
    class RateLimitError(Exception):
        status_code=429
        response=SimpleNamespace(headers={'retry-after':'10'})
    provider.error=RateLimitError('Sensitive provider message KEY_MUST_NOT_ESCAPE')
    run=worker.request('throttled','winners'); await worker.run(run['id'])
    status=worker.status()
    assert status['last_status']=='retry_wait' and not status['auto_blocked']
    assert status['active_run']['provider_diagnostic']['status_code']==429
    assert 'KEY_MUST_NOT_ESCAPE' not in json.dumps(status)
    await worker.run(run['id']); assert len(provider.calls)==1
    clock.add(20); provider.error=None; await worker.run(run['id'])
    assert worker.status()['last_status']=='completed' and len(provider.calls)==2
    assert len(colonies.applied)==1


def test_population_fingerprint_tracks_attributes_but_not_resource_ticks():
    from app.colony_planner import population_fingerprint
    colony=CouncilColonies().snapshot()['colonies'][0]
    before=population_fingerprint(colony)
    colony['island']['resources']={'materials':1000}
    assert population_fingerprint(colony)==before
    colony['island']['agents'][0]['capabilities'].append('store_water')
    assert population_fingerprint(colony)!=before

@pytest.mark.asyncio
async def test_restart_applies_durable_provider_output_without_repeating_request(fixture):
    repo,colonies,provider,_,worker=fixture
    run=worker.request('response-saved-before-crash','winners')
    def saved(tx):
        current=tx.get('colonyReasoning',run['id'])
        current.update(status='running',received_at='2026-10-24T10:00:00+00:00',
            proposal_text=json.dumps({'action':'carry','reason':'Use the persisted answer.'}))
        tx.put('colonyReasoning',current)
    repo.transaction(saved)
    await worker.start(); await worker.close()
    assert repo._data['colonyReasoning'][run['id']]['status']=='applying'
    await worker.run(run['id'])
    assert not provider.calls and len(colonies.applied)==1
    assert repo._data['colonyReasoning'][run['id']]['status']=='completed'


@pytest.mark.asyncio
async def test_cleanup_cannot_relabel_an_already_committed_turn(fixture):
    repo,colonies,provider,_,worker=fixture
    run=worker.request('committed-before-cleanup','winners'); await worker.run(run['id'])
    worker._fail(run['id'],'interrupted','Worker stopped during subsequent memory indexing.')
    assert repo._data['colonyReasoning'][run['id']]['status']=='completed'
    assert len(colonies.applied)==len(provider.calls)==1


def test_new_session_cannot_replace_a_council_awaiting_local_resolution(fixture):
    repo,_,_,clock,worker=fixture
    run=worker.request('awaiting-resolution','winners')
    def resolving(tx):
        state=worker._state(tx,True); state['pending_run_id']=None
        tx.put('colonyPlanner',state)
        session=tx.get('colonyCouncilSessions',run['session_id'])
        session.update(status='resolving',completed_turns=session['max_turns'])
        tx.put('colonyCouncilSessions',session)
    repo.transaction(resolving); clock.add(3)
    with pytest.raises(StoreError) as exc: worker.request('new-council-too-soon','losers')
    assert exc.value.code=='planner_busy'
    assert worker.status()['active_session_id']==run['session_id']


@pytest.mark.asyncio
async def test_slow_queue_refreshes_stock_useful_work_and_receipts_before_dispatch(fixture):
    from app.provider_queue import ProviderQueue
    repo, colonies, provider, clock, worker = fixture
    original = colonies.observation
    stock = {'materials': 2}
    def observation(colony, actor):
        value = original(colony, actor)
        value['resources'] = dict(stock)
        value['revision'] = stock['materials']
        value['work_options'] = {'useful_actions': [] if stock['materials'] == 1000 else ['carry'],
                                 'full_resources': ['materials'] if stock['materials'] == 1000 else []}
        value['last_receipts'] = [{'id': 'actual-work', 'resource_delta': {'materials': 0},
            'reserved_cost': {'ideas': 1}, 'resource_net_delta': {'ideas': -1}, 'progress_delta': 2,
            'decision_origin': 'model', 'execution_origin': 'local_executor',
            'scheduling_reason': 'Materials are full; completed accepted construction instead.',
            'requested_action': 'carry', 'action_switched': True}]
        value['board'] = [{'id': 'committed-report', 'kind': 'report', 'receipt_ids': ['actual-work'],
                          'interpretation': 'Materials are full; completed accepted construction instead.'}]
        return value
    colonies.observation = observation
    async def sleep(seconds):
        stock['materials'] = 1000
        clock.add(seconds)
    queue = ProviderQueue(clock=clock, sleep=sleep)
    queue.set_pacing('slow')
    async def earlier_request(): pass
    await queue.run('earlier', earlier_request)
    worker.queue = queue
    run = worker.request('storage-fills-while-waiting', 'winners')
    await worker.run(run['id'])
    sent = json.loads(provider.calls[0]['input'])
    assert sent['resources']['materials'] == 1000
    assert sent['work_options']['useful_actions'] == []
    assert sent['last_receipts'][0]['progress_delta'] == 2
    assert sent['last_receipts'][0]['reserved_cost'] == {'ideas': 1}
    assert sent['last_receipts'][0]['action_switched'] is True
    assert sent['last_receipts'][0]['requested_action'] == 'carry'
    assert sent['board'][0]['receipt_ids'] == ['actual-work']
    assert sent['board'][0]['interpretation'] == sent['last_receipts'][0]['scheduling_reason']
    saved = repo._data['colonyReasoning'][run['id']]
    assert saved['observation_summary']['full_resources'] == ['materials']
    assert saved['observation_summary']['revision'] == 1000
    assert saved['observation_summary']['observed_at'] == sent['observed_at']


@pytest.mark.asyncio
async def test_arrival_while_queued_reopens_council_without_spending_another_dispatch():
    from app.provider_queue import ProviderQueue
    clock = Clock(); settings = Settings(repository='memory', gemini_api_key='fixture-only')
    repo = MemoryRepository(settings); colonies = CouncilColonies(); provider = Provider()
    async def sleep(seconds):
        colonies.extra = True
        clock.add(seconds)
    queue = ProviderQueue(clock=clock, sleep=sleep)
    queue.set_pacing('slow')
    async def earlier_request(): pass
    await queue.run('earlier', earlier_request)
    worker = ColonyPlanner(repo, colonies, settings, client=provider, clock=clock, provider_queue=queue)
    run = worker.request('arrival-while-waiting', 'winners')
    await worker.run(run['id'])
    assert provider.calls == []
    assert worker.sessions()[0]['status'] == 'stale'
    assert worker.status()['last_status'] == 'rejected'
    assert worker.status()['auto_blocked'] is False
    assert queue.status()['local_usage']['requests_last_24_hours'] == 1
    assert queue.status()['last_error'] is None


@pytest.mark.asyncio
async def test_disabling_discussions_during_queue_wait_prevents_provider_dispatch(fixture):
    from app.provider_queue import ProviderQueue
    _, _, provider, clock, worker = fixture
    async def sleep(seconds):
        worker.toggle(False)
        clock.add(seconds)
    queue = ProviderQueue(clock=clock, sleep=sleep)
    queue.set_pacing('slow')
    async def earlier_request(): pass
    await queue.run('earlier', earlier_request)
    worker.queue = queue
    run = worker.request('disabled-while-queued', 'winners')
    await worker.run(run['id'])
    assert provider.calls == [] and worker.status()['enabled'] is False
    assert queue.status()['local_usage']['requests_last_24_hours'] == 1
    assert queue.status()['last_error'] is None


def test_paused_island_preference_cannot_starve_an_available_automatic_council(fixture):
    repo, colonies, provider, _, worker = fixture
    original = colonies.snapshot
    def snapshot():
        value = original()
        value['colonies'][0]['island']['paused'] = True
        return value
    colonies.snapshot = snapshot
    from app.colony_planner import population_fingerprint
    def seed(tx):
        state = worker._state(tx, True)
        state.update(preferred_colony_id='winners', next_trigger='population_changed')
        for colony in colonies.snapshot()['colonies']:
            state['population_fingerprints'][colony['id']] = population_fingerprint(colony)
            state['milestone_fingerprints'][colony['id']] = worker._milestone_fingerprint(colony)
        tx.put('colonyPlanner', state)
    repo.transaction(seed)
    worker._check_population()
    state = repo.read(worker._state)
    assert 'preferred_colony_id' not in state and 'next_trigger' not in state
    # Also cover the race where the preference was read just before the pause.
    run = worker.request('old-preference', colony_id='winners', automatic=True, trigger='population_changed')
    assert run['colony_id'] == 'losers'
    assert worker.sessions()[0]['trigger'] == 'review_progress'
    assert colonies.snapshot()['colonies'][0]['island']['paused'] is True
    assert provider.calls == []


def test_manual_council_does_not_silently_switch_away_from_a_paused_island(fixture):
    _, colonies, provider, _, worker = fixture
    original = colonies.snapshot
    def snapshot():
        value = original()
        value['colonies'][0]['island']['paused'] = True
        return value
    colonies.snapshot = snapshot
    with pytest.raises(StoreError) as exc:
        worker.request('manual-winner-only', colony_id='winners')
    assert exc.value.code == 'colony_not_ready'
    assert worker.sessions() == [] and provider.calls == []


@pytest.mark.asyncio
async def test_resumed_winner_waits_for_current_six_turn_council_then_gets_next_slow_council(fixture):
    """Resuming an island changes eligibility without interrupting its neighbour."""
    from datetime import datetime
    repo, colonies, provider, clock, worker = fixture
    original_snapshot, original_observation = colonies.snapshot, colonies.observation
    winner_paused = True

    def snapshot():
        value = original_snapshot()
        for colony in value['colonies']:
            side = colony['id']
            colony['island']['paused'] = side == 'winners' and winner_paused
            colony['island']['agents'] = [
                {'id': f'{side}-agent-{i}', 'character_id': f'{side}-character-{i}',
                 'display_name': f'{side} resident {i}'} for i in range(3)]
        return value

    def observation(side, actor):
        value = original_observation(side, side + '-agent')
        value['actor']['id'] = actor
        return value

    colonies.snapshot, colonies.observation = snapshot, observation
    worker.queue.set_pacing('slow')
    first = worker.request('loser-council-before-winner-resume', automatic=True)
    assert first['colony_id'] == 'losers'
    session_id = first['session_id']
    assert worker.sessions()[0]['max_turns'] == 6
    await worker.run(first['id'])

    # Mirror the observable state transition produced by the island resume API.
    # The scheduler fixture deliberately has no runtime or live provider client.
    winner_paused = False
    worker._check_population()
    state = repo.read(worker._state)
    assert state['preferred_colony_id'] == 'winners'
    assert state['active_session_id'] == session_id
    completed = [first['id']]
    for _ in range(5):
        turn = worker.status()['active_run']
        assert turn['colony_id'] == 'losers' and turn['session_id'] == session_id
        completed.append(turn['id'])
        await worker.run(turn['id'])
        clock.add(6)
        worker._check_population()

    assert worker.status()['active_run'] is None
    assert worker.status()['active_session_id'] is None
    assert len(provider.calls) == 6
    starts = sorted(datetime.fromisoformat(repo._data['colonyReasoning'][run_id]['dispatched_at']).timestamp()
                    for run_id in completed)
    assert all(right - left >= 60 for left, right in zip(starts, starts[1:]))

    clock.add(6)
    worker._check_population()
    state = repo.read(worker._state)
    following = worker.request('winner-council-after-resume', automatic=True,
        colony_id=state.get('preferred_colony_id'), trigger=state.get('next_trigger', 'review_progress'))
    assert following['colony_id'] == 'winners'
    assert worker.sessions()[0]['trigger'] == 'population_changed'
    assert worker.queue.pacing_mode == 'slow' and not worker.queue.paused
    assert worker.queue.min_dispatch_interval_seconds == 15
    assert worker.queue.background_min_dispatch_interval_seconds == 60
    assert len(provider.calls) == 6  # Scheduling the next council does not invoke the SDK.
