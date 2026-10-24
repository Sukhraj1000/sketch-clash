"""Connected demo contract checks, with no network or user's saved-world writes.

Real services/executor and memory transactions are used. YOLO, OCR and Gemini
responses are explicit controlled fixtures, not a recognition-quality claim.
Camera battles use accepted-evidence attribute combat; the fixture arena remains
separate and cannot unlock residents.
"""
from copy import deepcopy
import json
from types import SimpleNamespace

import pytest

from app.arena import ArenaStore
from app.colonies import ColoniesStore
from app.colony_experiments import BENEFITS
from app.colony_planner import ColonyPlanner
from app.config import Settings
from app.engine import PRESETS
from app.combat_v2 import ENGINE_VERSION
from app.recognition import RecognitionService
from app.repository import MemoryRepository, StoreError
from app.service import BattleService
from test_colonies import Clock, side
from test_provider_queue import queue_with_advancing_clock
from test_recognition import FakeClient, FakeEvidence, jpeg, proposal


def recognized(kind, features):
    template = kind if kind in {'mug', 'bottle', 'book', 'plant'} else 'generic'
    value = proposal(canonical_type_candidate=kind, proposed_label=kind,
                     display_name='Controlled ' + kind, visible_features=features,
                     archetype='Guard', stats=deepcopy(PRESETS['Guard']))
    value['visual_spec']['template_id'] = template
    return value


class CouncilFixture:
    """Scripted responses consume real observation IDs, never manufacture them."""
    def __init__(self):
        self.calls = []
        self.idle_only = False
        self.aio = SimpleNamespace(interactions=SimpleNamespace(create=self.create))

    async def create(self, **kwargs):
        payload = json.loads(kwargs['input'])
        self.calls.append(deepcopy(payload))
        options = payload['work_opportunities']
        actor = payload['actor']
        project = next((p for p in payload['projects']
                        if p.get('kind') == 'assembly' and
                        p.get('benefit', {}).get('resource') == 'water' and
                        p['level'] < p['max_level']), None)
        tests = [p for p in options['research_options'] if p['family'] == 'contain']
        designs = [p for p in options['tested_designs'] if p['family'] == 'contain']
        if self.idle_only:
            decision = {'action': 'rest', 'message': {'kind': 'reflection',
                'text': 'Our current jobs are complete; the beacon needs an energy courier.'}}
        elif project:
            decision = {'message': {'kind': 'support' if any(
                m.get('project_id') == project['id'] for m in payload['council_session']['conversation']) else 'proposal',
                'project_id': project['id'], 'text': 'Build the tested vessel to improve our water deliveries.'}}
        elif designs:
            design = designs[0]
            decision = {'reason': 'The completed test supports a useful water-delivery design.',
                'blueprint': {'name': 'Tested shared water vessel',
                    'purpose': 'Improve this crew water deliveries using the tested containment arrangement.',
                    'family': 'contain', 'parts': design['tested_parts'],
                    'experiment_id': design['experiment_id'], 'position': options['free_sites'][0]},
                'message': {'kind': 'reflection', 'text': 'The test passed; I am submitting its vessel design for crew review.'}}
        elif tests:
            decision = {'reason': 'We cannot supply the beacon energy. Test a useful water improvement instead.',
                'experiment': {'family': 'contain', 'subject_ids': [actor['character_id']],
                    'hypothesis': 'My declared simulation vessel can retain water across the normal delivery route.',
                    'expected_success': True, 'context': tests[0]['context']},
                'message': {'kind': 'reflection', 'text': 'I will test containment before claiming it improves our water deliveries.'}}
        else:
            decision = {'message': {'kind': 'reflection',
                'text': 'I am waiting for our container test and a verified design before proposing a build.'}}
        return SimpleNamespace(output_text=json.dumps(decision), model_dump=lambda **kw: {
            'usage': {'total_tokens': 40}, 'model_version': 'controlled-offline-fixture'})


