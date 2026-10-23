"""Engineering fixtures only: controlled labels, providers, preferences and render reports.

These tests establish isolation and lifecycle contracts, not real user evidence.
"""
from copy import deepcopy
from hashlib import sha256
from io import BytesIO
import asyncio
import json
import random
import time
from types import SimpleNamespace

import pytest
from PIL import Image

from app.config import Settings
from app.engine import PRESETS
from app.images import normalize_image
from app.pipeline import BASELINE_CONFIG, BASELINE_VERSION, active_key, version_key
from app.quality import QualityStore, POLICY, inference_payload, score_outcome, technical_check
from app.quality_jobs import QualityWorker, JobBudget, BudgetExceeded, JobCancelled
from app.repository import MemoryRepository, StoreError, key_for


def image_bytes(seed=1):
    rng = random.Random(seed)
    im = Image.new('RGB', (80, 80))
    im.putdata([(rng.randrange(256), rng.randrange(256), rng.randrange(256)) for _ in range(6400)])
    out = BytesIO()
    im.save(out, 'JPEG')
    return out.getvalue()


def fighter(kind='mug'):
    return {'battle_id': 'evaluation', 'player_slot': 0, 'capture_id': 'fixture',
        'image_hash': 'a'*64, 'image_ref': '/api/media/'+'a'*64,
        'canonical_type_id': kind, 'object_type': kind, 'display_name': 'Engineering fixture',
        'archetype': 'Quick', 'stats': deepcopy(PRESETS['Quick']),
        'visual_spec': {'template_id': 'mug' if kind == 'mug' else 'bottle', 'palette': ['#FF0000'], 'scale': 1,
            'proportions': {'width': 1, 'height': 1}, 'accessories': ['eyes'], 'animation_style': 'calm',
            'schema_version': '1', 'appearance_seed': 7}}


@pytest.fixture
def state():
    settings = Settings(repository='memory')
    repo = MemoryRepository(settings)
    return repo, QualityStore(repo), settings


def seed_feedback(repo, name='feedback', *, consent=True, close=True, seed=1, battle=None):
    battle = battle or repo.create_battle(name)
    image = normalize_image(image_bytes(seed), 'image/jpeg', repo.settings)
    repo.save_media(image)
    capture = {'capture_id': name, 'player_slot': 0, 'source': 'upload', 'image_hash': image.image_hash,
        'image_ref': image.image_ref, 'canonical_media_id': image.image_hash, 'width': image.width,
        'height': image.height, 'crop': None}
    repo.begin_capture(battle['id'], capture)
    observation = {**capture, 'status': 'recognized', 'output_id': 'out-'+name,
        'pipeline_version_id': battle['pipeline_version_id'], 'pending_fighter': fighter()}
    observation.pop('player_slot'); observation.pop('canonical_media_id')
    repo.finish_capture(battle['id'], name, observation)
    feedback = repo.submit_feedback(battle['id'], name, {
        'idempotency_key': name, 'output_id': 'out-'+name, 'pipeline_version_id': battle['pipeline_version_id'],
        'recognition_verdict': 'correct', 'creative_verdict': 'skipped', 'shared_consent': consent})
    if close: repo.cancel_battle(battle['id'])
    return feedback, battle


def review_body(feedback, **extra):
    return {'feedback_id': feedback['id'], 'expected_revision': 0, 'decision': 'approved',
        'expected_identity': 'coffee mug', 'clarification_required': False,
        'group_id': 'object-session-one', 'role': 'development', 'reviewer': 'Fixture operator',
        'reason': 'Synthetic engineering fixture, not real review evidence.', 'shared_consent': True, **extra}


def seed_case(repo, name, role='development', *, group=None, seed=1, consent=True, status='approved', expected='mug'):
    image = normalize_image(image_bytes(seed), 'image/jpeg', repo.settings)
    repo.save_media(image)
    case = {'_id': name, 'id': name, 'world_id': repo.world_id, 'revision': 1,
        'image_ref': image.image_ref, 'image_hash': image.image_hash, 'width': image.width, 'height': image.height,
        'crop': None, 'expected': {'canonical_type_id': expected, 'clarification_required': False},
        'visible_attributes': ['handle'], 'group_id': group or 'group-'+name, 'session_group': 'session-'+name,
        'role': role, 'review_status': status, 'shared_consent': consent,
        'provenance': {'reviewer': 'Synthetic test fixture', 'reason': 'Not human evaluation evidence.'},
        'created_at': repo.clock(), 'inclusion_reason': 'Controlled engineering fixture'}
    repo.transaction(lambda tx: tx.put('qualityCases', case))
    return case


