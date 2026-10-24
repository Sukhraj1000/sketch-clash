"""Controlled provider fixtures: prove budgets/authority, not personality quality."""
import asyncio,json
from copy import deepcopy
from types import SimpleNamespace
import pytest
from app.config import Settings
from app.repository import MemoryRepository,StoreError
from app.island_planner import IslandPlanner,LIMITS,MODEL

class Clock:
    def __init__(self):self.value=1792790000.0
    def __call__(self):return self.value
    def add(self,seconds):self.value+=seconds
class Island:
    def __init__(self):
        self.enabled=True;self.paused=False;self.applied={};self.failure=None
        self.agents=[{'character_id':f'agent-{i}','object_type':'bottle' if i else 'mug','allowed_actions':['forage','carry','rest'],
            'capabilities':['carry'],'persona':{'role':'Carrier'},'memories':[{'id':f'event-{i}','text':'Carried real simulated supplies.'}]} for i in range(2)]
    def snapshot(self):return {'enabled':self.enabled,'paused':self.paused,'agents':deepcopy(self.agents),'resources':{'materials':2},'active_project_id':'garden','projects':[{'id':'garden','progress':0}]}
    def set_persona(self,cid,persona,provenance):
        if self.failure==cid:self.failure=None;raise StoreError('Fixture write temporarily unavailable.',503)
        if self.applied.get(cid,{}).get('provenance',{}).get('run_id')==provenance['run_id']:return
        self.applied[cid]={'persona':persona,'provenance':provenance}
class Response:
    def __init__(self,agents):self.output_text=json.dumps({'agents':agents})
    def model_dump(self,**kw):return {'id':'fixture-interaction','model':MODEL,'model_version':'fixture','usage':{'total_tokens':321}}
class Provider:
    def __init__(self):self.calls=[];self.error=None;self.bad_action=False;self.invented_event=False;self.aio=SimpleNamespace(interactions=SimpleNamespace(create=self.create))
    async def create(self,**kw):
        self.calls.append(kw)
        if self.error:raise self.error
        data=json.loads(kw['input'])
        return Response([{'character_id':a['character_id'],'role':'Helpful carrier','temperament':'Steady and friendly',
            'motto':'One useful trip at a time.','goal':'Help the garden take shape.','preferred_action':'mint_money' if self.bad_action else 'carry',
            'lesson':'I learned from carrying supplies.','basis_event_ids':['invented'] if self.invented_event else [a['recent_events'][0]['id']]} for a in data['agents']])
@pytest.fixture
def fixture():
    settings=Settings(repository='memory',gemini_api_key='controlled-fixture-key')
    repo=MemoryRepository(settings);island=Island();provider=Provider();clock=Clock()
    return repo,island,provider,clock,IslandPlanner(repo,island,settings,provider,clock)

@pytest.mark.asyncio
async def test_plans_are_persistent_bounded_and_idempotent(fixture):
    repo,island,provider,clock,planner=fixture
    before=deepcopy(repo._data)
    assert planner.status()['requests_today']==0 and repo._data==before
    run=planner.request('one');assert run['status']=='queued' and planner.status()['requests_today']==0
    await planner.run(run['id'])
    assert len(provider.calls)==1 and len(island.applied)==2
    assert planner.status()['last_status']=='completed' and planner.status()['reported_tokens']==321
    assert planner.status()['reserved_tokens']==LIMITS['tokens_per_request']
    assert planner.request('one')['status']=='completed'
    await planner.run(run['id']);assert len(provider.calls)==1
    with pytest.raises(StoreError) as cooldown:planner.request('two')
    assert cooldown.value.code=='planner_cooldown'
    call=provider.calls[0]
    assert call['model']==MODEL and call['store'] is False
    assert call['generation_config']=={'thinking_level':'low','max_output_tokens':2048}
    assert call['response_format']['mime_type']=='application/json'
    assert 'controlled-fixture-key' not in json.dumps(call)
    assert set(repo._data.get('battles', {})) == set(before.get('battles', {}))

@pytest.mark.asyncio
@pytest.mark.parametrize('bad_field',['bad_action','invented_event'])
async def test_model_cannot_grant_actions_or_invent_memories(fixture,bad_field):
    _,island,provider,_,planner=fixture;setattr(provider,bad_field,True)
    run=planner.request('invalid');await planner.run(run['id'])
    assert island.applied=={} and planner.status()['last_status']=='failed'
    assert planner.status()['auto_blocked'] and planner.status()['requests_today']==1
    assert planner.status()['reported_tokens']==321

