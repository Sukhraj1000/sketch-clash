"""The real store accepts only a completed, current, independently-authored council."""
import json
from copy import deepcopy
from types import SimpleNamespace
import pytest
from app.colonies import ColoniesStore, route_completed_battle
from app.colony_planner import ColonyPlanner, population_fingerprint
from app.config import Settings
from app.repository import MemoryRepository, StoreError
from backend.tests.test_colonies import Clock, battle, side
from test_provider_queue import queue_with_advancing_clock


def setup_world():
    clock=Clock(); settings=Settings(repository='memory',world_id='real-council-fixture',gemini_api_key='fixture-key')
    repo=MemoryRepository(settings,clock)
    for identifier,kind in [('a','pencil'),('b','bottle'),('c','mug')]: battle(repo,identifier,kind,'battery')
    store=ColoniesStore(repo); store.initialize()
    return repo,store,clock,settings


def provider_for_garden():
    calls=[]
    async def create(**kwargs):
        payload=json.loads(kwargs['input']); calls.append(payload)
        conversation=payload['council_session']['conversation']
        decision={'reason':'Build a shared garden.', 'message':{'kind':'support' if conversation else 'proposal',
                    'project_id':'garden','text': 'I support the garden and its water supply.' if conversation else 'Shall we build a garden using our water and ideas?'}}
        return SimpleNamespace(output_text=json.dumps(decision),model_dump=lambda **kw:{'usage':{'total_tokens':40}})
    return SimpleNamespace(aio=SimpleNamespace(interactions=SimpleNamespace(create=create))),calls


@pytest.mark.asyncio
async def test_real_store_transcript_agreement_and_message_provenance():
    repo,store,clock,settings=setup_world(); provider,calls=provider_for_garden()
    worker=ColonyPlanner(repo,store,settings,client=provider,clock=lambda:clock.value.timestamp(),
        provider_queue=queue_with_advancing_clock(lambda:clock.value.timestamp(), clock.advance))
    worker.request('early-agreement-council','winners')
    for index in range(3):
        run=worker.status()['active_run']; assert run
        await worker.run(run['id']); clock.advance(3)
        if index < 2:
            # Two votes alone cannot silence the third invited participant.
            assert worker.sessions('winners')[0]['status']=='running'
            assert side(store)['planning']['selected_project_id'] is None
    session=worker.sessions('winners')[0]
    assert session['status']=='agreed' and session['project_id']=='garden'
    assert session['completed_turns']==3 and session['max_turns']==6
    assert session['completion_reason']=='validated_agreement'
    assert len(calls)==3 and len(session['messages'])==3
    assert not worker.status()['active_run']
    island=side(store)
    board={row['id']:row for row in island['board']}
    for index,message in enumerate(session['messages']):
        stored=board[message['id']]
        assert stored['origin']=='model' and stored['session_id']==session['id']
        assert stored['reply_to_id']==(session['messages'][index-1]['id'] if index else None)
        assert stored['seen_message_ids']==[m['id'] for m in session['messages'][:index]]
    assert island['planning']['selected_project_id']=='garden'
    before=deepcopy(repo._data)
    replay=store.resolve_council(session['id'],'winners',[a['id'] for a in session['participants']],session['population_fingerprint'])
    assert replay['status']=='agreed' and repo._data==before
    clock.advance(65); store.advance()
    assert any(a['task']['kind']=='build' for a in side(store)['island']['agents'])


@pytest.mark.asyncio
@pytest.mark.parametrize('case', ['missing_capability', 'silent_participant', 'manual_override'])
async def test_early_agreement_does_not_skip_required_evidence_or_override_controls(case):
    repo,store,clock,settings=setup_world(); calls=[]
    energy_before=side(store)['island']['resources']['energy']
    if case=='manual_override':
        store.command({'colony_id':'winners','kind':'priority','project_id':'workshop',
                       'idempotency_key':'manual-before-council'})
    async def create(**kwargs):
        payload=json.loads(kwargs['input']); calls.append(payload)
        decision={'message':{'kind':'support' if len(calls)>1 else 'proposal',
            'project_id':'beacon' if case=='missing_capability' else 'garden', 'text':'I support this project.'}}
        if case=='silent_participant' and len(calls)==3:
            decision={'action':'rest'}
        return SimpleNamespace(output_text=json.dumps(decision),model_dump=lambda **kw:{})
    provider=SimpleNamespace(aio=SimpleNamespace(interactions=SimpleNamespace(create=create)))
    worker=ColonyPlanner(repo,store,settings,client=provider,clock=lambda:clock.value.timestamp(),
        provider_queue=queue_with_advancing_clock(lambda:clock.value.timestamp(),clock.advance))
    worker.request('guarded-council-'+case,'winners')
    for _ in range(3):
        await worker.run(worker.status()['active_run']['id']); clock.advance(3)
    session=worker.sessions('winners')[0]
    assert session['status']=='running' and session['completed_turns']==3
    assert worker.status()['active_run'] and 'completion_reason' not in session
    assert side(store)['planning']['selected_project_id']==('workshop' if case=='manual_override' else None)
    assert side(store)['island']['resources']['energy']==energy_before
    for _ in range(3):
        await worker.run(worker.status()['active_run']['id']); clock.advance(3)
    session=worker.sessions('winners')[0]
    assert session['completed_turns']==6
    assert session['status']==('agreed' if case=='silent_participant' else 'no_agreement')
    if case=='manual_override':
        assert side(store)['planning']['selected_project_id']=='workshop'


