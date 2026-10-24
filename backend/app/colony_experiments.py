"""Bounded analytical island experiments, not claims about real-world physics.

The evaluator consumes numeric properties and arrangements, never object labels,
prices, dialogue or a model-supplied reward. All units are simulation units.
"""
from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json
import math
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .repository import StoreError

RULE_VERSION = 'island-laboratory-v1'
DOSSIER_EVIDENCE_VERSION = 'island-evidence-v2'
BENCHMARK_VERSION = 'island-production-v1'
# Normal island work has a declared bounded operating envelope. Passing a tiny
# prototype test does not authorize a bonus for that normal production workload.
PRODUCTION_BENCHMARKS = {
    'hold': {'wind_force': 1, 'load': 1, 'duration': 10},
    'contain': {'volume': .3, 'distance': 2},
    'support': {'span': .6, 'load': .2},
}
Family = Literal['hold', 'contain', 'support']


class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)


class ExperimentContext(StrictModel):
    wind_force: float = Field(default=1, ge=0, le=20)
    load: float = Field(default=1, gt=0, le=30)
    duration: float = Field(default=10, ge=1, le=60)
    span: float = Field(default=.6, ge=.1, le=4)
    volume: float = Field(default=.3, gt=0, le=10)
    distance: float = Field(default=2, ge=0, le=10)
    support_count: int = Field(default=2, ge=2, le=12, strict=True)
    tilt_degrees: float = Field(default=0, ge=0, le=70)


class ExperimentSpec(StrictModel):
    family: Family
    subject_ids: list[str] = Field(min_length=1, max_length=12)
    hypothesis: str = Field(min_length=5, max_length=400)
    expected_success: bool
    context: ExperimentContext = Field(default_factory=ExperimentContext)
    reply_to_finding_id: str | None = Field(default=None, max_length=128)

    @model_validator(mode='after')
    def unique_subjects(self):
        if len(set(self.subject_ids)) != len(self.subject_ids):
            raise ValueError('One physical resident cannot be duplicated in an experiment.')
        return self


class PartPosition(StrictModel):
    x: float = Field(default=0, ge=-3, le=3)
    y: float = Field(default=0, ge=0, le=3)
    z: float = Field(default=0, ge=-3, le=3)


class AssemblyPart(StrictModel):
    kind: Literal['beam', 'panel', 'vessel', 'connector']
    resident_id: str = Field(min_length=1, max_length=128)
    position: PartPosition = Field(default_factory=PartPosition)
    rotation: Literal[0, 90] = 0


class BlueprintProposal(StrictModel):
    name: str = Field(min_length=3, max_length=80)
    purpose: str = Field(min_length=8, max_length=300)
    family: Family
    parts: list[AssemblyPart] = Field(min_length=1, max_length=12)
    experiment_id: str = Field(min_length=1, max_length=128,
                              description='A successful current-version experiment whose result.production_validation.eligible is true; low-load prototypes need a production benchmark retest.')
    position: PartPosition = Field(default_factory=lambda: PartPosition(x=0, z=-.8))

    @model_validator(mode='after')
    def unique_sources(self):
        if len({part.resident_id for part in self.parts}) != len(self.parts):
            raise ValueError('Each source resident contributes one tested part design.')
        return self


def canonical_digest(value: dict | list) -> str:
    return sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()).hexdigest()


def context_for(family: str, context: dict | ExperimentContext) -> dict:
    value = context if isinstance(context, ExperimentContext) else ExperimentContext.model_validate(context)
    keys = {'hold': ('wind_force', 'load', 'duration'),
            'contain': ('volume', 'distance', 'tilt_degrees'),
            'support': ('span', 'load', 'support_count')}[family]
    return {key: getattr(value, key) for key in keys}