@pytest.mark.asyncio
async def test_unknown_outcomes_reserve_budget_and_do_not_repeat(fixture):
    _,island,provider,_,planner=fixture;provider.error=TimeoutError()
    run=planner.request('timeout');await planner.run(run['id']);await planner.run(run['id'])
    assert planner.status()['uncertain'] and planner.status()['auto_blocked']
    assert planner.status()['reserved_tokens']==7000 and len(provider.calls)==1 and not island.applied

@pytest.mark.asyncio
async def test_daily_budget_and_switch_are_enforced_before_calls(fixture):
    _,_,provider,clock,planner=fixture
    for i in range(12):
        run=planner.request('daily-'+str(i));await planner.run(run['id']);clock.add(61)
    with pytest.raises(StoreError) as limit:planner.request('over-limit')
    assert limit.value.code=='planner_daily_limit' and len(provider.calls)==12
    planner.toggle(False);clock.add(86400)
    with pytest.raises(StoreError) as disabled:planner.request('disabled')
    assert disabled.value.code=='planner_disabled'
    planner.toggle(True);run=planner.request('next-day');await planner.run(run['id'])
    assert planner.status()['requests_today']==1 and len(provider.calls)==13

@pytest.mark.asyncio
async def test_validated_partial_apply_recovers_without_second_model_call(fixture):
    repo,island,provider,_,planner=fixture;island.failure='agent-1'
    run=planner.request('partial');await planner.run(run['id'])
    stored=repo.read(lambda tx:tx.get('islandReasoning',run['id']))
    assert stored['status']=='applying' and len(island.applied)==1
    await planner.run(run['id'])
    assert len(provider.calls)==1 and len(island.applied)==2 and planner.status()['last_status']=='completed'

@pytest.mark.asyncio
async def test_pause_before_claim_spends_no_model_request(fixture):
    _,island,provider,_,planner=fixture
    run=planner.request('paused');island.paused=True;await planner.run(run['id'])
    assert not provider.calls and planner.status()['requests_today']==0
    assert planner.status()['last_status']=='failed'

@pytest.mark.asyncio
async def test_restart_marks_unknown_inflight_and_does_not_resubmit(fixture):
    repo,_,provider,_,planner=fixture
    run=planner.request('interrupted')
    def change(tx):
        row=tx.get('islandReasoning',run['id']);row['status']='running';tx.put('islandReasoning',row)
    repo.transaction(change)
    await planner.start();await asyncio.sleep(.01);await planner.close()
    assert planner.status()['uncertain'] and not provider.calls


def real_island_fixture(types=('mug', 'bottle')):
    """A real repository/engine with explicitly fabricated local fixture residents."""
    from datetime import datetime, timezone
    from app.island import IslandStore
    from app.repository import key_for

    clock = Clock()
    settings = Settings(repository='memory', world_id='fixture-real-planner', gemini_api_key='controlled-fixture-key')
    repo = MemoryRepository(settings, lambda: datetime.fromtimestamp(clock(), timezone.utc).isoformat())

    def seed(tx):
        for index, object_type in enumerate(types):
            character_id = key_for(repo.world_id, object_type)[:32]
            tx.put('worldCharacters', {
                '_id': character_id, 'id': character_id, 'world_id': repo.world_id,
                'canonical_type_id': object_type, 'object_type': object_type,
                'display_name': f'Fixture {object_type}', 'unlocked_at': repo.clock(),
                'home_position': {'x': index % 3 - 1, 'y': 0, 'z': 0},
                'visual_spec': {'template_id': object_type, 'palette': ['#3377AA']},
                'state': {'activity': 'wander', 'mood': 'curious'}, 'distinct_battle_count': 1,
            })
    repo.transaction(seed)
    island = IslandStore(repo)
    island.initialize()
    clock.add(60)
    island.advance()
    return settings, repo, island, clock