@pytest.mark.asyncio
async def test_early_agreement_requires_committed_board_evidence_not_forged_transcript():
    repo,store,clock,settings=setup_world(); provider,_=provider_for_garden()
    worker=ColonyPlanner(repo,store,settings,client=provider,clock=lambda:clock.value.timestamp(),
        provider_queue=queue_with_advancing_clock(lambda:clock.value.timestamp(),clock.advance))
    worker.request('durable-evidence-council','winners')
    for _ in range(2):
        await worker.run(worker.status()['active_run']['id']); clock.advance(3)
    session=worker.sessions('winners')[0]
    unheard=session['participants'][2]['id']
    session['completed_turns']=3
    session['messages'].append({'actor_id':unheard,'origin':'model','kind':'support','project_id':'garden','text':'Invented agreement.'})
    assert not repo.read(lambda tx:store.council_has_early_agreement(tx,session))
    # A resolution marker cannot bypass the same evidence check in the executor.
    session['status']='resolving'; session['_id']=session['id']
    repo.transaction(lambda tx:tx.put('colonyCouncilSessions',session))
    with pytest.raises(StoreError) as exc:
        store.resolve_council(session['id'],'winners',[a['id'] for a in session['participants']],session['population_fingerprint'])
    assert exc.value.code=='council_incomplete'
    assert side(store)['planning']['selected_project_id'] is None


@pytest.mark.asyncio
@pytest.mark.parametrize('enroll_arrival', [False, True])
async def test_population_is_rechecked_after_early_agreement_before_project_selection(enroll_arrival):
    repo,store,clock,settings=setup_world(); provider,calls=provider_for_garden()
    worker=ColonyPlanner(repo,store,settings,client=provider,clock=lambda:clock.value.timestamp(),
        provider_queue=queue_with_advancing_clock(lambda:clock.value.timestamp(),clock.advance))
    original=store.resolve_council
    def resolve_after_arrival(*args):
        arriving=battle(repo,'arrival-at-resolution','plant','lamp')
        repo.transaction(lambda tx:route_completed_battle(tx,arriving,repo.world_id))
        if enroll_arrival:
            store.advance()
        return original(*args)
    store.resolve_council=resolve_after_arrival
    worker.request('arrival-after-agreement','winners')
    for _ in range(3):
        await worker.run(worker.status()['active_run']['id']); clock.advance(3)
    assert len(calls)==3 and worker.sessions('winners')[0]['status']=='stale'
    assert side(store)['planning']['selected_project_id'] is None


@pytest.mark.asyncio
async def test_early_readiness_rechecks_routed_residents_before_their_agents_are_enrolled():
    repo,store,clock,settings=setup_world(); provider,_=provider_for_garden()
    worker=ColonyPlanner(repo,store,settings,client=provider,clock=lambda:clock.value.timestamp(),
        provider_queue=queue_with_advancing_clock(lambda:clock.value.timestamp(),clock.advance))
    async def defer_resolution(session):
        pass
    worker._resolve=defer_resolution
    worker.request('routed-roster-readiness','winners')
    for _ in range(3):
        await worker.run(worker.status()['active_run']['id']); clock.advance(3)
    session=worker.sessions('winners')[0]
    assert session['status']=='resolving'
    assert repo.read(lambda tx:store.council_has_early_agreement(tx,session))
    before_agents=side(store)['island']['agents']
    arriving=battle(repo,'routed-before-enrollment','plant','lamp')
    repo.transaction(lambda tx:route_completed_battle(tx,arriving,repo.world_id))
    assert side(store)['island']['agents']==before_agents
    assert not repo.read(lambda tx:store.council_has_early_agreement(tx,session))
    # Even a session created from the latest routed roster must wait for its
    # newly eligible participant to be enrolled by the regular island worker.
    session['resident_ids']=[c['id'] for c in side(store)['characters']]
    assert not repo.read(lambda tx:store.council_has_early_agreement(tx,session))


def test_council_cannot_resolve_without_durable_session():
    _,store,_,_=setup_world(); island=side(store)
    with pytest.raises(StoreError) as exc:
        store.resolve_council('invented','winners',[a['id'] for a in island['island']['agents']],population_fingerprint(island))
    assert exc.value.code=='invalid_council_session'


