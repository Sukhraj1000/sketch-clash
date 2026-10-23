"""Human-owned datasets, immutable comparisons and guarded pipeline adoption.

No quality operation calls the battle or island mutation APIs. Snapshots contain
reviewed answers for scoring; inference_payload deliberately excludes them.
"""
from __future__ import annotations
from copy import deepcopy
from datetime import datetime
from hashlib import sha256
from io import BytesIO
import json
import secrets
from PIL import Image
from .catalog import CHARACTER_TYPES, normalize_key
from .engine import validate_fighter_config, validate_visual_spec
from .pipeline import BASELINE_VERSION, BASE_PROMPT_HASH, active_key, version_key, validate_pipeline_config
from .repository import StoreError, key_for, public

POLICY = {
    'id': 'quality-policy-v1', 'min_development_cases': 3, 'min_final_cases': 3,
    'min_final_groups': 3, 'max_wrong_accepted_increase': 0,
    'max_coverage_drop': 0, 'max_unnecessary_clarification_increase': 0,
    'max_latency_ratio': 2, 'max_requests': 60, 'max_tokens': 600000,
    'deadline_seconds': 600, 'concurrency': 2, 'max_input_tokens': 48000,
    'max_output_tokens': 4096, 'max_cases': 12, 'max_references': 3,
    'statement': 'Small comparisons remain provisional; passing is not proof of generalisation.',
}
TERMINAL = {'completed', 'failed', 'cancelled', 'interrupted', 'budget_exceeded', 'needs_review'}

def identity(value):
    key = normalize_key(value or '')
    for record in CHARACTER_TYPES:
        if key in [normalize_key(x) for x in [record['canonical_key'], *record['aliases']]]:
            return record['canonical_key']
    return key

def score_outcome(expected, observation):
    accepted = observation.get('status') == 'recognized' and bool(observation.get('pending_fighter'))
    predicted = identity((observation.get('pending_fighter') or {}).get('canonical_type_id'))
    clarify = bool(expected.get('clarification_required'))
    correct = accepted and not clarify and predicted == identity(expected.get('canonical_type_id'))
    return {'correct_identity': int(correct), 'wrong_accepted': int(accepted and not correct),
            'appropriate_clarification': int(not accepted and clarify),
            'unnecessary_clarification': int(not accepted and not clarify), 'answered': int(accepted), 'total': 1}

def technical_check(observation):
    fighter = observation.get('pending_fighter')
    if not fighter:
        return {'valid': observation.get('status') in ('needs_selection', 'needs_recapture'), 'render_required': False}
    valid = validate_fighter_config(fighter)['valid'] and validate_visual_spec(fighter.get('visual_spec', {}))['valid']
    return {'valid': valid, 'render_required': True, 'combat_stats_fixed': validate_fighter_config(fighter)['valid']}

def inference_payload(case):
    # Never pass expected labels, comments, names, reviewer decisions or previous outputs.
    return {k: deepcopy(case[k]) for k in ('image_ref', 'image_hash', 'width', 'height')}

def perceptual_hash(data):
    with Image.open(BytesIO(data)) as im:
        pixels = list(im.convert('L').resize((9, 8)).getdata())
    return format(sum((pixels[y*9+x] > pixels[y*9+x+1]) << (y*8+x) for y in range(8) for x in range(8)), '016x')

def clean_document(value):
    """Export policy: no media bytes, credentials, opaque model steps or private input."""
    blocked = {'_id', 'data', 'image_bytes', 'steps', 'thought', 'signature', 'token', 'key', 'uri', 'embedding'}
    if isinstance(value, dict):
        return {k: clean_document(v) for k, v in value.items() if k not in blocked and not any(s in k.lower() for s in ('api_key', 'password', 'secret', 'mongodb_uri'))}
    if isinstance(value, list): return [clean_document(v) for v in value]
    if isinstance(value, bytes): return None
    return value