def create_job(store, kind='baseline', key='job', **extra):
    return store.create_job({'idempotency_key': key, 'kind': kind, 'scope': 'recognition', 'max_requests': 60, **extra})


def test_review_requires_player_consent_and_waits_for_closed_round(state):
    repo, store, _ = state
    feedback, battle = seed_feedback(repo, consent=False, close=False)
    assert store.overview()['queue'] == []
    with pytest.raises(StoreError) as private:
        store.review(review_body(feedback))
    assert private.value.code == 'private_round'
    repo.cancel_battle(battle['id'])
    assert len(store.overview()['queue']) == 1
    with pytest.raises(StoreError) as no_consent:
        store.review(review_body(feedback))
    assert no_consent.value.code == 'consent_required'
    result = store.review(review_body(feedback, shared_consent=False))
    assert result['case']['expected']['canonical_type_id'] == 'mug'
    assert not store.eligible(result['case'])
    assert store.overview()['readiness']['reviewed'] == 0
    assert store.export()['cases'] == []


def test_review_grouping_blocks_duplicate_or_session_leakage_and_preserves_disagreement(state):
    repo, store, _ = state
    first, _ = seed_feedback(repo, 'first', seed=1)
    reviewed = store.review(review_body(first))
    second, _ = seed_feedback(repo, 'second', seed=1)
    with pytest.raises(StoreError) as duplicate:
        store.review(review_body(second, group_id='different-physical-object'))
    assert duplicate.value.code == 'group_conflict'
    with pytest.raises(StoreError) as role:
        store.review(review_body(second, role='reserved'))
    assert role.value.code == 'dataset_leakage'
    disputed = store.review(review_body(first, expected_revision=1, expected_identity='bottle'))
    assert disputed['case']['review_status'] == 'disputed'
    assert not store.eligible(disputed['case'])
    assert len(repo._data['qualityReviews']) == 2
    assert len(repo._data['qualityCaseRevisions']) == 2
    with pytest.raises(StoreError) as stale:
        store.review(review_body(first, expected_revision=1))
    assert stale.value.code == 'stale_review'
    assert reviewed['case']['expected']['canonical_type_id'] == 'mug'


def test_snapshot_freezes_reviewed_roles_and_inference_never_contains_answers(state):
    repo, store, _ = state
    case = seed_case(repo, 'dev', seed=2)
    seed_case(repo, 'reference', 'reference', seed=3)
    seed_case(repo, 'reserved', 'reserved', seed=4, expected='heldout-answer')
    seed_case(repo, 'disputed', 'reference', seed=5, status='disputed')
    seed_case(repo, 'private', 'development', seed=6, consent=False)
    job = create_job(store)
    frozen = store.job(job['id'])
    assert [c['id'] for c in frozen['snapshot']['cases']] == ['dev']
    assert [c['id'] for c in frozen['snapshot']['references']] == ['reference']
    before = deepcopy(frozen['snapshot'])
    repo._data['qualityCases']['dev']['expected']['canonical_type_id'] = 'changed-after-freeze'
    assert store.job(job['id'])['snapshot'] == before
    leaked = {**case, 'filename': 'mug-the-answer.jpg', 'comment': 'expected mug', 'previous_output': fighter()}
    payload = inference_payload(leaked)
    assert set(payload) == {'image_ref', 'image_hash', 'width', 'height'}
    assert 'mug' not in json.dumps(payload)
    assert create_job(store)['id'] == job['id']


def test_factual_scoring_separates_coverage_from_clarification_and_has_no_creative_score():
    expected = {'canonical_type_id': 'coffee mug', 'clarification_required': False}
    correct = score_outcome(expected, {'status': 'recognized', 'pending_fighter': fighter('mug')})
    assert correct == {'correct_identity': 1, 'wrong_accepted': 0, 'appropriate_clarification': 0,
        'unnecessary_clarification': 0, 'answered': 1, 'total': 1}
    wrong = score_outcome(expected, {'status': 'recognized', 'pending_fighter': fighter('bottle')})
    assert wrong['wrong_accepted'] == 1 and wrong['answered'] == 1
    abstain = score_outcome(expected, {'status': 'needs_recapture'})
    assert abstain['unnecessary_clarification'] == 1 and abstain['answered'] == 0
    unclear = score_outcome({'clarification_required': True}, {'status': 'needs_selection'})
    assert unclear['appropriate_clarification'] == 1
    broken = fighter(); broken['stats']['health'] = 500
    assert technical_check({'pending_fighter': broken})['valid'] is False