def production_validation(family: str, context: dict, success: bool) -> dict:
    required = PRODUCTION_BENCHMARKS[family]
    unmet = [{'field': field, 'required_minimum': minimum, 'observed': context.get(field)}
             for field, minimum in required.items() if context.get(field, -1) < minimum]
    return {'eligible': bool(success and not unmet), 'benchmark_version': BENCHMARK_VERSION,
            'required_context': deepcopy(required), 'unmet_requirements': unmet,
            'detail': ('The tested arrangement covers the declared normal island workload.' if success and not unmet else
                       'A successful production benchmark is still required; this result remains valid only for its tested conditions.')}


def cavity_model(features: list[str], capabilities: list[str] | None = None) -> dict:
    """Keep a missing photograph distinct from an authored game capability.

    Existing capabilities can justify a simulated vessel, but do not become
    observations about the photographed object. Explicit negative or conflicting
    evidence is never overridden by a capability or an object name.
    """
    positive, negative = [], []
    for feature in features:
        text = str(feature).lower()
        absence = re.search(r'\b(no|without|lacks?)(?:\s+\w+){0,2}\s+cavit(?:y|ies)\b|\b(?:not|non[- ]?)\s*hollow\b|\b(?:solid block|solid slab|fully solid|solid metal rectangular body)\b', text)
        # Negated cavity language must not match the positive cue within it.
        if absence:
            negative.append(str(feature))
        elif (re.search(r'\b(hollow|open[- ]top|opening|concave|container|vessel|reservoir|cavity)\b', text)
              and not re.search(r'\b(no|not|without|lacks?)(?:\s+\w+){0,2}\s+(hollow|open[- ]top|opening|concave|container|vessel|reservoir|cavity)\b', text)):
            positive.append(str(feature))
    declared = sorted(set(capabilities or []).intersection({'contain_water', 'store_water'}))
    if positive and negative:
        return {'status': 'conflicting_evidence', 'authority': 'accepted_visible_features',
                'evidence': positive + negative, 'detail': 'Recorded shape cues disagree; containment needs clarified evidence.'}
    if positive:
        return {'status': 'observed_cavity', 'authority': 'accepted_visible_features',
                'evidence': positive, 'detail': 'A cavity is suggested by accepted visible features; capacity and leakage remain simulation assumptions.'}
    if negative:
        return {'status': 'observed_absence', 'authority': 'accepted_visible_features',
                'evidence': negative, 'detail': 'Recorded shape evidence explicitly describes a solid proxy without a cavity.'}
    if declared:
        return {'status': 'declared_simulation_cavity', 'authority': 'declared_game_capability',
                'evidence': declared, 'detail': 'An existing water-storage capability permits an authored vessel in this simulation. No photograph observation was recovered; a new test is still required.'}
    return {'status': 'unknown', 'authority': 'missing_evidence', 'evidence': [],
            'detail': 'No cavity observation or declared water-storage capability is available. Missing evidence does not establish a solid object.'}


def physical_property_fingerprint(properties: dict) -> str:
    # Evidence provenance is versioned separately from the numerical testbed.
    return canonical_digest({key: value for key, value in properties.items()
                             if not key.startswith('_') and key != 'provenance'})