@pytest.mark.asyncio
async def test_real_island_applies_missing_model_version_and_replay_spends_once():
    settings, repo, island, clock = real_island_fixture()

    class ResponseWithoutVersion(Response):
        def model_dump(self, **kwargs):
            return {'id': 'fixture-no-version', 'model': MODEL, 'usage': {'total_tokens': 321}}

    class RealProvider(Provider):
        async def create(self, **kwargs):
            self.calls.append(kwargs)
            supplied = json.loads(kwargs['input'])
            return ResponseWithoutVersion([
                {'character_id': agent['character_id'], 'role': 'Thoughtful builder',
                 'temperament': 'Patient and helpful', 'motto': 'One useful job at a time.',
                 'goal': 'Help build the island’s current project.', 'preferred_action': 'build',
                 'lesson': 'Supplies and teamwork help our project progress.',
                 'basis_event_ids': [agent['recent_events'][-1]['id']]}
                for agent in supplied['agents']
            ])

    provider = RealProvider()
    planner = IslandPlanner(repo, island, settings, provider, clock)
    before = island.snapshot()
    original_characters = deepcopy(repo._data['worldCharacters'])
    run = planner.request('real-island-no-version')
    await planner.run(run['id'])
    after = island.snapshot()
    assert planner.status()['last_status'] == 'completed'
    assert len(provider.calls) == 1
    assert len(after['agents']) == 2
    for old, updated in zip(before['agents'], after['agents']):
        assert updated['persona']['preferred_action'] == 'build'
        assert updated['persona_provenance']['run_id'] == run['id']
        assert 'model_version' not in updated['persona_provenance']
        assert updated['allowed_actions'] == old['allowed_actions']
        assert updated['capabilities'] == old['capabilities']
        assert updated['task'] == old['task']
        assert updated['xp'] == old['xp'] and updated['level'] == old['level']
        assert len([memory for memory in updated['memory'] if memory['kind'] == 'reflection']) == 1
    assert after['resources'] == before['resources']
    assert after['projects'] == before['projects']
    assert repo._data['worldCharacters'] == original_characters
    assert planner.status()['requests_today'] == 1
    assert planner.status()['reserved_tokens'] == LIMITS['tokens_per_request']
    assert planner.status()['reported_tokens'] == 321

    # Simulate a restart after applying every persona but before recording job completion.
    def incomplete_finish(tx):
        stored = tx.get('islandReasoning', run['id'])
        stored['status'] = 'applying'
        tx.put('islandReasoning', stored)
        state = tx.get('islandPlanner', planner.state_id)
        state.update(last_status='applying', pending_run_id=run['id'])
        tx.put('islandPlanner', state)
    repo.transaction(incomplete_finish)
    recovered = IslandPlanner(repo, island, settings, provider, clock)
    await recovered.run(run['id'])
    assert recovered.request('real-island-no-version')['status'] == 'completed'
    await recovered.run(run['id'])
    assert island.snapshot() == after
    assert len(provider.calls) == 1
    assert recovered.status()['requests_today'] == 1
    assert recovered.status()['reserved_tokens'] == LIMITS['tokens_per_request']
    assert recovered.status()['reported_tokens'] == 321


def test_real_six_resident_context_is_bounded_and_excludes_reflection_memories():
    from app.island_planner import SYSTEM

    settings, repo, island, clock = real_island_fixture(('mug', 'bottle', 'pencil', 'ruler', 'phone', 'plant'))

    def long_histories(tx):
        for agent in island._agents(tx):
            agent['persona'].update(role='Fixture role ' * 5, temperament='Careful and friendly. ' * 7,
                                    motto='We help our island grow. ' * 8, goal='Build our next shared project. ' * 8)
            agent['memory'] = [
                {'id': f"fixture-{agent['character_id']}-{index:02}", 'at': repo.clock(),
                 'kind': 'reflection' if index % 2 else 'forage',
                 'text': ('MODEL-ONLY-REFLECTION ' if index % 2 else 'Fixture supply delivery. ') * 20}
                for index in range(20)
            ]
            tx.put('islandAgents', agent)
    repo.transaction(long_histories)
    provider = Provider()
    planner = IslandPlanner(repo, island, settings, provider, clock)
    run = planner.request('six-resident-bounded-context')
    payload, encoded = planner._input(run)
    snapshot = island.snapshot()
    assert len(payload['agents']) == 6
    assert len(encoded) + len(SYSTEM) <= LIMITS['input_characters']
    assert 'MODEL-ONLY-REFLECTION' not in encoded
    assert 'controlled-fixture-key' not in encoded
    assert payload['resources'] == snapshot['resources']
    active_project = next(project for project in snapshot['projects'] if project['id'] == snapshot['active_project_id'])
    assert all(value == active_project[key] for key, value in payload['project'].items())
    for agent in payload['agents']:
        # The large batch exercises shrinking while preserving each newest real event.
        assert len(agent['recent_events']) == 1
        assert agent['recent_events'][0]['kind'] == 'forage'
        assert agent['recent_events'][0]['id'] == f"fixture-{agent['character_id']}-18"
        assert set(agent['persona']) == {'role', 'motto'}
    assert not provider.calls
    assert planner.status()['requests_today'] == 0
    assert planner.status()['reserved_tokens'] == 0