class FakeRecognizer:
    calls = []
    async def recognize_capture(self, data, **kwargs):
        type(self).calls.append({'kwargs': {k: (v if k == 'request_budget' else deepcopy(v)) for k, v in kwargs.items()}, 'image_hash': sha256(data).hexdigest()})
        return {'status': 'recognized', 'proposed_label': 'mug', 'pending_fighter': fighter(),
            'observed_object': {'canonical_type_id': 'mug'}, 'evidence': {'gemini': {'status': 'completed'}}}
    async def close(self): pass


@pytest.mark.asyncio
async def test_worker_isolates_each_case_and_cannot_mutate_live_world(state, monkeypatch):
    repo, store, settings = state
    case = seed_case(repo, 'development', seed=1)
    seed_case(repo, 'approved-reference', 'reference', seed=2)
    seed_case(repo, 'unreviewed-reference', 'reference', seed=3, status='unreviewed')
    seed_case(repo, 'heldout', 'reserved', seed=4, expected='do-not-expose')
    live = repo.create_battle('live-round-stays-pinned')
    before = {k: deepcopy(repo._data.get(k, {})) for k in ('battles', 'worlds', 'worldCharacters', 'encounters')}
    job = create_job(store)
    FakeRecognizer.calls = []
    retrieval_calls = []
    class ControlledReferences:
        available = True
        def __init__(self, *args): pass
        async def retrieve(self, image_hash, limit, *, exclude_groups, budget, snapshot):
            retrieval_calls.append({'image_hash': image_hash, 'limit': limit, 'exclude_groups': exclude_groups, 'snapshot': snapshot})
            assert isinstance(budget, JobBudget)
            assert exclude_groups == [case['group_id']]
            assert [reference['id'] for reference in snapshot] == ['approved-reference']
            ref = snapshot[0]
            return [{'id': ref['id'], 'image_bytes': repo.get_media(ref['image_hash'])['data'],
                     'label': ref['expected']['canonical_type_id'], 'visible_features': ref['visible_attributes'], 'provenance': ref['provenance']}]
        async def close(self): pass
    monkeypatch.setattr('app.quality_references.ApprovedReferences', ControlledReferences)
    worker = QualityWorker(store, settings, recognizer_factory=FakeRecognizer)
    await worker.evaluate(job['id'], case, 'baseline', BASELINE_VERSION, {**BASELINE_CONFIG, 'reference_limit': 3}, JobBudget(store, job['id']))
    assert len(retrieval_calls) == 1
    assert len(FakeRecognizer.calls) == 1
    supplied = FakeRecognizer.calls[0]['kwargs']
    assert supplied['persist_catalog'] is False
    assert supplied['capture_id'].startswith('evaluation-')
    assert 'expected' not in supplied and 'reviewer' not in supplied
    assert [r['id'] for r in supplied['references']] == ['approved-reference']
    assert 'do-not-expose' not in repr({k: v for k, v in supplied.items() if k != 'request_budget'})
    assert repo.get_battle(live['id'])['pipeline_version_id'] == BASELINE_VERSION
    assert {k: repo._data.get(k, {}) for k in before} == before
    await worker.evaluate(job['id'], case, 'baseline', BASELINE_VERSION, BASELINE_CONFIG, JobBudget(store, job['id']))
    assert len(FakeRecognizer.calls) == 1
    assert len(store.results(job['id'])) == 1