def physical_properties(features: list[str], visual_spec: dict | None = None,
                        capabilities: list[str] | None = None) -> dict:
    """Author stable testbed properties from accepted visual evidence.

    Shape cues come from visible_features, not the canonical label. Stiffness,
    friction, mass and leak rate are authored hidden properties; even an apparent
    material is a simulation assumption, not a measured material diagnosis.
    Identical evidence gives identical properties under a renamed object.
    """
    text = ' '.join(str(feature).lower() for feature in features)
    proportions = (visual_spec or {}).get('proportions', {})
    width = max(.3, min(1.5, float(proportions.get('width', 1))))
    height = max(.2, min(1.5, float(proportions.get('height', 1))))
    depth, length = width * .65, width
    if any(cue in text for cue in ('flat', 'thin', 'slender', 'elongated', 'long narrow', 'rectangular strip')):
        height, length = .12 * height, 1.8 * width
    if any(cue in text for cue in ('tall', 'vertical')):
        height *= 1.35
    cavity = cavity_model(features, capabilities)
    hollow = cavity['status'] in ('observed_cavity', 'declared_simulation_cavity')
    material = next((kind for kind in ('metal', 'ceramic', 'glass', 'wood', 'plastic', 'paper', 'fabric') if kind in text), 'unknown')
    # No identity fields or random display seed participate in physics.
    seed = int(canonical_digest({'features': sorted(features), 'width': width, 'height': height})[:8], 16)
    density, stiffness, permeability = {
        'metal': (2.8, 90, .001), 'ceramic': (2.2, 60, .002),
        'glass': (2.1, 55, .001), 'wood': (.8, 45, .03),
        'plastic': (.65, 28, .004), 'paper': (.3, 4, .22),
        'fabric': (.25, 1.5, .28), 'unknown': (1, 18, .04),
    }[material]
    variation = .9 + (seed % 21) / 100
    return {'width': round(width, 5), 'height': round(height, 5), 'depth': round(depth, 5),
            'length': round(length, 5), 'mass': round(max(.08, width * height * depth * density * variation), 5),
            'stiffness': round(stiffness * variation, 5), 'friction': round(.35 + (seed % 30) / 100, 5),
            'capacity': round(width * height * depth * .7 if hollow else 0, 5),
            'leak_rate': permeability, 'material_assumption': material,
            'provenance': ('authored_simulation_proxy_from_declared_game_capability' if cavity['status'] == 'declared_simulation_cavity' else
                           'authored_simulation_parameters_from_accepted_visible_features' if features else
                           'authored_generic_simulation_proxy_without_recorded_shape_evidence'),
            '_cavity_status': cavity['status'], '_cavity_authority': cavity['authority']}


def _numeric_properties(properties: list[dict]) -> list[dict]:
    if not 1 <= len(properties) <= 12:
        raise StoreError('An experiment needs one to twelve physical participants.', 422, 'invalid_experiment')
    result = []
    for original in properties:
        value = deepcopy(original)
        for field in ('width', 'height', 'depth', 'length', 'mass', 'stiffness', 'friction', 'capacity', 'leak_rate'):
            number = value.get(field)
            if isinstance(number, bool) or not isinstance(number, (float, int)) or not math.isfinite(number) or number < 0:
                raise StoreError('Simulation properties must be finite nonnegative values.', 422, 'invalid_physical_properties')
        if min(value['width'], value['height'], value['length'], value['mass'], value['stiffness']) <= 0:
            raise StoreError('Simulation geometry and material parameters must be positive.', 422, 'invalid_physical_properties')
        result.append(value)
    return result