@pytest.mark.asyncio
async def test_arrival_during_provider_request_prevents_stale_commit():
    repo,store,clock,settings=setup_world(); calls=[]
    async def create(**kwargs):
        calls.append(kwargs)
        arriving=battle(repo,'arrival','plant','lamp')
        repo.transaction(lambda tx: route_completed_battle(tx,arriving,repo.world_id))
        store.advance()
        return SimpleNamespace(output_text=json.dumps({'message':{'kind':'proposal','project_id':'garden','text':'Build the garden.'}}),model_dump=lambda **kw:{})
    provider=SimpleNamespace(aio=SimpleNamespace(interactions=SimpleNamespace(create=create)))
    worker=ColonyPlanner(repo,store,settings,client=provider,clock=lambda:clock.value.timestamp(),
        provider_queue=queue_with_advancing_clock(lambda:clock.value.timestamp(), clock.advance))
    run=worker.request('population-race','winners'); await worker.run(run['id'])
    assert len(calls)==1 and worker.sessions()[0]['status']=='stale'
    assert not worker.status()['auto_blocked']
    assert not [row for row in side(store)['board'] if row.get('session_id')==run['session_id'] and row['origin']=='model']


@pytest.mark.asyncio
async def test_rejected_research_does_not_disable_future_reasoning_and_feedback_is_visible():
    repo,store,clock,settings=setup_world()
    async def create(**kwargs):
        payload=json.loads(kwargs['input'])
        # A single object cannot invent extra physical intermediate supports.
        decision={'reason':'Test whether I span the river.', 'experiment':{
            'family':'support','subject_ids':[payload['actor']['character_id']],
            'hypothesis':'I can span the river using several supports.', 'expected_success':True,
            'context':{'span':1,'load':1,'support_count':4}}}
        return SimpleNamespace(output_text=json.dumps(decision),model_dump=lambda **kw:{})
    provider=SimpleNamespace(aio=SimpleNamespace(interactions=SimpleNamespace(create=create)))
    worker=ColonyPlanner(repo,store,settings,client=provider,clock=lambda:clock.value.timestamp(),
        provider_queue=queue_with_advancing_clock(lambda:clock.value.timestamp(), clock.advance))
    run=worker.request('invalid-support-count','winners'); await worker.run(run['id'])
    assert worker.status()['last_status']=='rejected' and not worker.status()['auto_blocked']
    assert repo._data['colonyReasoning'][run['id']]['validation_code']=='missing_support'
    payload,_=worker._input({'colony_id':'winners','agent_id':run['agent_id']})
    feedback=payload['recent_validation_feedback'][0]
    assert feedback['run_id']==run['id'] and feedback['code']=='missing_support'
    assert feedback['attempt']['experiment']['context']['support_count']==4
    assert not payload['learning']['experiments']


@pytest.mark.asyncio
@pytest.mark.parametrize('reason,origin', [('I will test my stability in this wind.','model'), ('','executor')])
async def test_experiment_only_turn_is_published_into_the_next_agents_conversation(reason,origin):
    repo,store,clock,settings=setup_world(); calls=[]
    async def create(**kwargs):
        payload=json.loads(kwargs['input']); calls.append(payload)
        if len(calls)==1:
            decision={'reason':reason, 'experiment':{
                'family':'hold','subject_ids':[payload['actor']['character_id']],
                'hypothesis':'My base keeps me stable in this wind.', 'expected_success':True,
                'context':{'wind_force':1,'load':1}}}
        else:
            message=payload['council_session']['conversation'][0]
            assert message['origin']==origin
            assert message['text']==(reason or 'The executor recorded this resident’s research submission. Inspect the attached evidence for its outcome.')
            assert message['evidence']['experiment']['status']=='completed'
            if origin=='executor': assert message['content_basis']=='executor_observation'
            decision={'message':{'kind':'reflection','text':'We can use that measured result when choosing our next test.'}}
        return SimpleNamespace(output_text=json.dumps(decision),model_dump=lambda **kw:{})
    provider=SimpleNamespace(aio=SimpleNamespace(interactions=SimpleNamespace(create=create)))
    worker=ColonyPlanner(repo,store,settings,client=provider,clock=lambda:clock.value.timestamp(),
        provider_queue=queue_with_advancing_clock(lambda:clock.value.timestamp(), clock.advance))
    run=worker.request('experiment-only-transcript','winners'); await worker.run(run['id'])
    session=worker.sessions('winners')[0]
    assert len(session['messages'])==1
    published=repo._data['colonyBoard'][session['messages'][0]['id']]
    assert published['kind']=='reflection' and published['evidence']['experiment']['status']=='completed'
    assert published['origin']==session['messages'][0]['origin']==origin
    clock.advance(3); await worker.run(worker.status()['active_run']['id'])
    assert len(calls)==2