@pytest.mark.asyncio
async def test_budget_reserves_unknown_requests_cancellation_and_restart_are_honest(state):
    repo, store, settings = state
    seed_case(repo, 'development')
    job = create_job(store)
    store.mutate_job(job['id'], lambda j: j['budget'].update(max_requests=1, max_tokens=5000))
    budget = JobBudget(store, job['id'])
    reservation = await budget.reserve(input_tokens=1000, output_tokens=1000, kind='fixture')
    assert store.job(job['id'])['inflight']['outcome'] == 'unknown_until_response'
    with pytest.raises(BudgetExceeded):
        await budget.reserve(input_tokens=1000, output_tokens=1000, kind='duplicate')
    assert store.job(job['id'])['budget']['requests'] == 1
    assert store.job(job['id'])['budget']['reserved_tokens'] == 2000
    store.mutate_job(job['id'], lambda j: j.update(status='running'))
    worker = QualityWorker(store, settings, recognizer_factory=FakeRecognizer)
    await worker.start()
    await worker.close()
    assert store.job(job['id'])['status'] == 'interrupted'
    assert store.job(job['id'])['budget']['requests'] == 1
    store.mutate_job(job['id'], lambda j: j.update(cancel_requested=True))
    with pytest.raises(JobCancelled): await budget.check()
    with pytest.raises(JobCancelled): await budget.reserve(input_tokens=1, output_tokens=1, kind='cancelled')


@pytest.mark.asyncio
async def test_agent_tools_see_development_only_and_cannot_approve_or_edit_truth(state):
    repo, store, settings = state
    seed_case(repo, 'dev')
    seed_case(repo, 'final', 'reserved', seed=2, expected='secret-final-identity')
    job = create_job(store, kind='candidate')
    worker = QualityWorker(store, settings, recognizer_factory=FakeRecognizer)
    budget = JobBudget(store, job['id'])
    before_cases = deepcopy(repo._data['qualityCases'])
    before_active = deepcopy(repo._data['qualityState'])
    result = await worker.agent_tool(job['id'], 'list_reviewed_development_failures', {}, budget)
    assert [case['id'] for case in result['cases']] == ['dev']
    assert 'secret-final-identity' not in repr(result)
    for forbidden in ('activate_version', 'edit_expected_answer', 'approve_candidate', 'write_code'):
        denied = await worker.agent_tool(job['id'], forbidden, {'value': 'evil'}, budget)
        assert 'not permitted' in denied['error']
    invalid = await worker.agent_tool(job['id'], 'propose_pipeline_configuration', {'config': {'stats': {'attack': 999}}, 'rationale': 'no'}, budget)
    assert 'error' in invalid
    candidate = await worker.agent_tool(job['id'], 'propose_pipeline_configuration', {
        'config': {'recognition_guidance': 'Check for the photographed handle.'}, 'rationale': 'Controlled development fixture'}, budget)
    assert candidate['frozen'] is True
    again = await worker.agent_tool(job['id'], 'propose_pipeline_configuration', {
        'config': {'recognition_guidance': 'Replace it.'}, 'rationale': 'no'}, budget)
    assert 'error' in again
    assert repo._data['qualityCases'] == before_cases
    assert repo._data['qualityState'] == before_active
    assert store.job(job['id'])['candidate_id'] == candidate['candidate_id']


def comparison_fixture(repo, store, *, scope='recognition'):
    cases = [seed_case(repo, f'{role}-{i}', role, seed=20+i+(10 if role == 'reserved' else 0))
        for role in ('development', 'reserved') for i in range(3)]
    job = create_job(store, kind='candidate', scope=scope)
    cid = 'fixture-candidate'
    repo.transaction(lambda tx: tx.put('pipelineVersions', {'_id': version_key(repo.world_id, cid), 'id': cid,
        'world_id': repo.world_id, 'job_id': job['id'], 'config': deepcopy(BASELINE_CONFIG), 'immutable': True}))
    store.mutate_job(job['id'], lambda j: j.update(candidate_id=cid, status='completed'))
    for case in cases:
        for variant in ('baseline', 'candidate'):
            wrong = variant == 'baseline' and case['id'] == 'reserved-0' and scope == 'recognition'
            obs = {'status': 'recognized', 'pending_fighter': fighter('bottle' if wrong else 'mug')}
            store.save_result(job['id'], {'case_id': case['id'], 'case_revision': 1, 'variant': variant,
                'role': case['role'], 'fighter': obs['pending_fighter'], 'prediction': {'status': 'recognized'},
                'technical': {'valid': True}, 'recognition': score_outcome(case['expected'], obs), 'latency_ms': 100,
                'render_status': 'passed', 'error': None})
    return job, cid


