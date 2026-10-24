"""The real store accepts only a completed, current, independently-authored council."""
import json
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
    worker.request('six-turn-council','winners')
    for _ in range(6):
        run=worker.status()['active_run']; assert run
        await worker.run(run['id']); clock.advance(3)
    session=worker.sessions('winners')[0]
    assert session['status']=='agreed' and session['project_id']=='garden'
    assert len(calls)==6 and len(session['messages'])==6
    island=side(store)
    board={row['id']:row for row in island['board']}
    for index,message in enumerate(session['messages']):
        stored=board[message['id']]
        assert stored['origin']=='model' and stored['session_id']==session['id']
        assert stored['reply_to_id']==(session['messages'][index-1]['id'] if index else None)
        assert stored['seen_message_ids']==[m['id'] for m in session['messages'][:index]]
    assert island['planning']['selected_project_id']=='garden'
    before=repo._data.copy()
    replay=store.resolve_council(session['id'],'winners',[a['id'] for a in session['participants']],session['population_fingerprint'])
    assert replay['status']=='agreed'


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