def simulate_experiment(family: str, properties: list[dict], context: dict | ExperimentContext) -> dict:
    """Pure, replayable evaluation; no stock, memory, labels or network access."""
    if family not in ('hold', 'contain', 'support'):
        raise StoreError('Unknown experiment family.', 422, 'invalid_experiment')
    p = _numeric_properties(properties)
    c = context_for(family, context)
    if family == 'hold':
        mass = sum(row['mass'] for row in p)
        grip = sum(row['mass'] * 9.81 * row['friction'] for row in p)
        restoring = sum(row['mass'] * 9.81 * row['width'] / 2 for row in p)
        wind = c['wind_force'] * (1 + c['load'] * .1)
        tipping = wind * max(row['height'] for row in p) / 2
        sliding_margin = grip - wind
        tipping_margin = restoring - tipping
        displacement = max(0, wind - grip) / mass * c['duration'] ** 2 / 2
        success = sliding_margin >= 0 and tipping_margin >= 0
        measures = {'sliding_margin': sliding_margin, 'tipping_margin': tipping_margin,
                    'displacement': displacement, 'held_seconds': c['duration'] if success else 0}
        reason = 'The arrangement stayed in place.' if success else 'The arrangement slid or tipped under the specified wind and load.'
    elif family == 'contain':
        if any(row.get('_cavity_status') in ('unknown', 'conflicting_evidence') for row in p):
            raise StoreError('Cavity evidence is unknown or conflicting. Clarify the recorded shape evidence or use an already declared water-storage capability; no failed physical finding was created.',
                             422, 'containment_evidence_missing')
        # Tilt changes the usable cavity; travel loss is proportional to leakage.
        tilt_factor = max(0, math.cos(math.radians(c['tilt_degrees'])) ** 2)
        capacities = [row['capacity'] * tilt_factor for row in p]
        usable = sum(capacities)
        initial = min(c['volume'], usable)
        leak = sum(row['leak_rate'] * capacities[i] for i, row in enumerate(p)) / usable if usable else 1
        retained = max(0, initial * (1 - min(1, leak * (1 + c['distance']))))
        spilled = c['volume'] - retained
        success = retained >= .85 * c['volume']
        measures = {'usable_capacity': usable, 'retained_volume': retained, 'spilled_volume': spilled,
                    'delivery_fraction': retained / c['volume']}
        reason = 'At least 85% of the load arrived.' if success else 'The cavity, tilt or leakage prevented the required delivery.'
    else:
        # The first subject spans two banks. Further subjects may add intermediate
        # supports; an invented support_count cannot summon extra residents.
        available_supports = len(p) + 1
        if c['support_count'] > available_supports:
            raise StoreError('Intermediate supports require additional physical participants.', 422, 'missing_support')
        beam = p[0]
        clear_span = c['span'] / (c['support_count'] - 1)
        inertia = beam['width'] * beam['height'] ** 3 / 12
        deflection = c['load'] * clear_span ** 3 / max(1e-8, 48 * beam['stiffness'] * inertia)
        strength = beam['stiffness'] * beam['width'] * beam['height'] ** 2 / (6 * clear_span)
        support_strength = min((row['mass'] * 9.81 + row['stiffness'] * row['width'] * row['depth'] for row in p[1:]), default=1e6)
        capacity = min(strength, support_strength)
        spans = beam['length'] >= c['span']
        success = spans and capacity >= c['load'] and deflection <= clear_span * .08
        measures = {'clear_span': clear_span, 'deflection': deflection, 'deflection_limit': clear_span * .08,
                    'supported_load': capacity, 'required_load': c['load'], 'span_covered': spans}
        reason = 'The span stayed within its load and deflection limits.' if success else 'The span was too short, overloaded or bent beyond its allowed deflection.'
    rounded = {key: round(value, 6) if isinstance(value, float) else value for key, value in measures.items()}
    return {'rule_version': RULE_VERSION, 'family': family, 'context': c, 'success': success,
            'measurements': rounded, 'summary': reason, 'authority': 'deterministic_simulation',
            'production_validation': production_validation(family, c, success),
            'replay': {'duration_seconds': min(8, c.get('duration', 4)),
                       'motion': {'hold': 'wind_test', 'contain': 'transfer_test', 'support': 'load_test'}[family],
                       'measurements': rounded}}


BENEFITS = {
    'hold': {'kind': 'task_yield_bonus', 'resource': 'ideas', 'eligible_actions': ['plan', 'measure'], 'amount': 1},
    'contain': {'kind': 'task_yield_bonus', 'resource': 'water', 'eligible_actions': ['water'], 'amount': 1},
    'support': {'kind': 'task_yield_bonus', 'resource': 'materials', 'eligible_actions': ['carry', 'forage'], 'amount': 1},
}