def seed_mature_condition(store, clock):
    """Only fixture setup: mimic the user's full stores and completed old work.

    This setup is not credited as actual construction. New containment research,
    agreement, construction and its following output below use the real executor.
    """
    for island in store.islands.values():
        def change(tx):
            state = tx.get('islandState', island.state_id)
            # Materials/ideas are full; water is far above the automatic
            # reserve, with room for one explicit post-build verification task.
            state['resources'] = {'materials': 1000, 'water': 990, 'ideas': 1000, 'energy': 0}
            for project in state['projects']:
                if project['id'] != 'beacon':
                    project.update(level=project['max_level'], status='complete', reserved_progress=0, workers=[])
            for index, family in enumerate(('hold', 'support')):
                complete = deepcopy(state['projects'][0])
                complete.update(id='fixture-old-' + family, kind='assembly', level=1, max_level=1,
                    status='complete', benefit=deepcopy(BENEFITS[family]), position={'x': index - 1, 'z': 2})
                state['projects'].append(complete)
            for actor in island._agents(tx):
                island._schedule(state, actor, clock.value)
                assert actor['task']['kind'] == 'rest'
                tx.put('islandAgents', actor)
            tx.put('islandState', state)
        island.repo.transaction(change)


@pytest.mark.asyncio
async def test_capture_correction_battle_two_crews_research_build_receipts_wait_and_arrival(monkeypatch):
    clock = Clock()
    settings = Settings(repository='memory', world_id='isolated-connected-demo', gemini_api_key='fixture-not-a-key')
    repo = MemoryRepository(settings, clock)
    evidence = FakeEvidence()
    recognizer_client = FakeClient([
        recognized('mug', ['blue rounded body']),  # Reviewed factual error.
        recognized('bottle', ['blue rounded body']),
        recognized('mug', ['white rounded body']),
        recognized('pencil', ['long narrow wooden body']),
        recognized('book', ['rectangular paper cover']),
        recognized('battery', ['rectangular metal casing']),
        recognized('plant', ['green leaves']),
    ])
    recognition = RecognitionService(settings, evidence_runner=evidence, client=recognizer_client)
    service = BattleService(settings, repo, recognition)
    monkeypatch.setattr('app.repository.secrets.randbelow', lambda _: 0)

    async def capture_battle(request, correct=False):
        battle = repo.create_battle(request)
        assert repo.create_battle(request) == battle
        for slot in (0, 1):
            obs = await service.submit_capture(battle['id'], request + '-' + str(slot), slot,
                                               'upload', jpeg(), 'image/jpeg')
            assert obs['status'] == 'recognized', obs['evidence']
            assert obs['evidence']['detector']['coordinate_space'] == 'selected_region'
            assert obs['evidence']['ocr']['status'] == 'empty'
            assert obs['evidence']['gemini']['status'] == 'completed'
            if slot == 0 and correct:
                original = deepcopy(obs)
                body = {'idempotency_key': request + '-correction', 'kind': 'factual',
                    'output_id': obs['output_id'], 'pipeline_version_id': obs['pipeline_version_id'],
                    'canonical_label': 'bottle', 'details': 'Review the bottle neck; the first proposed label was incorrect.'}
                obs = await service.correct_capture(battle['id'], obs['capture_id'], body)
                calls = len(recognizer_client.calls)
                assert await service.correct_capture(battle['id'], original['capture_id'], body) == obs
                assert len(recognizer_client.calls) == calls
                assert obs['pending_fighter']['canonical_type_id'] == 'bottle'
                assert obs['parent_output_id'] == original['output_id']
                assert repo.get_capture(battle['id'], original['capture_id'])['observation'] == original
            repo.confirm_capture(battle['id'], slot, obs['capture_id'])
        started = repo.start_battle(battle['id'], 'quick')
        assert started['engine_version'] == ENGINE_VERSION == 'object-combat-2'
        assert started['combat']['counterfactual']['without_price']['changed_winner'] is False
        assert all(profile['price']['amount_gbp'] is None for profile in started['combat']['fighters'])
        assert started['combat']['events'] == started['events']
        with pytest.raises(StoreError) as early:
            repo.finalize_battle(battle['id'])
        assert early.value.code == 'playback_pending'
        clock.advance(7)
        complete = repo.finalize_battle(battle['id'])
        before = deepcopy(repo._data)
        assert repo.finalize_battle(battle['id']) == complete
        assert repo._data == before  # No duplicate routing/rewards.
        return complete

    first = await capture_battle('containers', correct=True)
    second = await capture_battle('planners')
    assert len(recognizer_client.calls) == len(evidence.detector_images) == len(evidence.ocr_images) == 5
    assert len(repo.world()['characters']) == 4
    store = ColoniesStore(repo)
    store.initialize()
    for crew_id, slot in [('winners', first['winner_slot']), ('losers', 1 - first['winner_slot'])]:
        crew = side(store, crew_id)
        assert len(crew['characters']) == len(crew['island']['agents']) == 2
        assert first['fighters'][slot]['canonical_type_id'] in {c['canonical_type_id'] for c in crew['characters']}
        assert second['fighters'][second['winner_slot'] if crew_id == 'winners' else 1 - second['winner_slot']]['canonical_type_id'] in {
            c['canonical_type_id'] for c in crew['characters']}
        container = next(d for d in crew['learning']['dossiers'] if d['object_type'] in {'bottle', 'mug'})
        assert container['simulation_properties']['apparent_cavity'] is None
        assert container['simulation_properties']['cavity_model']['status'] == 'declared_simulation_cavity'

    seed_mature_condition(store, clock)
    provider = CouncilFixture()
    worker = ColonyPlanner(repo, store, settings, client=provider, clock=lambda: clock.value.timestamp(),
        provider_queue=queue_with_advancing_clock(lambda: clock.value.timestamp(), clock.advance))
    built_ids = {}
    for crew_id in ('winners', 'losers'):
        assert side(store, crew_id)['behavior']['status'] == 'research_available'
        before_energy = side(store, crew_id)['island']['resources']['energy']
        container = next(a for a in side(store, crew_id)['island']['agents'] if 'water' in a['allowed_actions'])
        for council_number in range(3):
            worker.request(f'{crew_id}-water-{council_number}', crew_id, container['id'])
            for _ in range(6):
                run = worker.status()['active_run']
                if not run:
                    break
                await worker.run(run['id'])
                assert repo._data['colonyReasoning'][run['id']]['status'] == 'completed'
                clock.advance(3)
            if side(store, crew_id)['planning']['selected_project_id']:
                break
        crew = side(store, crew_id)
        experiment = next(e for e in crew['learning']['experiments'] if e['family'] == 'contain')
        assert experiment['result']['success'] and experiment['result']['production_validation']['eligible']
        assert experiment['evidence_status'] == 'current'
        blueprint = next(b for b in crew['learning']['blueprints'] if b['family'] == 'contain')
        project_id = blueprint['project']['id']
        assert crew['planning']['selected_project_id'] == project_id
        assert any(s['status'] == 'agreed' and s['project_id'] == project_id for s in worker.sessions(crew_id))
        assert crew['island']['resources']['energy'] == before_energy == 0
        # Time advances actual tasks. No direct project completion mutation.
        for _ in range(20):
            clock.advance(20)
            store.advance()
            project = next(p for p in side(store, crew_id)['island']['projects'] if p['id'] == project_id)
            if project['status'] == 'complete':
                break
        assert project['status'] == 'complete'
        built_ids[crew_id] = project_id
        receipts = [e for e in repo._data['islandEvents'].values() if e.get('project_id') == project_id and e.get('progress_delta', 0) > 0]
        assert receipts and sum(e['progress_delta'] for e in receipts) == blueprint['work_required']
        reports = [m for m in side(store, crew_id)['board'] if m.get('kind') == 'report' and
                   any(receipt['id'] in m.get('receipt_ids', []) for receipt in receipts)]
        assert reports and all(m['verified'] and m['origin'] == 'executor' for m in reports)
        island = store.islands[crew_id]
        current_state = repo.read(lambda tx: tx.get('islandState', island.state_id))
        watered_actor = next(a for a in side(store, crew_id)['island']['agents'] if a['id'] == container['id'])
        # Counterfactual uses the same actual state, removing only the completed
        # assembly, proving its +1 yield rather than conflating base upgrades.
        current_state['resources']['water'] = 0
        gain, earned = island._production_yield(current_state, watered_actor, 'water')
        without = deepcopy(current_state)
        without['projects'] = [p for p in without['projects'] if p['id'] != project_id]
        base, _ = island._production_yield(without, watered_actor, 'water')
        assert earned and gain['water'] == base['water'] + 1
        delivery = store.apply_decision(crew_id, watered_actor['id'], {
            'action': 'water', 'reason': 'Controlled check: execute one water delivery using the completed vessel.'},
            'verify-delivery-' + crew_id)['decision']
        clock.advance(100)
        store.advance()
        delivery_receipts = [e for e in repo._data['islandEvents'].values() if e.get('decision_id') == delivery['id']]
        assert len(delivery_receipts) == 1
        assert delivery_receipts[0]['resource_delta']['water'] == gain['water']
        assert delivery_receipts[0]['decision_origin'] == 'model'
        assert delivery_receipts[0]['decision_evidence'] == 'accepted_decision'

    # Every provider turn only sees its own crew and committed earlier dialogue.
    for payload in provider.calls:
        ids = {payload['actor']['id'], *[p['id'] for p in payload['peers']]}
        conversation = payload['council_session']['conversation']
        assert all(m['actor_id'] in ids for m in conversation)
        assert all(m['id'] in repo._data['colonyBoard'] for m in conversation)
        for message in conversation:
            saved = repo._data['colonyBoard'][message['id']]
            public_text = saved.get('interpretation') if saved['kind'] in ('proposal', 'support', 'objection') else None
            assert message['text'] == (public_text or saved['text'])

    # A clean idle review should stay quiet through task/receipt bookkeeping.
    provider.idle_only = True
    for crew_id in ('winners', 'losers'):
        clock.advance(65)
        store.advance()
        assert side(store, crew_id)['behavior']['status'] == 'waiting_for_change'
        worker.request('review-' + crew_id, crew_id)
        for _ in range(6):
            run = worker.status()['active_run']
            if not run:
                break
            await worker.run(run['id'])
            clock.advance(3)
        assert crew_id in worker.status()['reviewed_work_fingerprints']
    calls_before_idle = len(provider.calls)
    clock.advance(65)
    store.advance()
    worker_state = repo.read(lambda tx: worker._state(tx))
    assert worker._available_colonies(store.snapshot(), worker_state) == []
    assert len(provider.calls) == calls_before_idle

    # Reopening service handles retains the exact accepted saves. This checks
    # adapter state recovery, not disk/Atlas durability (covered separately).
    reopened = ColoniesStore(repo)
    assert reopened.snapshot() == store.snapshot()
    before_arrival = deepcopy(repo._data)
    arrival = await capture_battle('new-capability')
    store.advance()
    battery_side = 'winners' if arrival['fighters'][arrival['winner_slot']]['canonical_type_id'] == 'battery' else 'losers'
    crew = side(store, battery_side)
    battery = next(a for a in crew['island']['agents'] if a['object_type'] == 'battery')
    assert 'charge' in battery['allowed_actions'] and battery['action_yields']['charge'] == {'energy': 3}
    assert battery_side in [c['id'] for c in worker._available_colonies(store.snapshot(), worker_state)]
    assert 'energy' not in crew['behavior']['missing_capabilities']
    for identifier, record in before_arrival.get('colonyExperiments', {}).items():
        assert repo._data['colonyExperiments'][identifier] == record
    assert len(repo.world()['characters']) == 6
    assert len(recognizer_client.calls) == len(evidence.detector_images) == len(evidence.ocr_images) == 7
    assert all(next(p for p in side(store, c)['island']['projects'] if p['id'] == pid)['status'] == 'complete'
               for c, pid in built_ids.items())


def test_attribute_price_conditional_arena_remains_separate_from_camera_rewards():
    repo = MemoryRepository(Settings(repository='memory', world_id='isolated-attribute-demo', ai_paused=True))
    before = deepcopy(repo._data)
    arena = ArenaStore(repo)
    match = arena.create('conditional-match', ['filled-water-jug', 'hardback-book'])
    assert match['source'] == 'local_fixture' and match['island_rewards'] is False
    assert match['counterfactual'] and match['explanation']['summary']
    assert any(r['id'] == 'splash-absorbent' for e in match['events'] for r in e['receipt']['interaction_rules'])
    assert all(0 <= e['receipt']['price_percent'] <= 1 for e in match['events'])
    assert arena.create('conditional-match', ['filled-water-jug', 'hardback-book']) == match
    assert {k: v for k, v in repo._data.items() if k != 'arenaBattles'} == before