class QualityStore:
    def __init__(self, repository):
        self.repo = repository
        self.world_id = repository.world_id

    def ensure_indexes(self):
        if not hasattr(self.repo, 'db'): return
        indexes = {
            'qualityCases': [([('world_id', 1), ('feedback_id', 1)], True), ([('world_id', 1), ('role', 1), ('review_status', 1), ('shared_consent', 1)], False)],
            'qualityReviews': [([('world_id', 1), ('feedback_id', 1), ('created_at', -1)], False)],
            'qualityCaseRevisions': [([('world_id', 1), ('id', 1), ('revision', 1)], True)],
            'qualityJobs': [([('world_id', 1), ('status', 1), ('created_at', 1)], False)],
            'qualityState': [([('world_id', 1), ('id', 1)], True)],
            'qualityResults': [([('world_id', 1), ('job_id', 1), ('case_id', 1), ('variant', 1)], True)],
            'qualityComparisons': [([('world_id', 1), ('job_id', 1), ('case_id', 1)], True)],
            'qualityActivation': [([('world_id', 1), ('created_at', -1)], False)],
            'qualityReservedUse': [([('world_id', 1), ('group_id', 1)], True)],
            'qualityGroupTransitions': [([('world_id', 1), ('group_id', 1)], True)],
        }
        for collection, definitions in indexes.items():
            for keys, unique in definitions: self.repo.db[collection].create_index(keys, unique=unique)

    def rows(self, tx, collection):
        return tx.find(collection, {'world_id': self.world_id}, limit=501)

    def get(self, tx, collection, identifier):
        doc = tx.get(collection, identifier)
        if not doc or doc.get('world_id') != self.world_id:
            raise StoreError('Quality record not found.', 404, 'not_found')
        return doc

    def overview(self):
        def read(tx):
            feedback = self.rows(tx, 'qualityFeedback')
            reviews = self.rows(tx, 'qualityReviews')
            cases = self.rows(tx, 'qualityCases')
            queue = []
            for item in feedback:
                battle = tx.get('battles', item['battle_id'])
                if not battle or battle['status'] not in ('completed', 'cancelled', 'failed'): continue
                capture = tx.get('captures', key_for(item['battle_id'], item['capture_id']))
                if not capture: continue
                own_reviews = sorted([r for r in reviews if r['feedback_id'] == item['id']], key=lambda r: (r.get('expected_revision', 0), r.get('created_at', '')))
                queue.append({'id': item['id'], 'feedback': public(item), 'battle_id': item['battle_id'],
                              'capture': {'image_ref': capture['image_ref'], 'crop': capture.get('crop'), 'observation': capture.get('observation')},
                              'review': public(own_reviews[-1]) if own_reviews else None})
            queue.sort(key=lambda q: (q['review'] is not None, q['feedback'].get('recognition_verdict') == 'correct', q['feedback'].get('creative_verdict') != 'change'))
            eligible = [c for c in cases if self.eligible(c)]
            readiness = {role: sum(c['role'] == role for c in eligible) for role in ('reference', 'development', 'reserved')}
            readiness.update({'reviewed': len(eligible), 'groups': len({c['group_id'] for c in eligible}),
                              'message': 'Needs human review' if not eligible else 'Reviewed data available; final gates still require independent groups.'})
            jobs = self.rows(tx, 'qualityJobs')
            for job in jobs:
                job['gate'] = self.gates(job['id'], tx)
            versions = [public(v) for v in self.rows(tx, 'pipelineVersions')]
            activations = self.rows(tx, 'qualityActivation')
            by_version = {version['id']: version for version in versions}
            by_job = {job['id']: job for job in jobs}
            for version in versions:
                job = by_job.get(version.get('job_id'))
                version['human_decision'] = deepcopy((job or {}).get('human_decision'))
                rejected = (version['human_decision'] or {}).get('decision') == 'rejected'
                version['activation_eligible'] = bool(job and job['gate']['passing'] and not rejected)
                version['rollback_eligible'] = not rejected and (version['id'] == BASELINE_VERSION or any(h['version_id'] == version['id'] for h in activations))
                parent = by_version.get(version.get('parent_id'))
                version['config_diff'] = ([{'field': key, 'before': deepcopy(parent['config'].get(key)),
                                            'after': deepcopy(version['config'].get(key))}
                    for key in sorted(set(parent['config']) | set(version['config']))
                    if parent['config'].get(key) != version['config'].get(key)] if parent else [])
            exposed = self.rows(tx, 'qualityReservedUse')
            exposed_groups = [{'group_id': use['group_id'], 'case_ids': sorted(c['id'] for c in cases
                if c['group_id'] == use['group_id'] and c['role'] == 'reserved')} for use in exposed]
            exposed_groups = [group for group in exposed_groups if group['case_ids']]
            return {'active': public(tx.get('qualityState', active_key(self.world_id))),
                    'versions': versions, 'queue': queue[:100],
                    'cases': [public(c) for c in cases], 'jobs': [self.public_job(j) for j in jobs][-50:][::-1],
                    'exposed_reserved_groups': exposed_groups,
                    'readiness': readiness, 'policy': POLICY, 'reference_retrieval': {'mode': 'reviewed visual references', 'status': 'no approved references' if not readiness['reference'] else 'approved references available'}}
        return self.repo.read(read)

    @staticmethod
    def eligible(case):
        return case.get('review_status') == 'approved' and case.get('shared_consent') is True and not case.get('retired')

    def review(self, body):
        def operation(tx):
            feedback = self.get(tx, 'qualityFeedback', body['feedback_id'])
            battle = tx.get('battles', feedback['battle_id'])
            if battle['status'] not in ('completed', 'cancelled', 'failed'):
                raise StoreError('Finish or close the round before reviewing it.', 409, 'private_round')
            capture = tx.get('captures', key_for(feedback['battle_id'], feedback['capture_id']))
            media = tx.get('media', capture['image_ref'].rsplit('/', 1)[-1])
            if not media: raise StoreError('Reviewed media is unavailable.', 409, 'missing_media')
            case_id = key_for(self.world_id, 'case', feedback['id'])
            prior = tx.get('qualityCases', case_id)
            revision = (prior or {}).get('revision', 0)
            if body.get('expected_revision', 0) != revision:
                raise StoreError('This review changed. Refresh before reviewing again.', 409, 'stale_review')
            group = body['group_id'].strip()
            if prior and prior['group_id'] != group and tx.get('qualityReservedUse', key_for(self.world_id, 'reserved-use', prior['group_id'])):
                raise StoreError('An exposed physical-object group cannot be renamed to become a fresh test group.', 409, 'group_exposed')
            if body['role'] == 'reserved' and tx.get('qualityReservedUse', key_for(self.world_id, 'reserved-use', group)):
                raise StoreError('An exposed group cannot return to reserved testing. Use development data and collect a fresh final group.', 409, 'reserved_exposed')
            phash = perceptual_hash(media['data'])
            consent = bool(feedback.get('shared_consent') and body.get('shared_consent'))
            if body.get('shared_consent') and not feedback.get('shared_consent'):
                raise StoreError('The player has not approved this photo for shared evaluation.', 409, 'consent_required')
            for other in self.rows(tx, 'qualityCases'):
                if other['id'] == case_id: continue
                related = (other['image_hash'] == capture['image_hash'] or other.get('session_group') == feedback['battle_id']
                           or (other.get('perceptual_hash') and (int(other['perceptual_hash'], 16) ^ int(phash, 16)).bit_count() <= 4))
                if related and other['group_id'] != group:
                    raise StoreError('A duplicate, similar photo or capture session already belongs to group '+other['group_id']+'. Review grouping before splitting it.', 409, 'group_conflict')
                if other['group_id'] == group and other['role'] != body['role']:
                    raise StoreError('One physical-object/session group cannot cross dataset roles.', 409, 'dataset_leakage')
            decision = body['decision']
            expected = {'canonical_type_id': identity(body.get('expected_identity')), 'clarification_required': bool(body.get('clarification_required'))}
            if decision == 'approved' and not expected['canonical_type_id'] and not expected['clarification_required']:
                raise StoreError('Review an identity or explicitly require clarification.', 422, 'review_required')
            # Conflicting labels are retained, never silently promoted to ground truth.
            if prior and prior.get('expected') != expected and prior['review_status'] == 'approved': decision = 'disputed'
            timestamp = self.repo.clock()
            review_id = key_for(case_id, str(revision + 1))
            provenance = {'reviewer': body['reviewer'], 'at': timestamp, 'reason': body['reason'], 'kind': 'human_operator'}
            review = {'_id': review_id, 'id': review_id, 'world_id': self.world_id, **deepcopy(body),
                      'decision': decision, 'created_at': timestamp, 'provenance': provenance}
            case = {'_id': case_id, 'id': case_id, 'world_id': self.world_id, 'feedback_id': feedback['id'],
                    'revision': revision + 1, 'image_ref': capture['image_ref'], 'image_hash': capture['image_hash'],
                    'width': media['width'], 'height': media['height'], 'crop': capture.get('crop'),
                    'perceptual_hash': phash, 'expected': expected, 'visible_attributes': body.get('visible_attributes', []),
                    'group_id': group, 'session_group': feedback['battle_id'], 'role': body['role'],
                    'review_status': decision, 'shared_consent': consent, 'provenance': provenance,
                    'created_at': timestamp, 'inclusion_reason': body['reason'], 'creative': body.get('creative', {})}
            tx.put('qualityReviews', review)
            tx.put('qualityCases', case)
            tx.put('qualityCaseRevisions', {**case, '_id': review_id})
            return {'review': public(review), 'case': public(case)}
        return self.repo.transaction(operation)

    def create_job(self, body):
        identifier = key_for(self.world_id, 'job', body['idempotency_key'])
        from .quality_catalog import freeze_catalog
        catalog_snapshot = freeze_catalog(self.repo, getattr(self, 'catalog_settings', None))
        def operation(tx):
            existing = tx.get('qualityJobs', identifier)
            if existing: return self.public_job(existing)
            active = tx.get('qualityState', active_key(self.world_id))
            version = tx.get('pipelineVersions', version_key(self.world_id, active['active_version_id']))
            all_cases = [c for c in self.rows(tx, 'qualityCases') if self.eligible(c)]
            selected = set(body.get('case_ids') or [])
            cases = [c for c in all_cases if c['role'] != 'reference' and (not selected or c['id'] in selected)]
            if body['kind'] == 'baseline': cases = [c for c in cases if c['role'] == 'development']
            if len(cases) > POLICY['max_cases']:
                raise StoreError('Select at most 12 cases per bounded comparison.', 422, 'dataset_limit')
            references = [c for c in all_cases if c['role'] == 'reference'][:30]
            all_groups = {role: {c['group_id'] for c in all_cases if c['role'] == role} for role in ('reference', 'development', 'reserved')}
            if any(all_groups[a] & all_groups[b] for a, b in [('reference', 'development'), ('reference', 'reserved'), ('development', 'reserved')]):
                raise StoreError('Dataset groups overlap. Resolve them before evaluation.', 409, 'dataset_leakage')
            for case in cases:
                if case['role'] == 'reserved' and tx.get('qualityReservedUse', key_for(self.world_id, 'reserved-use', case['group_id'])):
                    raise StoreError('A reserved group was used by an earlier comparison. Move exposed groups into development and review fresh final cases.', 409, 'reserved_exposed')
            needs_review = not cases or not any(c['role'] == 'development' for c in cases)
            requests = min(POLICY['max_requests'], body.get('max_requests', 24))
            estimate = len(cases) * (4 if body['kind'] == 'candidate' else 2) + (2 if body['kind'] == 'candidate' else 0)
            estimated_tokens = estimate * 15000
            if estimate > requests or estimated_tokens > POLICY['max_tokens']:
                raise StoreError(f'Estimated minimum {estimate} requests exceeds this job limit. Select fewer cases or raise the bounded limit.', 422, 'estimate_over_budget')
            job = {'_id': identifier, 'id': identifier, 'world_id': self.world_id, 'kind': body['kind'], 'scope': body.get('scope', 'recognition'),
                   'status': 'needs_review' if needs_review else 'queued', 'created_at': self.repo.clock(),
                   'baseline_id': version['id'], 'baseline_config': deepcopy(version['config']), 'candidate_id': None,
                   'policy': deepcopy(POLICY), 'snapshot': {'cases': deepcopy(cases), 'references': deepcopy(references), 'catalog': catalog_snapshot},
                   'snapshot_hash': sha256(json.dumps({'cases': cases, 'references': references, 'catalog': catalog_snapshot['digest']}, sort_keys=True).encode()).hexdigest(),
                   'progress': {'completed': 0, 'total': len(cases) * (2 if body['kind'] == 'candidate' else 1)},
                   'budget': {'max_requests': requests, 'requests': 0, 'max_tokens': POLICY['max_tokens'], 'reserved_tokens': 0, 'reported_tokens': 0,
                              'deadline_seconds': POLICY['deadline_seconds'], 'estimated_requests': estimate, 'estimated_tokens': estimated_tokens},
                   'checkpoints': [], 'inflight': None, 'cancel_requested': False,
                   'error': 'Needs human review: approve consented development cases before paid evaluation.' if needs_review else None}
            tx.put('qualityJobs', job)
            return self.public_job(job)
        return self.repo.transaction(operation)

    @staticmethod
    def _human_reason(body):
        reviewer, reason = str(body.get('reviewer', '')).strip(), str(body.get('reason', '')).strip()
        if not reviewer or not reason or len(reviewer) > 80 or len(reason) > 600:
            raise StoreError('Provide a reviewer name and concise decision reason.', 422, 'human_reason_required')
        return {'reviewer': reviewer, 'reason': reason}

    def reject_job(self, identifier, body):
        decision = self._human_reason(body)
        def operation(tx):
            job = self.get(tx, 'qualityJobs', identifier)
            prior = job.get('human_decision')
            if prior:
                if prior.get('decision') == 'rejected' and all(prior.get(key) == value for key, value in decision.items()):
                    return self.public_job(job)
                raise StoreError('This job already has an immutable human decision.', 409, 'decision_exists')
            if job['kind'] != 'candidate' or not job.get('candidate_id'):
                raise StoreError('This job has no frozen candidate to reject.', 409, 'no_candidate')
            pointer = tx.get('qualityState', active_key(self.world_id))
            if pointer['active_version_id'] == job['candidate_id']:
                raise StoreError('Roll back the active version before rejecting its candidate.', 409, 'rollback_required')
            if job['status'] not in TERMINAL:
                raise StoreError('Finish or cancel the running comparison before recording rejection.', 409, 'job_in_progress')
            # Adoption also writes this pointer: serialize rejection against concurrent activation
            # without changing the active version or its optimistic-concurrency revision.
            pointer['human_decision_sequence'] = pointer.get('human_decision_sequence', 0) + 1
            tx.put('qualityState', pointer)
            job['human_decision'] = {'decision': 'rejected', **decision, 'kind': 'human_operator', 'created_at': self.repo.clock()}
            tx.put('qualityJobs', job)
            return self.public_job(job)
        return self.repo.transaction(operation)

    def retire_group(self, body):
        decision = self._human_reason(body)
        group = body['group_id']
        transition_id = key_for(self.world_id, 'reserved-to-development', group)
        def operation(tx):
            prior = tx.get('qualityGroupTransitions', transition_id)
            if prior:
                if all(prior.get(key) == value for key, value in decision.items()):
                    return {'transition': public(prior), 'already_applied': True}
                raise StoreError('This group already has an immutable retirement decision.', 409, 'transition_exists')
            exposed = tx.get('qualityReservedUse', key_for(self.world_id, 'reserved-use', group))
            if not exposed:
                raise StoreError('Only groups already used in final evaluation can be retired through this action.', 409, 'group_not_exposed')
            cases = tx.find('qualityCases', {'world_id': self.world_id, 'group_id': group}, limit=501)
            if not cases or len(cases) > 500 or any(case['role'] != 'reserved' for case in cases):
                raise StoreError('The complete group must still contain reserved cases. Refresh its dataset state.', 409, 'stale_group')
            jobs = self.rows(tx, 'qualityJobs')
            if len(jobs) > 500:
                raise StoreError('The bounded active-job safety scan is full.', 409, 'quality_scan_limit')
            if any(job['status'] not in TERMINAL and any(case.get('group_id') == group
                for case in job.get('snapshot', {}).get('cases', []) + job.get('snapshot', {}).get('references', [])) for job in jobs):
                raise StoreError('A queued or running comparison still uses this group. Finish or cancel it first.', 409, 'group_in_use')
            timestamp = self.repo.clock()
            transitions = []
            for case in cases:
                previous_revision = case['revision']
                case.update(role='development', revision=previous_revision + 1, reserved_retired_at=timestamp,
                            dataset_transition_id=transition_id)
                revision_id = key_for(case['id'], str(case['revision']))
                if tx.get('qualityCaseRevisions', revision_id):
                    raise StoreError('A case revision already exists. Refresh the group before retrying.', 409, 'revision_conflict')
                tx.put('qualityCases', case)
                tx.put('qualityCaseRevisions', {**deepcopy(case), '_id': revision_id})
                transitions.append({'case_id': case['id'], 'from_revision': previous_revision, 'to_revision': case['revision']})
            audit = {'_id': transition_id, 'id': transition_id, 'world_id': self.world_id, 'group_id': group,
                     'from_role': 'reserved', 'to_role': 'development', 'case_ids': sorted(case['id'] for case in cases),
                     'case_revisions': transitions, 'exposed_by_job_id': exposed['job_id'], **decision,
                     'kind': 'human_operator', 'created_at': timestamp}
            tx.put('qualityGroupTransitions', audit)
            return {'transition': public(audit), 'already_applied': False}
        return self.repo.transaction(operation)

    def create_reference_job(self, body):
        identifier = key_for(self.world_id, 'reference-job', body['idempotency_key'])
        def operation(tx):
            prior = tx.get('qualityJobs', identifier)
            if prior: return self.public_job(prior)
            references = [self.get(tx, 'qualityCases', cid) for cid in dict.fromkeys(body['case_ids'])]
            if not references or any(not self.eligible(c) or c['role'] != 'reference' for c in references):
                raise StoreError('Select approved, consented reference cases first.', 409, 'reference_ineligible')
            pointer = tx.get('qualityState', active_key(self.world_id))
            job = {'_id': identifier, 'id': identifier, 'world_id': self.world_id, 'kind': 'references', 'scope': 'reference-preparation',
                   'status': 'queued', 'created_at': self.repo.clock(), 'baseline_id': pointer['active_version_id'], 'candidate_id': None,
                   'policy': deepcopy(POLICY), 'snapshot': {'cases': [], 'references': deepcopy(references)},
                   'snapshot_hash': sha256(json.dumps(references, sort_keys=True).encode()).hexdigest(),
                   'progress': {'completed': 0, 'total': len(references)},
                   'budget': {'max_requests': len(references), 'requests': 0, 'max_tokens': len(references)*8192,
                              'reserved_tokens': 0, 'reported_tokens': 0, 'estimated_requests': len(references),
                              'deadline_seconds': POLICY['deadline_seconds']}, 'checkpoints': [], 'inflight': None, 'cancel_requested': False}
            tx.put('qualityJobs', job)
            return self.public_job(job)
        return self.repo.transaction(operation)

    @staticmethod
    def public_job(job):
        return {**{k: deepcopy(v) for k, v in job.items() if k not in ('_id', 'snapshot', 'baseline_config', 'inflight')}, 'external_request_uncertain': bool(job.get('inflight'))}

    def job(self, identifier):
        return self.repo.read(lambda tx: self.get(tx, 'qualityJobs', identifier))

    def mutate_job(self, identifier, callback):
        def operation(tx):
            job = self.get(tx, 'qualityJobs', identifier)
            callback(job)
            tx.put('qualityJobs', job)
            return deepcopy(job)
        return self.repo.transaction(operation)

    def results(self, identifier):
        return self.repo.read(lambda tx: [public(r) for r in tx.find('qualityResults', {'world_id': self.world_id, 'job_id': identifier})])

    def save_result(self, identifier, result):
        def operation(tx):
            job = self.get(tx, 'qualityJobs', identifier)
            rid = key_for(identifier, result['case_id'], result['variant'])
            if tx.get('qualityResults', rid): return
            tx.put('qualityResults', {'_id': rid, 'id': rid, 'world_id': self.world_id, 'job_id': identifier,
                                     'created_at': self.repo.clock(), 'render_status': 'pending' if result.get('fighter') else 'not_required', **deepcopy(result)})
            job['progress']['completed'] += 1
            job['checkpoints'].append(rid)
            job['inflight'] = None
            tx.put('qualityJobs', job)
        self.repo.transaction(operation)

    def render(self, result_id, body):
        def operation(tx):
            result = self.get(tx, 'qualityResults', result_id)
            passed = body['status'] == 'passed' and body['bounds_ok'] and body['visible'] and not body['errors'] and set(body['states']) >= {'idle', 'rest', 'wander'}
            report = {**body, 'status': 'passed' if passed else ('unavailable' if body['status'] == 'unavailable' else 'failed'), 'created_at': self.repo.clock()}
            result['render_status'] = report['status']
            result['render_report'] = report
            tx.put('qualityResults', result)
            return public(result)
        return self.repo.transaction(operation)

    def comparison(self, identifier):
        def operation(tx):
            job = self.get(tx, 'qualityJobs', identifier)
            results = tx.find('qualityResults', {'world_id': self.world_id, 'job_id': identifier})
            pairs = []
            for case in job['snapshot']['cases']:
                choices = [r for r in results if r['case_id'] == case['id'] and r.get('fighter')]
                if len(choices) != 2: continue
                pair_id = key_for(identifier, 'pair', case['id'])
                pair = tx.get('qualityComparisons', pair_id)
                if not pair:
                    if secrets.randbelow(2): choices.reverse()
                    pair = {'_id': pair_id, 'id': pair_id, 'world_id': self.world_id, 'job_id': identifier, 'case_id': case['id'],
                            'left_id': choices[0]['id'], 'right_id': choices[1]['id'], 'review': None}
                    tx.put('qualityComparisons', pair)
                by_id = {r['id']: r for r in choices}
                pairs.append({'id': pair_id, 'case_id': case['id'], 'image_ref': case['image_ref'], 'review': pair['review'],
                              **{side: {'result_id': pair[side+'_id'], 'fighter': by_id[pair[side+'_id']]['fighter']} for side in ('left', 'right')}})
            return {'pairs': pairs, 'blinded': True, 'instruction': 'Judge resemblance and appeal in context. Labels remain hidden until your review is recorded.'}
        return self.repo.transaction(operation)

    def compare_review(self, pair_id, body):
        def operation(tx):
            pair = self.get(tx, 'qualityComparisons', pair_id)
            if pair['review']:
                raise StoreError('This comparison already has an immutable human review.', 409, 'review_exists')
            pair['review'] = {**body, 'created_at': self.repo.clock(), 'kind': 'human_operator'}
            tx.put('qualityComparisons', pair)
            return public(pair)
        return self.repo.transaction(operation)

    def gates(self, identifier, tx=None):
        if tx is None: return self.repo.read(lambda current: self.gates(identifier, current))
        job = self.get(tx, 'qualityJobs', identifier)
        policy = job['policy']
        results = tx.find('qualityResults', {'world_id': self.world_id, 'job_id': identifier})
        final = [c for c in job['snapshot']['cases'] if c['role'] == 'reserved']
        development = [c for c in job['snapshot']['cases'] if c['role'] == 'development']
        reasons = []
        if (job.get('human_decision') or {}).get('decision') == 'rejected': reasons.append('The operator rejected this candidate.')
        if job['kind'] != 'candidate' or not job.get('candidate_id'): reasons.append('No frozen candidate comparison.')
        if job['status'] != 'completed': reasons.append('The comparison did not complete successfully.')
        budget = job['budget']
        if budget['requests'] > budget['max_requests'] or budget['reserved_tokens'] > budget['max_tokens'] or job.get('inflight') or job.get('cancel_requested'):
            reasons.append('Budget, cancellation or unresolved request checks failed.')
        if job.get('completed_at') and job.get('deadline_at') and datetime.fromisoformat(job['completed_at']).timestamp() > job['deadline_at']:
            reasons.append('The fixed job deadline was exceeded.')
        if len(development) < policy['min_development_cases'] or len(final) < policy['min_final_cases'] or len({c['group_id'] for c in final}) < policy['min_final_groups']:
            reasons.append('Insufficient independent reviewed cases/groups (3 development and 3 final groups required).')
        if len(results) != len(job['snapshot']['cases']) * 2: reasons.append('Comparison results are incomplete.')
        if any(not r.get('technical', {}).get('valid') or r.get('error') for r in results): reasons.append('Mandatory technical checks failed.')
        if any(r.get('fighter') and r.get('render_status') != 'passed' for r in results): reasons.append('Actual 3D render checks are missing, unavailable or failed.')
        totals = {}
        for variant in ('baseline', 'candidate'):
            selected = [r for r in results if r['variant'] == variant and r.get('role') == 'reserved']
            totals[variant] = {k: sum(r.get('recognition', {}).get(k, 0) for r in selected) for k in ('correct_identity', 'wrong_accepted', 'appropriate_clarification', 'unnecessary_clarification', 'answered', 'total')}
        a, b = totals['baseline'], totals['candidate']
        if b['wrong_accepted'] > a['wrong_accepted']: reasons.append('Wrong accepted identities increased.')
        if b['answered'] < a['answered']: reasons.append('Coverage decreased.')
        if b['unnecessary_clarification'] > a['unnecessary_clarification']: reasons.append('Unnecessary clarification increased.')
        if job['scope'] == 'recognition' and b['correct_identity'] + b['appropriate_clarification'] <= a['correct_identity'] + a['appropriate_clarification']:
            reasons.append('No independent recognition improvement demonstrated.')
        latencies = {v: sum(r.get('latency_ms', 0) for r in results if r['variant'] == v) for v in ('baseline', 'candidate')}
        if latencies['candidate'] > max(1, latencies['baseline']) * policy['max_latency_ratio']: reasons.append('Candidate latency exceeds the fixed limit.')
        comparisons = tx.find('qualityComparisons', {'world_id': self.world_id, 'job_id': identifier})
        creative = {'reviewed': 0, 'candidate_preferred': 0, 'baseline_preferred': 0, 'ties': 0, 'neither': 0}
        for pair in comparisons:
            review = pair.get('review')
            if not review: continue
            creative['reviewed'] += 1
            pref = review['preference']
            if pref in ('tie', 'neither'): creative['ties' if pref == 'tie' else 'neither'] += 1
            else:
                picked = tx.get('qualityResults', pair[pref+'_id'])
                creative['candidate_preferred' if picked['variant'] == 'candidate' else 'baseline_preferred'] += 1
        if job['scope'] == 'appearance' and (creative['reviewed'] < len(final) + len(development) or creative['candidate_preferred'] <= creative['baseline_preferred'] or creative['neither']):
            reasons.append('Creative comparison needs human review and supporting preference evidence.')
        return {'status': 'eligible_for_human_approval' if not reasons else 'blocked', 'passing': not reasons,
                'reasons': reasons, 'recognition': totals, 'creative': creative, 'policy_id': policy['id'], 'provisional': True}

    def activate(self, body, rollback=False):
        def operation(tx):
            pointer = tx.get('qualityState', active_key(self.world_id))
            if pointer['active_version_id'] != body['expected_active_version_id'] or pointer['revision'] != body['expected_revision']:
                raise StoreError('The active version changed. Refresh before approving.', 409, 'stale_activation')
            version = tx.get('pipelineVersions', version_key(self.world_id, body['version_id']))
            if not version: raise StoreError('Pipeline version not found.', 404, 'not_found')
            source_job = tx.get('qualityJobs', version['job_id']) if version.get('job_id') else None
            if ((source_job or {}).get('human_decision') or {}).get('decision') == 'rejected':
                raise StoreError('This candidate has an immutable human rejection.', 409, 'candidate_rejected')
            history = self.rows(tx, 'qualityActivation')
            if rollback:
                if version['id'] != BASELINE_VERSION and not any(h['version_id'] == version['id'] for h in history):
                    raise StoreError('Rollback is limited to previously active versions.', 409, 'invalid_rollback')
            else:
                if not version.get('job_id') or not self.gates(version['job_id'], tx)['passing']:
                    raise StoreError('Evaluation and review gates have not passed.', 409, 'gates_failed')
            pointer.update({'active_version_id': version['id'], 'revision': pointer['revision'] + 1, 'updated_at': self.repo.clock()})
            tx.put('qualityState', pointer)
            event_id = key_for(self.world_id, 'activation', str(pointer['revision']))
            tx.put('qualityActivation', {'_id': event_id, 'id': event_id, 'world_id': self.world_id, **body,
                                         'action': 'rollback' if rollback else 'activation', 'created_at': self.repo.clock()})
            return public(pointer)
        return self.repo.transaction(operation)

    def export(self, identifier=None):
        overview = self.overview()
        # Private gameplay feedback is never bulk-exported; only explicitly consented reviewed cases.
        payload = {'schema': 'quality-export-v1', 'policy': POLICY,
                   'cases': [c for c in overview['cases'] if self.eligible(c)],
                   'versions': overview['versions']}
        if identifier:
            job = self.job(identifier)
            payload.update({'job': self.public_job(job), 'results': self.results(identifier)})
        return clean_document(payload)
