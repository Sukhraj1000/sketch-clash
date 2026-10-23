"""Controlled operator-decision and dataset-transition tests; no real approvals."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from types import SimpleNamespace

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
import pytest

from app.pipeline import BASELINE_VERSION, version_key
from app.repository import StoreError, key_for
from app.quality_api import OperatorGate, register_quality_routes
from test_quality import state, comparison_fixture, seed_case, create_job


def decision(**extra):
    return {'reviewer': 'Synthetic operator fixture', 'reason': 'Engineering verification only; not a human adoption decision.', **extra}


def exposed_group(repo, store, *, active=False):
    group = 'same-physical-object-and-session'
    first = seed_case(repo, 'angle-one', 'reserved', group=group, seed=41)
    second = seed_case(repo, 'angle-two', 'reserved', group=group, seed=42)
    seed_case(repo, 'development', seed=43)
    for case in (first, second):
        repo.transaction(lambda tx, c=case: tx.put('qualityCaseRevisions', {**c, '_id': key_for(c['id'], str(c['revision']))}))
    job = create_job(store, kind='candidate')
    store.mutate_job(job['id'], lambda j: j.update(status='running' if active else 'completed'))
    repo.transaction(lambda tx: tx.put('qualityReservedUse', {'_id': key_for(repo.world_id, 'reserved-use', group),
        'world_id': repo.world_id, 'group_id': group, 'job_id': job['id'], 'created_at': repo.clock()}))
    return group, [first, second], job


def test_rejection_is_immutable_idempotent_blocks_adoption_and_preserves_frozen_version(state):
    repo, store, _ = state
    battle = repo.create_battle('unchanged-round')
    before_world = deepcopy(repo.world())
    job, version_id = comparison_fixture(repo, store)
    version = repo._data['pipelineVersions'][version_key(repo.world_id, version_id)]
    version['parent_id'] = BASELINE_VERSION
    version['config']['recognition_guidance'] = 'A controlled fixture difference.'
    original_version = deepcopy(repo.get_pipeline(version_id))
    frozen_snapshot = deepcopy(store.job(job['id'])['snapshot'])
    original_results = deepcopy(store.results(job['id']))
    rejected = store.reject_job(job['id'], decision())
    assert rejected['human_decision']['decision'] == 'rejected'
    assert store.reject_job(job['id'], decision()) == rejected
    with pytest.raises(StoreError) as changed:
        store.reject_job(job['id'], decision(reason='A different later decision cannot overwrite the first.'))
    assert changed.value.code == 'decision_exists'
    assert not store.gates(job['id'])['passing']
    assert 'operator rejected' in ' '.join(store.gates(job['id'])['reasons']).lower()
    viewed = next(item for item in store.overview()['versions'] if item['id'] == version_id)
    assert viewed['human_decision'] == rejected['human_decision']
    assert viewed['activation_eligible'] is False
    assert viewed['config_diff'] == [{'field': 'recognition_guidance', 'before': '', 'after': 'A controlled fixture difference.'}]
    with pytest.raises(StoreError) as blocked:
        store.activate(decision(version_id=version_id, expected_active_version_id=BASELINE_VERSION, expected_revision=1))
    assert blocked.value.code == 'candidate_rejected'
    assert repo.get_pipeline(version_id) == original_version
    assert store.job(job['id'])['snapshot'] == frozen_snapshot
    assert store.results(job['id']) == original_results
    assert repo.get_battle(battle['id'])['pipeline_version_id'] == BASELINE_VERSION
    assert repo.world() == before_world


def test_active_candidate_requires_rollback_before_rejection_and_cannot_be_restored_afterwards(state):
    repo, store, _ = state
    job, version_id = comparison_fixture(repo, store)
    store.activate(decision(version_id=version_id, expected_active_version_id=BASELINE_VERSION, expected_revision=1))
    with pytest.raises(StoreError) as active:
        store.reject_job(job['id'], decision())
    assert active.value.code == 'rollback_required'
    assert not store.job(job['id']).get('human_decision')
    store.activate(decision(version_id=BASELINE_VERSION, expected_active_version_id=version_id, expected_revision=2), rollback=True)
    store.reject_job(job['id'], decision())
    with pytest.raises(StoreError) as rejected_rollback:
        store.activate(decision(version_id=version_id, expected_active_version_id=BASELINE_VERSION, expected_revision=3), rollback=True)
    assert rejected_rollback.value.code == 'candidate_rejected'
    viewed = next(item for item in store.overview()['versions'] if item['id'] == version_id)
    assert viewed['rollback_eligible'] is False


def test_running_or_missing_candidate_cannot_receive_a_misleading_final_rejection(state):
    repo, store, _ = state
    seed_case(repo, 'dev')
    baseline = create_job(store, key='missing-candidate')
    with pytest.raises(StoreError) as missing: store.reject_job(baseline['id'], decision())
    assert missing.value.code == 'no_candidate'
    job, _ = comparison_fixture(repo, store)
    store.mutate_job(job['id'], lambda j: j.update(status='running'))
    with pytest.raises(StoreError) as running: store.reject_job(job['id'], decision())
    assert running.value.code == 'job_in_progress'


def test_retirement_moves_all_group_cases_atomically_without_rewriting_truth_or_frozen_results(state):
    repo, store, _ = state
    group, cases, job = exposed_group(repo, store)
    snapshot = deepcopy(store.job(job['id'])['snapshot'])
    world = deepcopy(repo.world())
    pointer = deepcopy(store.overview()['active'])
    assert store.overview()['exposed_reserved_groups'] == [{'group_id': group, 'case_ids': ['angle-one', 'angle-two']}]
    retired = store.retire_group(decision(group_id=group))
    assert retired['already_applied'] is False
    assert retired['transition']['from_role'] == 'reserved'
    assert retired['transition']['to_role'] == 'development'
    assert retired['transition']['case_ids'] == ['angle-one', 'angle-two']
    for original in cases:
        case = repo._data['qualityCases'][original['id']]
        assert case['revision'] == 2 and case['role'] == 'development'
        for key in ('expected', 'shared_consent', 'provenance', 'image_hash', 'image_ref', 'visible_attributes', 'review_status'):
            assert case[key] == original[key]
        assert repo._data['qualityCaseRevisions'][key_for(original['id'], '1')]['role'] == 'reserved'
        assert repo._data['qualityCaseRevisions'][key_for(original['id'], '2')]['role'] == 'development'
    again = store.retire_group(decision(group_id=group))
    assert again['already_applied'] is True
    assert again['transition'] == retired['transition']
    assert len(repo._data['qualityGroupTransitions']) == 1
    assert store.job(job['id'])['snapshot'] == snapshot
    assert all(case['role'] == 'reserved' for case in snapshot['cases'] if case['group_id'] == group)
    assert store.overview()['exposed_reserved_groups'] == []
    assert store.overview()['active'] == pointer and repo.world() == world
    fresh = create_job(store, kind='baseline', key='regression')
    assert {case['id'] for case in store.job(fresh['id'])['snapshot']['cases']} == {'development', 'angle-one', 'angle-two'}


def test_retirement_requires_exposure_and_blocks_active_or_stale_group_changes(state):
    repo, store, _ = state
    with pytest.raises(StoreError) as unused: store.retire_group(decision(group_id='unused'))
    assert unused.value.code == 'group_not_exposed'
    group, cases, job = exposed_group(repo, store, active=True)
    original = deepcopy(repo._data['qualityCases'])
    with pytest.raises(StoreError) as running: store.retire_group(decision(group_id=group))
    assert running.value.code == 'group_in_use'
    assert repo._data['qualityCases'] == original
    store.mutate_job(job['id'], lambda j: j.update(status='cancelled'))
    repo._data['qualityCases'][cases[1]['id']]['role'] = 'development'
    with pytest.raises(StoreError) as stale: store.retire_group(decision(group_id=group))
    assert stale.value.code == 'stale_group'
    assert repo._data['qualityCases'][cases[0]['id']]['revision'] == 1
    assert not repo._data.get('qualityGroupTransitions')


def test_conflicting_revision_rolls_back_the_entire_group_transition(state):
    repo, store, _ = state
    group, cases, _ = exposed_group(repo, store)
    original = deepcopy(repo._data['qualityCases'])
    conflict_id = key_for(cases[-1]['id'], '2')
    repo.transaction(lambda tx: tx.put('qualityCaseRevisions', {'_id': conflict_id, 'fixture': 'existing immutable revision'}))
    with pytest.raises(StoreError) as conflict: store.retire_group(decision(group_id=group))
    assert conflict.value.code == 'revision_conflict'
    assert repo._data['qualityCases'] == original
    assert key_for(cases[0]['id'], '2') not in repo._data['qualityCaseRevisions']
    assert not repo._data.get('qualityGroupTransitions')


def test_repeated_simultaneous_group_retirement_creates_one_audit_and_one_revision(state):
    repo, store, _ = state
    group, cases, _ = exposed_group(repo, store)
    with ThreadPoolExecutor(max_workers=5) as pool:
        results = list(pool.map(lambda _: store.retire_group(decision(group_id=group)), range(10)))
    assert sum(not result['already_applied'] for result in results) == 1
    assert len(repo._data['qualityGroupTransitions']) == 1
    assert all(repo._data['qualityCases'][case['id']]['revision'] == 2 for case in cases)
    with pytest.raises(StoreError) as changed: store.retire_group(decision(group_id=group, reviewer='Different reviewer'))
    assert changed.value.code == 'transition_exists'


def test_new_decisions_require_operator_session_and_bounded_human_provenance(state):
    repo, store, _ = state
    app = FastAPI()
    app.state.operator_gate = OperatorGate(token='fixture-only-operator-token-123456789')
    app.state.quality = store
    app.state.quality_worker = SimpleNamespace(wake=asyncio.Event())
    @app.exception_handler(StoreError)
    async def handle(request: Request, exc: StoreError):
        return JSONResponse({'code': exc.code}, status_code=exc.status)
    register_quality_routes(app)
    job, _ = comparison_fixture(repo, store)
    with TestClient(app) as client:
        assert client.post(f"/api/quality/jobs/{job['id']}/reject", json=decision()).status_code == 401
        assert client.post('/api/quality/groups/retire', json=decision(group_id='guessed')).status_code == 401
        assert client.post('/api/quality/session', json={'token': 'fixture-only-operator-token-123456789'}).status_code == 200
        assert client.post(f"/api/quality/jobs/{job['id']}/reject", json=decision(reason='x'*601)).status_code == 422
        assert client.post(f"/api/quality/jobs/{job['id']}/reject", json=decision(reviewer='   ')).status_code == 422
        assert client.post('/api/quality/groups/retire', json=decision(group_id='../escape')).status_code == 422
        saved = client.post(f"/api/quality/jobs/{job['id']}/reject", json=decision())
        assert saved.status_code == 200
        assert saved.json()['human_decision']['decision'] == 'rejected'


def test_exposed_single_case_cannot_rename_its_group_to_bypass_final_holdout_rules(state):
    from test_quality import seed_feedback, review_body
    repo, store, _ = state
    feedback, _ = seed_feedback(repo)
    original = store.review(review_body(feedback, role='reserved', group_id='original-group'))['case']
    repo.transaction(lambda tx: tx.put('qualityReservedUse', {'_id': key_for(repo.world_id, 'reserved-use', 'original-group'),
        'world_id': repo.world_id, 'group_id': 'original-group', 'job_id': 'fixture-used-job'}))
    with pytest.raises(StoreError) as renamed:
        store.review(review_body(feedback, expected_revision=1, role='reserved', group_id='pretend-fresh-group'))
    assert renamed.value.code == 'group_exposed'
    assert repo._data['qualityCases'][original['id']]['group_id'] == 'original-group'
    with pytest.raises(StoreError) as reused:
        store.review(review_body(feedback, expected_revision=1, role='reserved', group_id='original-group'))
    assert reused.value.code == 'reserved_exposed'