def test_render_failures_and_missing_human_creative_review_block_activation(state):
    repo, store, _ = state
    job, cid = comparison_fixture(repo, store, scope='appearance')
    gate = store.gates(job['id'])
    assert not gate['passing']
    assert any('human review' in r for r in gate['reasons'])
    result = store.results(job['id'])[0]
    store.render(result['id'], {'status': 'passed', 'bounds_ok': False, 'visible': True, 'states': ['idle', 'rest', 'wander'], 'errors': []})
    assert store.results(job['id'])[0]['render_status'] == 'failed'
    assert any('3D render' in r for r in store.gates(job['id'])['reasons'])
    with pytest.raises(StoreError) as blocked:
        store.activate({'version_id': cid, 'expected_active_version_id': BASELINE_VERSION, 'expected_revision': 1,
            'reviewer': 'Fixture operator', 'reason': 'Cannot approve failed fixture'})
    assert blocked.value.code == 'gates_failed'


def test_activation_and_rollback_are_atomic_and_preserve_pinned_rounds_and_residents(state):
    repo, store, _ = state
    live = repo.create_battle('in-progress')
    resident = {'_id': 'resident', 'id': 'resident', 'world_id': repo.world_id, 'canonical_type_id': 'mug',
        'visual_spec': fighter()['visual_spec'], 'home_position': {'x': 1, 'y': 0, 'z': 1}, 'distinct_battle_count': 5}
    repo.transaction(lambda tx: tx.put('worldCharacters', resident))
    before = deepcopy(repo.world())
    job, cid = comparison_fixture(repo, store)
    assert store.gates(job['id'])['passing']
    approval = {'version_id': cid, 'expected_active_version_id': BASELINE_VERSION, 'expected_revision': 1,
        'reviewer': 'Synthetic operator fixture', 'reason': 'Engineering test only'}
    active = store.activate(approval)
    assert active['active_version_id'] == cid and active['revision'] == 2
    with pytest.raises(StoreError) as stale: store.activate(approval)
    assert stale.value.code == 'stale_activation'
    assert repo.create_battle('future')['pipeline_version_id'] == cid
    assert repo.get_battle(live['id'])['pipeline_version_id'] == BASELINE_VERSION
    rollback = store.activate({**approval, 'version_id': BASELINE_VERSION, 'expected_active_version_id': cid, 'expected_revision': 2}, rollback=True)
    assert rollback['revision'] == 3 and rollback['active_version_id'] == BASELINE_VERSION
    assert repo.world() == before
    assert len(repo._data['qualityActivation']) == 2


def test_blinded_comparison_persists_order_and_records_human_preferences_separately(state):
    repo, store, _ = state
    job, _ = comparison_fixture(repo, store, scope='appearance')
    initial = store.comparison(job['id'])
    assert len(initial['pairs']) == 6
    assert initial['blinded'] is True
    assert store.comparison(job['id']) == initial
    by_id = {result['id']: result for result in store.results(job['id'])}
    for pair in initial['pairs']:
        assert 'variant' not in pair['left'] and 'variant' not in pair['right']
        preferred = next(side for side in ('left', 'right') if by_id[pair[side]['result_id']]['variant'] == 'candidate')
        body = {'preference': preferred, 'reviewer': 'Synthetic preference fixture',
            'reason': 'Engineering test only, not real user preference.',
            'rubric': {'resemblance': 3, 'feature_preservation': 3, 'style_fit': 3, 'appeal': 3}}
        store.compare_review(pair['id'], body)
        with pytest.raises(StoreError) as immutable: store.compare_review(pair['id'], body)
        assert immutable.value.code == 'review_exists'
    gate = store.gates(job['id'])
    assert gate['passing']
    assert gate['creative']['reviewed'] == 6
    assert gate['creative']['candidate_preferred'] == 6
    assert gate['recognition']['candidate']['correct_identity'] == 3


@pytest.mark.asyncio
async def test_reserved_groups_cannot_be_reused_after_their_outcomes_have_been_exposed(state):
    repo, store, settings = state
    seed_case(repo, 'dev')
    final = seed_case(repo, 'final', 'reserved', seed=2)
    one, two = create_job(store, kind='candidate', key='one'), create_job(store, kind='candidate', key='two')
    worker = QualityWorker(store, settings, recognizer_factory=FakeRecognizer)
    await worker.claim_reserved(one['id'], final)
    await worker.claim_reserved(one['id'], final)  # Retry the same immutable job safely.
    with pytest.raises(StoreError) as exposed:
        await worker.claim_reserved(two['id'], final)
    assert exposed.value.code == 'reserved_exposed'
    assert len(repo._data['qualityReservedUse']) == 1


