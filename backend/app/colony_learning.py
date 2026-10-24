"""Evidence-bound object dossiers, experiments and construction proposals.

All writes use the repository's transaction boundary. Findings describe tested
simulation conditions, never new real-world facts or unrestricted agent powers.
"""
from __future__ import annotations

import asyncio
from copy import deepcopy
import math
import re

from pydantic import ValidationError

from .colony_experiments import (BlueprintProposal, ExperimentSpec, RULE_VERSION, DOSSIER_EVIDENCE_VERSION,
                                PRIMARY_KINDS, PRODUCTION_BENCHMARKS, canonical_digest, cavity_model,
                                reflection_model, dossier_fingerprint, context_for,
                                physical_properties, physical_property_fingerprint, simulate_experiment, validate_blueprint)
from .repository import StoreError, key_for

DOSSIERS = 'colonyObjectDossiers'
DOSSIER_REVISIONS = 'colonyObjectDossierRevisions'
EXPERIMENTS = 'colonyExperiments'
FINDINGS = 'colonyFindings'
BLUEPRINTS = 'colonyBlueprints'
RESEARCH = 'colonyResearch'
STATE = 'colonyLearningState'
VECTOR_INDEX = 'colony_findings_vector'
MAX_FINDINGS = 1000


def finding_index_definition(dimensions=768):
    return {'fields': [{'type': 'vector', 'path': 'embedding', 'numDimensions': dimensions, 'similarity': 'cosine'},
                       *[{'type': 'filter', 'path': path} for path in
                         ('world_id', 'rule_version', 'embedding_model', 'embedding_dimensions', 'status')]]}


def public_learning(value):
    """Exclude hidden physical properties and embedding vectors from observations."""
    if isinstance(value, list):
        return [public_learning(item) for item in value]
    if isinstance(value, dict):
        return {key: public_learning(item) for key, item in value.items()
                if not key.startswith('_') and key != 'embedding'}
    return value


def _validated(model, body, code):
    try:
        return body if isinstance(body, model) else model.model_validate(body)
    except (ValidationError, ValueError, TypeError):
        raise StoreError('The research proposal has unsupported fields or invalid values.', 422, code) from None


def _covered_structure_actions(projects, resource):
    """Reserved or delivered capped benefits must not be sold as new utility."""
    covered = set()
    for project in projects:
        if project.get('kind') != 'assembly' or project.get('status') not in ('planned', 'building', 'complete'):
            continue
        benefit = project.get('benefit', {})
        amount = benefit.get('amount', 0)
        if (benefit.get('kind') == 'task_yield_bonus' and benefit.get('resource') == resource
                and isinstance(amount, (int, float)) and not isinstance(amount, bool)
                and math.isfinite(amount) and amount >= 1):
            covered.update(benefit.get('eligible_actions', []))
    return covered


def evidence_status(record, dossiers):
    """Read-time applicability, keeping the original experiment/finding intact."""
    if record.get('rule_version') != RULE_VERSION:
        return 'historical_rules'
    ids = record.get('subject_ids') or []
    subjects = [dossiers.get(identifier) for identifier in ids]
    if not ids or any(row is None for row in subjects):
        return 'missing_subject_evidence'
    if record.get('property_fingerprints') != [dossier_fingerprint(row, record.get('family')) for row in subjects]:
        return 'superseded_properties'
    if record.get('family') == 'contain' and any(
            (row.get('simulation_properties', {}).get('cavity_model') or
             cavity_model(row.get('observed_evidence', {}).get('visible_features', [])))['status']
            in ('unknown', 'conflicting_evidence') for row in subjects):
        return 'missing_cavity_evidence'
    if record.get('family') == 'reflect' and any(
            row.get('simulation_properties', {}).get('reflection_model', {}).get('status')
            != 'observed_reflective_surface' for row in subjects):
        return 'missing_reflection_evidence'
    return 'current'


def annotated_evidence(record, dossiers):
    status = evidence_status(record, dossiers)
    return {**record, 'evidence_status': status,
            'evidence_detail': ('Applies to the current simulation proxy and these tested conditions.' if status == 'current' else
                                'Historical receipt preserved. It is not current evidence for this object proxy; a supported retest is required.')}