def validate_blueprint(proposal: BlueprintProposal | dict, dossiers: dict[str, dict], experiment: dict) -> dict:
    """Costed design derived only from a successful same-arrangement test.

    Residents inspire reusable manufactured shapes; they are not consumed or
    cloned. Parts use island materials. This is a construction recipe, not an
    arbitrary model-authored physics script.
    """
    value = proposal if isinstance(proposal, BlueprintProposal) else BlueprintProposal.model_validate(proposal)
    ids = [part.resident_id for part in value.parts]
    if any(identifier not in dossiers for identifier in ids):
        raise StoreError('Every part must reference a resident from this island.', 422, 'blueprint_part_unavailable')
    if (not experiment.get('result', {}).get('success') or experiment.get('rule_version') != RULE_VERSION
            or experiment.get('family') != value.family or experiment.get('subject_ids') != ids):
        raise StoreError('A construction needs a successful current-version test of these ordered participants.', 422, 'blueprint_evidence_mismatch')
    if experiment.get('property_fingerprints') != [dossiers[identifier]['property_fingerprint'] for identifier in ids]:
        raise StoreError('The tested objects changed; this design needs a new experiment.', 422, 'blueprint_evidence_stale')
    if value.family == 'contain' and any(
            (dossiers[identifier].get('simulation_properties', {}).get('cavity_model') or
             cavity_model(dossiers[identifier].get('observed_evidence', {}).get('visible_features', [])))['status']
            in ('unknown', 'conflicting_evidence') for identifier in ids):
        raise StoreError('Containment needs a supported current cavity model and a successful test of it.', 422, 'containment_evidence_missing')
    operational = production_validation(value.family, experiment['context'], experiment['result']['success'])
    if not operational['eligible']:
        missing = ', '.join(f"{row['field']} >= {row['required_minimum']}" for row in operational['unmet_requirements'])
        raise StoreError('This prototype has not covered normal island work. Run a successful retest with ' + missing +
                         ' before proposing a production construction.', 422, 'production_benchmark_not_met')
    primary = {'hold': {'panel', 'connector'}, 'contain': {'vessel'}, 'support': {'beam', 'panel'}}[value.family]
    if value.parts[0].kind not in primary:
        raise StoreError('The first construction part must match the tested function.', 422, 'blueprint_function_mismatch')
    # Only this canonical arrangement has been tested. Coordinates are not a way
    # to turn a successful small experiment into an untested arbitrary structure.
    for index, part in enumerate(value.parts):
        expected_x = 0 if index == 0 else round((index / len(value.parts) - .5) * experiment['context'].get('span', .6), 4)
        if abs(part.position.x - expected_x) > .001 or part.position.y != 0 or part.position.z != 0 or part.rotation != 0:
            raise StoreError('Part positions must use the tested arrangement (primary at origin; supports along the span).', 422, 'untested_arrangement')
    materials = sum(max(1, math.ceil(dossiers[part.resident_id]['simulation_properties']['geometry']['width'] *
                                      dossiers[part.resident_id]['simulation_properties']['geometry']['length'] * 2)) for part in value.parts)
    work = max(4, len(value.parts) * 4)
    actions = math.ceil(work / 2)
    per_action = {'materials': max(1, math.ceil(materials / actions)), 'ideas': 1}
    parts = [{**part.model_dump(), 'geometry': deepcopy(dossiers[part.resident_id]['simulation_properties']['geometry']),
              'material_assumption': dossiers[part.resident_id]['simulation_properties']['material_assumption']}
             for part in value.parts]
    benefit = {**deepcopy(BENEFITS[value.family]), 'benchmark_version': BENCHMARK_VERSION,
               'operating_context': deepcopy(PRODUCTION_BENCHMARKS[value.family])}
    return {'parts': parts, 'work_required': work,
            'cost_per_action': per_action, 'minimum_actions': actions,
            'maximum_cost_at_base_work': {resource: amount * actions for resource, amount in per_action.items()},
            'benefit': benefit, 'context': deepcopy(experiment['context']),
            'rule_version': RULE_VERSION, 'manufacturing_basis': 'island_materials_reproduce_tested_shape_assumptions'}