@pytest.mark.asyncio
async def test_cancelled_queued_job_and_expired_budget_make_no_provider_requests(state):
    repo, store, settings = state
    seed_case(repo, 'dev')
    cancelled = create_job(store, key='cancelled')
    store.mutate_job(cancelled['id'], lambda j: j.update(cancel_requested=True))
    FakeRecognizer.calls = []
    worker = QualityWorker(store, settings, recognizer_factory=FakeRecognizer)
    await worker.run(cancelled['id'])
    assert store.job(cancelled['id'])['status'] == 'cancelled'
    assert FakeRecognizer.calls == []
    expired = create_job(store, key='expired')
    store.mutate_job(expired['id'], lambda j: j.update(deadline_at=time.time()-1))
    with pytest.raises(BudgetExceeded):
        await JobBudget(store, expired['id']).reserve(input_tokens=1, output_tokens=1, kind='too-late')
    assert store.job(expired['id'])['budget']['requests'] == 0


def test_export_omits_private_records_raw_data_and_credentials(state):
    repo, store, _ = state
    seed_case(repo, 'consented')
    seed_case(repo, 'private', seed=2, consent=False)
    seed_case(repo, 'disputed', seed=3, status='disputed')
    from app.quality import clean_document
    cleaned = clean_document({'safe': 'yes', 'GEMINI_API_KEY': 'fixture-hidden', 'mongodb_uri': 'fixture-hidden',
        'steps': [{'thought': 'fixture-hidden'}], 'data': b'photo', 'nested': {'password': 'fixture-hidden'}})
    assert cleaned == {'safe': 'yes', 'nested': {}}
    exported = store.export()
    assert [case['id'] for case in exported['cases']] == ['consented']
    assert 'raw_image' not in json.dumps(exported)


def test_gate_uses_frozen_policy_snapshot_not_later_process_defaults(state, monkeypatch):
    repo, store, _ = state
    job, _ = comparison_fixture(repo, store)
    assert store.gates(job['id'])['passing']
    monkeypatch.setitem(POLICY, 'min_final_cases', 99)
    assert store.gates(job['id'])['passing'], 'A later default must not rewrite the policy of a frozen comparison.'


def test_operator_gate_protects_review_paid_jobs_activation_rollback_and_exports(state):
    from fastapi import FastAPI, Request
    from fastapi.responses import JSONResponse
    from fastapi.testclient import TestClient
    from app.quality_api import OperatorGate, register_quality_routes
    repo, store, _ = state
    app = FastAPI()
    app.state.operator_gate = OperatorGate(token='fixture-operator-key-not-a-secret-1234')
    app.state.quality = store
    app.state.quality_worker = SimpleNamespace(wake=asyncio.Event())
    @app.exception_handler(StoreError)
    async def handle(request: Request, exc: StoreError):
        return JSONResponse({'detail': str(exc), 'code': exc.code}, status_code=exc.status)
    register_quality_routes(app)
    with TestClient(app) as client:
        for path in ('/api/quality/overview', '/api/quality/export', '/api/quality/jobs/guessed', '/api/quality/jobs/guessed/comparison'):
            assert client.get(path).status_code == 401
        for path in ('/api/quality/reviews', '/api/quality/jobs', '/api/quality/activate', '/api/quality/rollback',
                     '/api/quality/results/guessed/render', '/api/quality/comparisons/guessed'):
            assert client.post(path, json={}).status_code == 401
        assert client.post('/api/quality/session', json={'token': 'wrong-fixture-key'}).status_code == 401
        logged = client.post('/api/quality/session', json={'token': 'fixture-operator-key-not-a-secret-1234'})
        assert logged.status_code == 200
        cookie = logged.headers['set-cookie'].lower()
        assert 'httponly' in cookie and 'samesite=strict' in cookie and 'path=/api/quality' in cookie
        assert client.get('/api/quality/overview').status_code == 200
        assert client.get('/api/quality/export').status_code == 200
        # No consented cases: paid action remains a useful no-work state, with zero requests.
        job = client.post('/api/quality/jobs', json={'idempotency_key': 'no-data', 'kind': 'baseline'}).json()
        assert job['status'] == 'needs_review' and job['budget']['requests'] == 0
        assert client.delete('/api/quality/session').status_code == 200
        assert client.get('/api/quality/overview').status_code == 401
    assert repo.world()['characters'] == []