class ColonyLearningStore:
    def __init__(self, repo):
        self.repo = repo

    def ensure_indexes(self):
        """Initialize bounded evidence indexes; missing Search never blocks play."""
        if not hasattr(self.repo, 'db'):
            return {'status': 'exact_only', 'detail': 'The memory development adapter has no Atlas search indexes.'}
        try:
            from pymongo.operations import SearchIndexModel
            for collection in (DOSSIERS, DOSSIER_REVISIONS, EXPERIMENTS, FINDINGS, BLUEPRINTS, RESEARCH):
                self.repo.db[collection].create_index([('world_id', 1)])
            self.repo.db[FINDINGS].create_index([('world_id', 1), ('rule_version', 1), ('updated_at', -1)])
            self.repo.db[DOSSIERS].create_index([('world_id', 1), ('resident_id', 1)], unique=True)
            collection = self.repo.db[FINDINGS]
            indexes = list(collection.list_search_indexes(name=VECTOR_INDEX))
            if not indexes:
                dimensions = getattr(self.repo.settings, 'embedding_dimensions', 768)
                collection.create_search_index(SearchIndexModel(definition=finding_index_definition(dimensions),
                                                                 name=VECTOR_INDEX, type='vectorSearch'))
                return {'status': 'vector_index_building', 'detail': 'The findings vector index is being built; exact retrieval is available.'}
            return {'status': 'vector_ready' if any(row.get('queryable') is True for row in indexes) else 'vector_index_building'}
        except Exception as exc:
            return {'status': 'exact_only', 'error_category': type(exc).__name__,
                    'detail': 'Atlas search setup is unavailable; exact evidence lookup remains available.'}

    def _scope(self, scope):
        # Import lazily to keep the SDK/colonies/learning dependency acyclic.
        from .colonies import COLONY_IDS, colony_world_id
        for colony_id in COLONY_IDS:
            if scope == colony_world_id(self.repo.world_id, colony_id):
                return colony_id
        raise StoreError('Research belongs to one of this world’s islands.', 404, 'research_scope_not_found')

    def _event(self, tx, scope, identifier, kind, message, *, actor=None, data=None):
        from .observability import record_event
        return record_event(tx, self.repo.world_id, event_id=identifier, kind=kind,
                            island_id=self._scope(scope), actor_id=(actor or {}).get('id'),
                            actor_name=(actor or {}).get('display_name'), message=message, data=data or {}, at=self.repo.clock())

    def initialize_resident(self, tx, resident, accepted_fighter=None, placement_id=None):
        scope = resident['world_id']
        self._scope(scope)
        identifier = key_for(scope, 'object-dossier', resident['id'])
        existing = tx.get(DOSSIERS, identifier)
        source = accepted_fighter or resident
        observed = deepcopy(source.get('observed_object') or {})
        previous_evidence = (existing or {}).get('observed_evidence', {})
        # Accepted evidence wins; a later refresh lacking the original placement
        # cannot erase the source evidence already attached to this dossier.
        features = [str(item)[:200] for item in (observed.get('visible_features') or previous_evidence.get('visible_features') or [])[:24]]
        agent = next(iter(tx.find('islandAgents', {'world_id': scope, 'character_id': resident['id']}, limit=1)), {})
        capabilities = agent.get('capabilities', [])
        visual = source.get('visual_spec') or resident.get('visual_spec')
        cavity = cavity_model(features, capabilities)
        reflection = reflection_model(features)
        evidence_fingerprint = canonical_digest({'version': DOSSIER_EVIDENCE_VERSION, 'features': features,
                                                 'visual_proportions': (visual or {}).get('proportions', {}), 'cavity': cavity})
        if existing and existing.get('evidence_fingerprint') == evidence_fingerprint:
            return public_learning(existing)
        props = physical_properties(features, visual, capabilities)
        geometry = {key: props[key] for key in ('width', 'height', 'depth', 'length')}
        property_fingerprint = physical_property_fingerprint(props)
        if (existing and existing.get('_physical_properties') and
                physical_property_fingerprint(existing['_physical_properties']) == property_fingerprint):
            # v1 included a provenance string in its hash. Preserve that legacy
            # token when numeric properties are unchanged, while correcting the
            # provenance label; this does not invalidate unrelated valid tests.
            property_fingerprint = existing['property_fingerprint']
        timestamp = self.repo.clock()
        dossier = {'_id': identifier, 'id': identifier, 'world_id': scope, 'root_world_id': self.repo.world_id,
                   'resident_id': resident['id'], 'colony_id': self._scope(scope),
                   'display_name': resident['display_name'], 'object_type': resident.get('object_type'),
                   'canonical_type_id': resident.get('canonical_type_id'), 'created_at': (existing or {}).get('created_at', timestamp),
                   'rule_version': RULE_VERSION, 'evidence_version': DOSSIER_EVIDENCE_VERSION,
                   'evidence_fingerprint': evidence_fingerprint, 'revision': (existing or {}).get('revision', 0) + 1,
                   'updated_at': timestamp,
                   'observed_evidence': {'visible_features': features, 'capture_id': source.get('capture_id') or previous_evidence.get('capture_id'),
                       'output_id': source.get('output_id') or previous_evidence.get('output_id'),
                       'pipeline_version_id': source.get('pipeline_version_id') or previous_evidence.get('pipeline_version_id'),
                       'placement_id': placement_id or previous_evidence.get('placement_id'), 'battle_id': resident.get('first_battle_id'),
                       'status': 'accepted_capture' if features else 'historical_features_unavailable'},
                   'simulation_properties': {'geometry': geometry,
                       'apparent_cavity': True if cavity['status'] == 'observed_cavity' else False if cavity['status'] == 'observed_absence' else None,
                       'cavity_model': cavity,
                       'reflection_model': reflection,
                       'material_assumption': props['material_assumption'],
                       'authority': 'authored_testbed_assumptions_not_measured_real_world_properties',
                       'unknowns': ['mass', 'friction', 'stiffness', 'usable_capacity', 'leakage', 'reflectance'],
                       'units': 'normalized_simulation_units'},
                   'property_fingerprint': property_fingerprint, '_physical_properties': props,
                   'family_property_fingerprints': {'reflect': canonical_digest({
                       'base': property_fingerprint, 'surface': reflection, 'reflectance': props['_reflectivity']})},
                   'tested_capabilities': [], 'finding_ids': deepcopy((existing or {}).get('finding_ids', []))}
        if existing:
            revision_id = key_for(identifier, 'revision', str(existing.get('revision', 0)),
                                  existing.get('evidence_fingerprint') or existing.get('property_fingerprint', 'legacy'))
            if not tx.get(DOSSIER_REVISIONS, revision_id):
                tx.put(DOSSIER_REVISIONS, {**deepcopy(existing), '_id': revision_id, 'id': revision_id,
                       'dossier_id': identifier, 'archived_at': timestamp, 'immutable': True})
            dossier['previous_revision_id'] = revision_id
            dossier['refresh_reason'] = 'Refresh evidence-scoped simulation capabilities; preserve earlier evidence and receipts.'
            # A changed proxy needs a new test; unchanged numerical properties
            # retain their valid capabilities. Never reinterpret old receipts.
            dossier['tested_capabilities'] = [deepcopy(row) for row in existing.get('tested_capabilities', [])
                if row.get('rule_version') == RULE_VERSION and
                dossier_fingerprint(existing, row.get('family')) == dossier_fingerprint(dossier, row.get('family'))
                and not (row.get('family') == 'contain' and cavity['status'] in ('unknown', 'conflicting_evidence'))]
        tx.put(DOSSIERS, dossier)
        return public_learning(dossier)

    def refresh_arrivals(self, tx, scope, colony_id, residents):
        if self._scope(scope) != colony_id:
            raise StoreError('Arrival research cannot cross islands.', 422, 'research_scope_mismatch')
        state_id = key_for(scope, 'learning-state')
        old = tx.get(STATE, state_id)
        records = []
        for resident in sorted(residents, key=lambda item: item['id']):
            if resident.get('world_id') != scope:
                raise StoreError('Arrival research contains a resident from another island.', 422, 'research_scope_mismatch')
            # Accepted placement is immutable; historical upgrades recover its
            # evidence rather than re-recognizing or changing the resident.
            placements = tx.find('colonyPlacements', {'world_id': self.repo.world_id, 'resident_id': resident['id']}, limit=1000)
            first = next((row for row in placements if row.get('battle_id') == resident.get('first_battle_id')), None)
            dossier = self.initialize_resident(tx, resident, (first or {}).get('accepted_fighter'), (first or {}).get('id'))
            agent = next(iter(tx.find('islandAgents', {'world_id': scope, 'character_id': resident['id']}, limit=1)), {})
            records.append({'resident_id': resident['id'], 'property_fingerprint': dossier['property_fingerprint'],
                            'evidence_fingerprint': dossier.get('evidence_fingerprint'),
                            'capabilities': sorted(agent.get('capabilities', [])),
                            'actions': sorted(agent.get('allowed_actions', []))})
        fingerprint = canonical_digest(records)
        if old and old['capability_fingerprint'] == fingerprint:
            return {'changed': False, 'fingerprint': fingerprint, 'reopened': [], 'new_resident_ids': []}
        previous_ids = set((old or {}).get('resident_ids', []))
        new_ids = [record['resident_id'] for record in records if record['resident_id'] not in previous_ids]
        reopened = []
        for research in tx.find(RESEARCH, {'world_id': scope}, limit=1000):
            if research.get('status') == 'blocked' and research.get('capability_fingerprint') != fingerprint:
                research.update(status='needs_reassessment', reassessment_reason='Available object attributes changed.',
                                previous_capability_fingerprint=research.get('capability_fingerprint'),
                                capability_fingerprint=fingerprint, updated_at=self.repo.clock())
                tx.put(RESEARCH, research)
                reopened.append(research['id'])
        state = {'_id': state_id, 'id': state_id, 'world_id': scope, 'colony_id': colony_id,
                 'capability_fingerprint': fingerprint, 'resident_ids': [record['resident_id'] for record in records],
                 'revision': (old or {}).get('revision', 0) + 1, 'updated_at': self.repo.clock(),
                 'last_change': {'new_resident_ids': new_ids, 'reopened_research_ids': reopened},
                 'retrieval': (old or {}).get('retrieval', {'status': 'exact_only', 'detail': 'Findings are retrieved by exact evidence and text.'})}
        tx.put(STATE, state)
        self._event(tx, scope, key_for(state_id, fingerprint), 'learning.arrival',
                    'New object attributes changed the island’s research possibilities.',
                    data={'new_resident_ids': new_ids, 'reopened_research_ids': reopened,
                          'capability_fingerprint': fingerprint})
        return {'changed': True, 'fingerprint': fingerprint, 'reopened': reopened, 'new_resident_ids': new_ids}

    def _actor(self, tx, scope, actor_id):
        self._scope(scope)
        actor = tx.get('islandAgents', actor_id)
        if not actor:
            actor = next(iter(tx.find('islandAgents', {'world_id': scope, 'character_id': actor_id}, limit=1)), None)
        if not actor or actor.get('world_id') != scope:
            raise StoreError('Only an active resident of this island may conduct research.', 404, 'research_actor_not_found')
        return actor

    def _dossiers(self, tx, scope, identifiers):
        records = []
        for identifier in identifiers:
            row = tx.get(DOSSIERS, key_for(scope, 'object-dossier', identifier))
            if not row or row.get('world_id') != scope:
                raise StoreError('Every experimental participant must belong to this island.', 422, 'experiment_subject_unavailable')
            records.append(row)
        return records

    def _idempotent(self, tx, collection, identifier, fingerprint):
        previous = tx.get(collection, identifier)
        if previous and previous.get('request_fingerprint') != fingerprint:
            raise StoreError('This research request identifier already describes different work.', 409, 'research_request_mismatch')
        return previous

    def run_experiment(self, scope, actor_id, body, request_id):
        return self.repo.transaction(lambda tx: self.run_experiment_tx(tx, scope, actor_id, body, request_id))

    def run_experiment_tx(self, tx, scope, actor_id, body, request_id):
        from .observability import agent_span
        with agent_span('agent.experiment', island_id=self._scope(scope), actor_id=actor_id):
            return self._run_experiment_tx(tx, scope, actor_id, body, request_id)

    def _run_experiment_tx(self, tx, scope, actor_id, body, request_id):
        spec = _validated(ExperimentSpec, body, 'invalid_experiment')
        actor = self._actor(tx, scope, actor_id)
        fingerprint = canonical_digest({'actor_id': actor['id'], 'spec': spec.model_dump()})
        identifier = key_for(scope, 'experiment', str(request_id))
        previous = self._idempotent(tx, EXPERIMENTS, identifier, fingerprint)
        if previous:
            return public_learning(previous)
        dossiers = self._dossiers(tx, scope, spec.subject_ids)
        if actor['character_id'] not in spec.subject_ids:
            raise StoreError('The proposing resident must take part in its experiment.', 422, 'experiment_actor_missing')
        if spec.family == 'contain' and any(
                (row.get('simulation_properties', {}).get('cavity_model') or
                 cavity_model(row.get('observed_evidence', {}).get('visible_features', [])))['status']
                in ('unknown', 'conflicting_evidence') for row in dossiers):
            raise StoreError('This containment test lacks a supported current cavity model. Missing historical features are not evidence of no cavity; refresh the dossier or clarify its evidence first.',
                             422, 'containment_evidence_missing')
        related = tx.get(FINDINGS, spec.reply_to_finding_id) if spec.reply_to_finding_id else None
        if spec.reply_to_finding_id and (not related or related['world_id'] != scope):
            raise StoreError('The cited finding is not evidence from this island.', 422, 'finding_not_found')
        result = simulate_experiment(spec.family, [dossier['_physical_properties'] for dossier in dossiers], spec.context)
        state = tx.get('islandState', key_for(scope, 'island-state'))
        if not state:
            raise StoreError('Start island life before running experiments.', 409, 'island_not_started')
        if state['resources'].get('ideas', 0) < 1:
            self.remember_blocked_tx(tx, scope, actor['id'], spec.hypothesis, ['ideas'], identifier)
            # Return a durable blocked request, not a false experiment finding.
            blocked = {'_id': identifier, 'id': identifier, 'world_id': scope, 'actor_id': actor['id'],
                       'status': 'blocked', 'family': spec.family, 'subject_ids': spec.subject_ids,
                       'hypothesis': spec.hypothesis, 'expected_success': spec.expected_success,
                       'context': context_for(spec.family, spec.context), 'rule_version': RULE_VERSION,
                       'request_fingerprint': fingerprint, 'created_at': self.repo.clock(),
                       'reason': 'One idea is needed to run this test.', 'result': None}
            tx.put(EXPERIMENTS, blocked)
            return public_learning(blocked)
        state['resources']['ideas'] -= 1
        state['revision'] += 1
        tx.put('islandState', state)
        property_fingerprints = [dossier_fingerprint(dossier, spec.family) for dossier in dossiers]
        finding_id = key_for(scope, 'finding', canonical_digest({'family': spec.family, 'subjects': spec.subject_ids,
                             'context': result['context'], 'properties': property_fingerprints, 'rules': RULE_VERSION}))
        timestamp = self.repo.clock()
        experiment = {'_id': identifier, 'id': identifier, 'world_id': scope, 'actor_id': actor['id'],
                      'actor_name': actor['display_name'], 'family': spec.family, 'subject_ids': spec.subject_ids,
                      'hypothesis': spec.hypothesis, 'expected_success': spec.expected_success,
                      'prediction_correct': spec.expected_success == result['success'], 'context': result['context'],
                      'rule_version': RULE_VERSION, 'status': 'completed', 'request_fingerprint': fingerprint,
                      'created_at': timestamp, 'result': result, 'finding_id': finding_id,
                      'cost': {'ideas': 1}, 'property_fingerprints': property_fingerprints,
                      'evidence_version': DOSSIER_EVIDENCE_VERSION,
                      'dossier_revisions': [{'resident_id': row['resident_id'], 'revision': row.get('revision'),
                          'evidence_fingerprint': row.get('evidence_fingerprint'),
                          'cavity_model': deepcopy(row.get('simulation_properties', {}).get('cavity_model')),
                          'reflection_model': deepcopy(row.get('simulation_properties', {}).get('reflection_model'))}
                          for row in dossiers],
                      'reply_to_finding_id': spec.reply_to_finding_id}
        tx.put(EXPERIMENTS, experiment)
        finding = tx.get(FINDINGS, finding_id)
        if not finding:
            finding = {'_id': finding_id, 'id': finding_id, 'world_id': scope, 'rule_version': RULE_VERSION,
                       'family': spec.family, 'subject_ids': spec.subject_ids, 'context': result['context'],
                       'property_fingerprints': property_fingerprints,
                       'status': 'tested_in_sim', 'success': result['success'], 'claim': result['summary'],
                       'measurements': result['measurements'], 'created_at': timestamp,
                       'supporting_experiment_ids': [], 'boundary_evidence_ids': [],
                       'interpretation': 'Applies only to these simulation conditions; transfer needs another test.'}
        # Repetition is provenance, not an increase in confidence or new powers.
        finding['supporting_experiment_ids'] = list(dict.fromkeys([*finding['supporting_experiment_ids'], identifier]))[-32:]
        finding['updated_at'] = timestamp
        from .observability import agent_span
        with agent_span('agent.learning.update', island_id=self._scope(scope), actor_id=actor['id'], finding_id=finding_id):
            tx.put(FINDINGS, finding)
        if related and related['id'] != finding_id:
            related['boundary_evidence_ids'] = list(dict.fromkeys([*related.get('boundary_evidence_ids', []), identifier]))[-32:]
            related['updated_at'] = timestamp
            tx.put(FINDINGS, related)
        for dossier in dossiers:
            dossier['finding_ids'] = list(dict.fromkeys([*dossier['finding_ids'], finding_id]))[-64:]
            if result['success']:
                capability = {'family': spec.family, 'context': result['context'], 'finding_id': finding_id,
                              'rule_version': RULE_VERSION, 'authority': 'tested_simulation_only'}
                dossier['tested_capabilities'] = [row for row in dossier['tested_capabilities'] if row['finding_id'] != finding_id]
                dossier['tested_capabilities'] = [*dossier['tested_capabilities'], capability][-32:]
            tx.put(DOSSIERS, dossier)
        self._event(tx, scope, identifier, 'experiment.completed', result['summary'], actor=actor,
                    data={'experiment_id': identifier, 'finding_id': finding_id, 'family': spec.family,
                          'expected_success': spec.expected_success, 'success': result['success'],
                          'prediction_correct': experiment['prediction_correct'], 'measurements': result['measurements']})
        self._event(tx, scope, key_for(identifier, 'memory'), 'memory.updated',
                    'Recorded experimental evidence with its tested conditions.', actor=actor,
                    data={'finding_id': finding_id, 'experiment_id': identifier, 'context': result['context']})
        return public_learning(experiment)

    def remember_blocked_tx(self, tx, scope, actor_id, goal, missing, request_id):
        actor = self._actor(tx, scope, actor_id)
        state = tx.get(STATE, key_for(scope, 'learning-state')) or {}
        identifier = key_for(scope, 'research', request_id)
        research = {'_id': identifier, 'id': identifier, 'world_id': scope, 'actor_id': actor['id'],
                    'goal': str(goal)[:400], 'status': 'blocked', 'missing': [str(item)[:80] for item in missing][:12],
                    'capability_fingerprint': state.get('capability_fingerprint'), 'created_at': self.repo.clock(),
                    'updated_at': self.repo.clock()}
        tx.put(RESEARCH, research)
        return public_learning(research)

    def propose_blueprint(self, scope, actor_id, body, request_id):
        return self.repo.transaction(lambda tx: self.propose_blueprint_tx(tx, scope, actor_id, body, request_id))

    def propose_blueprint_tx(self, tx, scope, actor_id, body, request_id):
        proposal = _validated(BlueprintProposal, body, 'invalid_blueprint')
        actor = self._actor(tx, scope, actor_id)
        identifier = key_for(scope, 'blueprint', str(request_id))
        fingerprint = canonical_digest({'actor_id': actor['id'], 'blueprint': proposal.model_dump()})
        previous = self._idempotent(tx, BLUEPRINTS, identifier, fingerprint)
        if previous:
            return public_learning(previous)
        experiment = tx.get(EXPERIMENTS, proposal.experiment_id)
        if not experiment or experiment['world_id'] != scope:
            raise StoreError('The cited experiment is not from this island.', 422, 'experiment_not_found')
        dossiers = self._dossiers(tx, scope, [part.resident_id for part in proposal.parts])
        if actor['character_id'] not in [row['resident_id'] for row in dossiers]:
            raise StoreError('A resident must contribute to the construction it proposes.', 422, 'blueprint_actor_missing')
        validated = validate_blueprint(proposal, {row['resident_id']: row for row in dossiers}, experiment)
        if proposal.family == 'reflect' and not any(
                'signal' in resident.get('allowed_actions', []) and
                resident.get('action_yields', {}).get('signal', {}).get('ideas', 0) > 0
                for resident in tx.find('islandAgents', {'world_id': scope}, limit=80)):
            raise StoreError('A signal relay needs an existing crew member with the signal action. '
                             'The construction improves that work; it cannot grant observation powers.',
                             422, 'blueprint_beneficiary_missing')
        state = tx.get('islandState', key_for(scope, 'island-state')) or {}
        benefit = validated['benefit']
        actions = set(benefit.get('eligible_actions', []))
        if (benefit.get('kind') == 'task_yield_bonus' and actions
                and actions <= _covered_structure_actions(state.get('projects', []), benefit['resource'])):
            raise StoreError('An existing or planned structure already covers this capped bonus. '
                             'Choose a construction that adds a missing benefit or test a different capability.',
                             422, 'duplicate_structure_benefit')
        if len([project for project in state.get('projects', []) if project.get('kind') == 'assembly']) >= 12:
            raise StoreError('This island has room for twelve constructed experiments.', 409, 'assembly_limit')
        position = {'x': proposal.position.x, 'z': proposal.position.z}
        if proposal.position.y != 0 or math.hypot(position['x'], position['z']) > 3.4:
            raise StoreError('Construction must be grounded inside the island.', 422, 'invalid_construction_position')
        if any(math.hypot(project['position']['x'] - position['x'], project['position']['z'] - position['z']) < .65
               for project in state.get('projects', [])):
            raise StoreError('This construction overlaps an existing project.', 422, 'construction_overlap')
        blueprint = {'_id': identifier, 'id': identifier, 'world_id': scope, 'actor_id': actor['id'],
                     'name': proposal.name, 'purpose': proposal.purpose, 'family': proposal.family,
                     'experiment_id': experiment['id'], 'finding_id': experiment['finding_id'],
                     'status': 'proposed', 'created_at': self.repo.clock(), 'request_fingerprint': fingerprint,
                     'rule_version': RULE_VERSION, **validated}
        project_id = 'assembly-' + identifier[:20]
        project = {'id': project_id, 'kind': 'assembly', 'name': proposal.name, 'description': proposal.purpose,
                   'position': position, 'base_progress': validated['work_required'],
                   'required_progress': validated['work_required'], 'progress': 0, 'reserved_progress': 0,
                   'workers': [], 'level': 0, 'max_level': 1, 'status': 'planned',
                   'cost_per_action': validated['cost_per_action'],
                   'reward': '+1 ' + validated['benefit']['resource'] + ' on eligible completed tasks; total bonus capped at one.',
                   'blueprint_id': identifier, 'assembly': {'family': proposal.family, 'parts': validated['parts'],
                                                          'context': validated['context']}, 'benefit': validated['benefit']}
        blueprint['project'] = project
        blueprint['missing_resources'] = [resource for resource, amount in validated['maximum_cost_at_base_work'].items()
                                          if state.get('resources', {}).get(resource, 0) < amount]
        if blueprint['missing_resources']:
            self.remember_blocked_tx(tx, scope, actor['id'], proposal.purpose, blueprint['missing_resources'], identifier)
        tx.put(BLUEPRINTS, blueprint)
        self._event(tx, scope, identifier, 'blueprint.proposed', 'A tested construction is ready for crew agreement.',
                    actor=actor, data={'blueprint_id': identifier, 'project_id': project_id,
                                      'experiment_id': experiment['id'], 'cost_per_action': validated['cost_per_action']})
        return public_learning(blueprint)

    def complete_blueprint_tx(self, tx, scope, project):
        """Called after an executor has actually finished the reserved build work."""
        self._scope(scope)
        if project.get('kind') != 'assembly' or project.get('level', 0) < project.get('max_level', 1):
            return None
        blueprint = tx.get(BLUEPRINTS, project.get('blueprint_id', ''))
        if not blueprint or blueprint['world_id'] != scope or blueprint['project']['id'] != project['id']:
            raise StoreError('Completed construction has no validated blueprint.', 503, 'blueprint_invariant')
        if blueprint['status'] == 'completed':
            return public_learning(blueprint)
        blueprint.update(status='completed', completed_at=self.repo.clock())
        tx.put(BLUEPRINTS, blueprint)
        self._event(tx, scope, key_for(blueprint['id'], 'completed'), 'blueprint.completed',
                    'The crew completed a tested construction.', data={'blueprint_id': blueprint['id'], 'project_id': project['id'],
                                                                      'benefit': blueprint['benefit']})
        return public_learning(blueprint)

    def structure_bonus(self, tx, scope, action):
        self._scope(scope)
        for blueprint in tx.find(BLUEPRINTS, {'world_id': scope, 'status': 'completed'}, limit=12):
            benefit = blueprint['benefit']
            if action in benefit['eligible_actions']:
                return {benefit['resource']: 1}
        return {}

    def snapshot_tx(self, tx, scope):
        self._scope(scope)
        state = tx.get(STATE, key_for(scope, 'learning-state')) or {}
        dossiers = tx.find(DOSSIERS, {'world_id': scope}, limit=80)
        by_id = {row['resident_id']: row for row in dossiers}
        findings = [annotated_evidence(row, by_id) for row in tx.find(FINDINGS, {'world_id': scope}, 'updated_at', 80)]
        return public_learning({'rule_version': RULE_VERSION, 'capability_fingerprint': state.get('capability_fingerprint'),
                                'tools': {
                                    'experiment': {'cost': {'ideas': 1}, 'subject_id_field': 'character_id',
                                        'actor_must_participate': True, 'families': {
                                            'hold': {'purpose': 'Keep an arrangement stable under wind.', 'context_fields': ['wind_force', 'load', 'duration']},
                                            'contain': {'purpose': 'Deliver at least 85% of a specified liquid load.', 'context_fields': ['volume', 'distance', 'tilt_degrees']},
                                            'support': {'purpose': 'Cover a span within load and deflection limits.', 'context_fields': ['span', 'load', 'support_count']},
                                            'reflect': {'purpose': 'Redirect existing test light to improve signal contrast. Requires accepted visible reflective-surface evidence; load is background interference, tilt is alignment error. Does not create energy or grant signal.',
                                                        'context_fields': ['distance', 'load', 'tilt_degrees']}},
                                        'support_rule': 'First subject spans two banks; each extra subject can provide one intermediate support.'},
                                    'blueprint': {'requires': 'Successful current-version experiment of the same ordered resident IDs.',
                                        'production_benchmarks': deepcopy(PRODUCTION_BENCHMARKS),
                                        'production_rule': 'An experiment must succeed at these minimum operating conditions before its blueprint can earn a normal-work bonus. Easier tests remain valid prototypes; retest them.',
                                        'maximum_parts': 12, 'primary_kinds': deepcopy(PRIMARY_KINDS),
                                        'arrangement': 'Primary part at (0,0,0); extra part i at x=(i/part_count-0.5)*tested_span, y=z=0. All rotations zero.',
                                        'construction': 'Costs and bonus are calculated by the server. Crew agreement and actual reserved build work are required.'},
                                    'truth_boundary': 'Physical properties are simulation assumptions. Missing observations are unknown, not proof of absence. Declared game capabilities may supply a separately labelled proxy; changed proxies need a new test. Repetition does not increase confidence.'},
                                'last_change': state.get('last_change'), 'retrieval': state.get('retrieval', {'status': 'exact_only'}),
                                'dossiers': dossiers,
                                'findings': [row for row in findings if row['evidence_status'] == 'current'][:40],
                                'historical_findings': [row for row in findings if row['evidence_status'] != 'current'][:24],
                                'experiments': [annotated_evidence(row, by_id) for row in tx.find(EXPERIMENTS, {'world_id': scope}, 'created_at', 30)],
                                'blueprints': tx.find(BLUEPRINTS, {'world_id': scope}, 'created_at', 24),
                                'research': tx.find(RESEARCH, {'world_id': scope}, 'updated_at', 24)})

    def snapshot(self, scope):
        return self.repo.read(lambda tx: self.snapshot_tx(tx, scope))

    def knowledge(self, scope, query='', limit=6):
        self._scope(scope)
        terms = set(re.findall(r'[a-z0-9]+', query.lower()))
        def retrieve(tx):
            dossiers = {row['resident_id']: row for row in tx.find(DOSSIERS, {'world_id': scope}, limit=80)}
            rows = tx.find(FINDINGS, {'world_id': scope, 'rule_version': RULE_VERSION}, 'updated_at', MAX_FINDINGS)
            rows = [row for row in rows if evidence_status(row, dossiers) == 'current']
            rows.sort(key=lambda row: (len(terms.intersection(re.findall(r'[a-z0-9]+', self.finding_text(row).lower()))), row['updated_at']), reverse=True)
            return {'status': 'exact_only', 'detail': 'Evidence-scoped text matching; vector search was not used.',
                    'findings': public_learning(rows[:max(1, min(12, limit))])}
        return self.repo.read(retrieve)

    @staticmethod
    def finding_text(finding):
        return (f"{finding['family']}: {finding['claim']} Conditions: {finding['context']}. "
                f"Measurements: {finding['measurements']}. Simulation rules: {finding['rule_version']}.")[:1200]

    async def prepare_embeddings(self, scope, embedder, limit=12):
        """Explicit event-driven preparation; never called by a simulation tick.

        Inject the application's existing AtlasRetriever to share its documented
        Gemini preprocessing, caching and provider queue. No SDK client lives here.
        """
        self._scope(scope)
        if not hasattr(self.repo, 'db') or embedder is None:
            return {'status': 'exact_only', 'prepared': 0, 'detail': 'Atlas embedding preparation is unavailable.'}
        def current_findings(tx):
            dossiers = {row['resident_id']: row for row in tx.find(DOSSIERS, {'world_id': scope}, limit=80)}
            return [row for row in tx.find(FINDINGS, {'world_id': scope, 'rule_version': RULE_VERSION}, 'updated_at', MAX_FINDINGS)
                    if evidence_status(row, dossiers) == 'current']
        rows = await asyncio.to_thread(self.repo.read, current_findings)
        prepared = 0
        for finding in rows:
            text = self.finding_text(finding)
            digest = canonical_digest({'text': text, 'model': embedder.config.model, 'dimensions': embedder.config.dimensions})
            if finding.get('embedding_content_hash') == digest:
                continue
            vector = await embedder.embed(text, document=True, title='Island experiment evidence')
            def save(tx):
                current = tx.get(FINDINGS, finding['id'])
                if not current or self.finding_text(current) != text:
                    return False
                current.update(embedding=vector, embedding_model=embedder.config.model,
                               embedding_dimensions=embedder.config.dimensions, embedding_content_hash=digest)
                tx.put(FINDINGS, current)
                return True
            prepared += int(await asyncio.to_thread(self.repo.transaction, save))
            if prepared >= max(1, min(32, limit)):
                break
        return {'status': 'prepared', 'prepared': prepared, 'model': embedder.config.model}

    async def retrieve(self, scope, query, embedder=None, limit=6):
        exact = await asyncio.to_thread(self.knowledge, scope, query, limit)
        if not hasattr(self.repo, 'db') or embedder is None:
            return exact
        try:
            collection = self.repo.db[FINDINGS]
            indexes = await asyncio.to_thread(lambda: list(collection.list_search_indexes(name=VECTOR_INDEX)))
            if not any(row.get('queryable') is True for row in indexes):
                return {**exact, 'status': 'vector_index_unavailable', 'detail': 'Vector index is not ready; exact evidence was retrieved.'}
            enrolled = await asyncio.to_thread(self.repo.read, lambda tx: tx.find(FINDINGS,
                {'world_id': scope, 'rule_version': RULE_VERSION, 'embedding_model': embedder.config.model,
                 'embedding_dimensions': embedder.config.dimensions}, limit=1))
            if not enrolled:
                return {**exact, 'status': 'vector_not_enrolled', 'detail': 'Evidence has not been embedded; exact retrieval remains available.'}
            vector = await embedder.embed(query)
            count = max(1, min(12, limit))
            pipeline = [{'$vectorSearch': {'index': VECTOR_INDEX, 'path': 'embedding', 'queryVector': vector,
                         'numCandidates': max(40, count * 10), 'limit': count,
                         'filter': {'world_id': scope, 'rule_version': RULE_VERSION, 'status': 'tested_in_sim',
                                    'embedding_model': embedder.config.model, 'embedding_dimensions': embedder.config.dimensions}}},
                        {'$project': {'id': 1, 'score': {'$meta': 'vectorSearchScore'}}}]
            matches = await asyncio.to_thread(lambda: list(collection.aggregate(pipeline, maxTimeMS=5000)))
            def resolve(tx):
                result = []
                dossiers = {row['resident_id']: row for row in tx.find(DOSSIERS, {'world_id': scope}, limit=80)}
                for match in matches:
                    finding = tx.get(FINDINGS, match['id'])
                    if finding and finding.get('world_id') == scope and evidence_status(finding, dossiers) == 'current':
                        result.append({**public_learning(finding), 'retrieval_score': match['score']})
                return result
            findings = await asyncio.to_thread(self.repo.read, resolve)
            return {'status': 'atlas_vector_search', 'detail': 'Similarity retrieved exact, island-scoped experiment evidence.',
                    'findings': findings, 'model': embedder.config.model}
        except Exception as exc:
            return {**exact, 'status': 'vector_unavailable', 'error_category': type(exc).__name__,
                    'detail': 'Vector retrieval failed; exact evidence remains available.'}