def test_operator_cookie_is_signed_expires_and_rate_limits_wrong_tokens():
    from app.quality_api import OperatorGate
    gate = OperatorGate(token='fixture-operator-key-not-a-secret-1234')
    cookie = gate.login('fixture-operator-key-not-a-secret-1234', 'fixture-address')
    assert gate.check(cookie)
    assert not gate.check(cookie[:-4]+'AAAA')
    assert not gate.check('not-valid-base64!')
    for _ in range(5):
        with pytest.raises(StoreError) as failed: gate.login('wrong', 'attacker')
        assert failed.value.status == 401
    with pytest.raises(StoreError) as limited: gate.login('wrong', 'attacker')
    assert limited.value.status == 429


@pytest.mark.asyncio
async def test_uncertain_provider_failure_preserves_reservation_and_is_never_scored_as_clarification(state):
    repo, store, settings = state
    seed_case(repo, 'dev')
    job = create_job(store)
    class FailedRecognizer:
        async def recognize_capture(self, data, **kwargs):
            await kwargs['request_budget'].reserve(input_tokens=1000, output_tokens=1000, kind='fixture-unknown')
            return {'status': 'needs_recapture', 'evidence': {'gemini': {'status': 'failed', 'error_category': 'TimeoutError'}}}
        async def close(self): pass
    worker = QualityWorker(store, settings, recognizer_factory=FailedRecognizer)
    await worker.run(job['id'])
    saved = store.job(job['id'])
    assert saved['status'] in ('failed', 'interrupted')
    assert saved['inflight'] and saved['inflight']['outcome'] == 'unknown_until_response'
    assert saved['budget']['requests'] == 1
    assert store.results(job['id']) == []
    assert store.gates(job['id'])['passing'] is False
    assert store.overview()['active']['active_version_id'] == BASELINE_VERSION


class FakeAgentClient:
    def __init__(self):
        self.calls = []
        self.aio = SimpleNamespace(interactions=SimpleNamespace(create=self.create))
        self.sequence = [
            ('list_reviewed_development_failures', {}),
            ('propose_pipeline_configuration', {'config': {'recognition_guidance': 'Inspect the handle before identifying the vessel.'}, 'rationale': 'Engineering fixture from development only'}),
            ('run_development_evaluation', {}),
            ('compare_baseline_and_candidate', {}),
            ('submit_candidate', {}),
        ]
    async def create(self, **kwargs):
        self.calls.append(deepcopy(kwargs))
        name, arguments = self.sequence.pop(0)
        return {'id': f'fixture-response-{len(self.calls)}', 'model': 'gemini-4-argon', 'model_version': 'engineering-fixture',
            'steps': [{'type': 'function_call', 'id': f'fixture-call-{len(self.calls)}', 'name': name, 'arguments': arguments}],
            'usage': {'total_tokens': 100}}


@pytest.mark.asyncio
async def test_bounded_agent_candidate_flow_runs_independent_final_service_without_self_activation(state):
    repo, store, settings = state
    for i in range(3):
        seed_case(repo, f'dev-{i}', seed=i+10)
        seed_case(repo, f'final-{i}', 'reserved', seed=i+30, expected='reserved-secret-object')
    job = create_job(store, kind='candidate')
    agent = FakeAgentClient()
    worker = QualityWorker(store, settings, recognizer_factory=FakeRecognizer, agent_client=agent)
    before = deepcopy(repo.world())
    await worker.run(job['id'])
    result = store.job(job['id'])
    assert result['status'] == 'completed'
    assert result['agent_submitted'] is True
    assert result['candidate_id'].startswith('candidate-')
    assert result['budget']['requests'] == 5
    assert result['budget']['reported_tokens'] == 500
    assert len(store.results(job['id'])) == 12
    assert len(repo._data['qualityReservedUse']) == 3
    assert all('reserved-secret-object' not in json.dumps(call) for call in agent.calls)
    assert all(call['store'] is False and call['model'] == 'gemini-4-argon' for call in agent.calls)
    assert all(call['generation_config'] == {'thinking_level': 'medium', 'max_output_tokens': 2048} for call in agent.calls)
    for call in agent.calls[1:]:
        for step in call['input']:
            if step['type'] == 'function_result':
                assert isinstance(step['result'], list) and step['result'][0]['type'] == 'text'
    assert store.gates(job['id'])['passing'] is False  # No fabricated improvement, no actual browser render review.
    assert store.overview()['active']['active_version_id'] == BASELINE_VERSION
    assert repo.world() == before


@pytest.mark.asyncio
async def test_frozen_reference_adapter_excludes_new_enrolments_and_rejects_review_drift(state):
    from app.quality_references import ApprovedReferences, COLLECTION, DIMENSIONS, visual_reference_index_definition
    repo, store, settings = state
    class Vectors:
        def __init__(self): self.pipelines = []
        def list_search_indexes(self, **kwargs):
            return [{'queryable': True, 'latestDefinition': visual_reference_index_definition()}]
        def aggregate(self, pipeline, **kwargs):
            self.pipelines.append(pipeline)
            return repo.read(lambda tx: tx.find(COLLECTION, {'world_id': repo.world_id}))
    vectors = Vectors()
    repo.db = {COLLECTION: vectors}
    requests = []
    async def embed(**kwargs):
        requests.append(kwargs)
        return SimpleNamespace(embeddings=[SimpleNamespace(values=[1.0]*DIMENSIONS)])
    client = SimpleNamespace(aio=SimpleNamespace(models=SimpleNamespace(embed_content=embed)))
    adapter = ApprovedReferences(repo, settings, client)
    class Counter:
        async def reserve(self, **kw): return kw
        async def complete(self, reservation, response): pass
    reference = seed_case(repo, 'frozen-reference', 'reference', seed=11)
    frozen = [deepcopy(reference)]
    await adapter.prepare_reference(reference['id'], Counter())
    later = seed_case(repo, 'later-reference', 'reference', seed=12)
    await adapter.prepare_reference(later['id'], Counter())
    query = seed_case(repo, 'query-case', seed=13)
    result = await adapter.retrieve(query['image_hash'], 3, exclude_groups=[query['group_id']], budget=Counter(), snapshot=frozen)
    assert [item['id'] for item in result] == ['frozen-reference']
    filters = vectors.pipelines[-1][0]['$vectorSearch']['filter']
    assert filters['case_id']['$in'] == ['frozen-reference']
    assert query['group_id'] in filters['group_id']['$nin']
    before_requests = len(requests)
    repo._data['qualityCases']['frozen-reference']['revision'] = 2
    with pytest.raises(StoreError) as changed:
        await adapter.retrieve(query['image_hash'], 3, budget=Counter(), snapshot=frozen)
    assert changed.value.code == 'stale_reference'
    assert not adapter.available and adapter.status['error_category'] == 'StoreError'
    assert len(requests) == before_requests


@pytest.mark.asyncio
async def test_reference_preparation_job_is_bounded_checkpointed_and_detects_stale_review(state, monkeypatch):
    repo, store, settings = state
    reference = seed_case(repo, 'reference', 'reference')
    seed_case(repo, 'private-reference', 'reference', seed=2, consent=False)
    with pytest.raises(StoreError) as private:
        store.create_reference_job({'idempotency_key': 'private', 'case_ids': ['private-reference']})
    assert private.value.code == 'reference_ineligible'
    body = {'idempotency_key': 'prepare', 'case_ids': [reference['id']]}
    job = store.create_reference_job(body)
    assert store.create_reference_job(body)['id'] == job['id']
    calls = []
    class ControlledPreparation:
        def __init__(self, *args): pass
        async def prepare_reference(self, case_id, budget):
            calls.append(case_id)
            reservation = await budget.reserve(input_tokens=8192, output_tokens=0, kind='visual_reference_embedding')
            await budget.complete(reservation, {'usage': {'total_tokens': 42}})
            return {'status': 'prepared'}
        async def close(self): pass
    monkeypatch.setattr('app.quality_references.ApprovedReferences', ControlledPreparation)
    worker = QualityWorker(store, settings)
    before = deepcopy(repo.world())
    await worker.run(job['id'])
    saved = store.job(job['id'])
    assert saved['status'] == 'completed'
    assert saved['checkpoints'] == [reference['id']]
    assert saved['progress'] == {'completed': 1, 'total': 1}
    assert saved['budget']['requests'] == 1 and saved['budget']['reported_tokens'] == 42
    await worker.prepare_references(saved, JobBudget(store, job['id']))
    assert calls == [reference['id']]
    assert repo.world() == before
    stale = store.create_reference_job({'idempotency_key': 'stale', 'case_ids': [reference['id']]})
    repo._data['qualityCases']['reference']['revision'] = 2
    await worker.run(stale['id'])
    assert store.job(stale['id'])['status'] == 'failed'
    assert calls == [reference['id']]
