"""Bounded facts that help a council turn existing stock and evidence into work.

This is observation preparation, not a planner: it does not choose a project,
create a model message, grant a capability, or change the world. The existing
executor and blueprint validator remain authoritative when a decision arrives.
"""
from __future__ import annotations

from copy import deepcopy
import math

from .colony_experiments import BENEFITS, PRODUCTION_BENCHMARKS, RULE_VERSION, context_for, validate_blueprint
from .repository import StoreError

PRIMARY_KINDS = {'hold': ['panel', 'connector'], 'contain': ['vessel'], 'support': ['beam', 'panel']}


def _rows(value):
    return [row for row in value if isinstance(row, dict)] if isinstance(value, list) else []


def _number(value, default=0):
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) else default


def _complete(project):
    return _number(project.get('level')) >= _number(project.get('max_level'), 1)


def _coverage(projects, crew_actions):
    """Task bonuses are capped at one, not multiplied by matching buildings."""
    rows = []
    for family, benefit in BENEFITS.items():
        matches = [project for project in projects if project.get('kind') == 'assembly'
                   and project.get('status') in ('planned', 'building', 'complete')
                   and project.get('benefit', {}).get('kind') == 'task_yield_bonus'
                   and _number(project.get('benefit', {}).get('amount')) >= 1
                   and project.get('benefit', {}).get('resource') == benefit['resource']
                   and set(project.get('benefit', {}).get('eligible_actions', [])).intersection(benefit['eligible_actions'])]
        completed = [project for project in matches if _complete(project)]
        provided = set().union(*(set(project.get('benefit', {}).get('eligible_actions', [])) for project in completed))
        planned = set().union(*(set(project.get('benefit', {}).get('eligible_actions', [])) for project in matches if not _complete(project)))
        rows.append({'family': family, 'resource': benefit['resource'], 'amount_cap_per_task': 1,
                     'eligible_crew_actions': sorted(set(benefit['eligible_actions']).intersection(crew_actions)),
                     'already_provided_actions': sorted(set(benefit['eligible_actions']).intersection(provided)),
                     'planned_actions': sorted(set(benefit['eligible_actions']).intersection(planned)),
                     'completed_project_ids': [project['id'] for project in completed if project.get('id')][:12],
                     'unfinished_project_ids': [project['id'] for project in matches if not _complete(project) and project.get('id')][:12]})
    return rows


def _new_benefit_actions(benefit, coverage, crew_actions):
    provided = set().union(*(set(row['already_provided_actions']) for row in coverage
                            if row['resource'] == benefit.get('resource')))
    return sorted(set(benefit.get('eligible_actions', [])).intersection(crew_actions) - provided)


def _free_sites(projects):
    # Coordinates also obey the blueprint schema's individual +/-3 bounds.
    # These are independent alternatives, not permission to build all at once.
    points = [(x * .75, z * .75) for x in range(-4, 5) for z in range(-4, 5)
              if math.hypot(x * .75, z * .75) <= 3.4]
    points.sort(key=lambda point: (math.hypot(*point), point[1], point[0]))
    existing = [(project.get('position') or {}) for project in projects]
    return [{'x': x, 'y': 0, 'z': z} for x, z in points
            if all(math.hypot(x - _number(position.get('x')), z - _number(position.get('z'))) >= .65
                   for position in existing)][:6]


def _research_options(actor, dossiers, experiments, coverage, sites, slots, resources):
    """Uncovered functions worth testing, never a prediction of success.

    An unchanged failed production test is not a new opportunity. Different
    arrangements remain model proposals; this small list covers grounded solo
    tests and marks its scope explicitly instead of claiming exhaustive search.
    """
    identifier = actor.get('character_id')
    dossier = dossiers.get(identifier)
    if not dossier or not sites or not slots or _number(resources.get('ideas')) < 1:
        return []
    props = dossier.get('simulation_properties') or {}
    output = []
    for row in coverage:
        family = row['family']
        if not set(row['eligible_crew_actions']) - set(row['already_provided_actions']) - set(row['planned_actions']):
            continue
        cavity = props.get('cavity_model') or {}
        if family == 'contain' and cavity.get('status') not in ('observed_cavity', 'declared_simulation_cavity'):
            continue
        current_tests = [test for test in experiments if test.get('family') == family
                         and test.get('rule_version') == RULE_VERSION
                         and test.get('subject_ids') == [identifier]
                         and test.get('property_fingerprints') == [dossier.get('property_fingerprint')]
                         and test.get('status') != 'blocked' and isinstance(test.get('result'), dict)]
        # A failed normal-workload test needs a changed arrangement/evidence,
        # not another identical paid probe. Successful tests go to tested_designs.
        normal_context = context_for(family, PRODUCTION_BENCHMARKS[family])
        def already_tested(test):
            context = test.get('context') or {}
            if test['result'].get('success'):
                return all(_number(context.get(k), -1) >= v for k, v in PRODUCTION_BENCHMARKS[family].items())
            # Failure at another tilt, support count or heavier load does not
            # establish failure of the proposed normal arrangement.
            return all(_number(context.get(k), v) == v for k, v in normal_context.items())
        if any(already_tested(test) for test in current_tests):
            continue
        output.append({'family': family, 'resident_id': identifier, 'dossier_id': dossier.get('id'),
                       'evidence_basis': cavity.get('authority', 'declared_simulation_geometry') if family == 'contain' else 'declared_simulation_geometry',
                       'property_fingerprint': dossier.get('property_fingerprint'),
                       'context': deepcopy(PRODUCTION_BENCHMARKS[family]),
                       'benefits_actions': row['eligible_crew_actions'],
                       'reason': 'An uncovered useful function has current simulation evidence and no matching completed benchmark test. Test before claiming a benefit.'})
    return output


def work_opportunities(payload):
    """Summarize the full current observation before its history is trimmed.

    Stored-stock funding excludes expected gains from tasks still in flight.
    Candidate feasibility is taken from the executor's assessment. Tested design
    options are independently checked by the production blueprint validator,
    including ordered participant identity, fingerprints, operating conditions
    and the permitted arrangement. No model-authored claim upgrades evidence.
    """
    actor = payload.get('actor') or {}
    projects = _rows(payload.get('projects'))
    resources = payload.get('resources') or {}
    crew = [actor, *_rows(payload.get('peers'))]
    crew_actions = {action for resident in crew for action in resident.get('allowed_actions', [])}
    coverage = _coverage(projects, crew_actions)
    project_by_id = {project['id']: project for project in projects if project.get('id')}
    funded, gathering, blocked, redundant = [], [], [], []
    for candidate in _rows((payload.get('planning') or {}).get('candidates')):
        project = project_by_id.get(candidate.get('project_id'))
        if not project or candidate.get('complete') or _complete(project):
            continue
        summary = {key: deepcopy(candidate[key]) for key in ('project_id', 'name', 'target_level',
                   'remaining_work', 'reserved_work', 'remaining_actions', 'required_resources',
                   'gathering_needed', 'missing_capabilities', 'reason') if key in candidate}
        summary['benefit'] = deepcopy(project.get('benefit') or {'description': project.get('reward', '')})
        summary['actor_can_build'] = 'build' in actor.get('allowed_actions', [])
        if project.get('kind') == 'assembly' and not _new_benefit_actions(project.get('benefit', {}), coverage, crew_actions):
            redundant.append({'project_id': project['id'], 'reason': 'No additional eligible crew action benefits: matching task bonuses are already provided or this crew lacks those actions.'})
        elif not candidate.get('feasible'):
            blocked.append(summary)
        elif all(_number(resources.get(resource)) >= _number(amount)
                 for resource, amount in candidate.get('required_resources', {}).items()):
            summary['funding'] = 'remaining_cost_covered_by_current_stored_stock'
            funded.append(summary)
        else:
            summary['funding'] = 'requires_incoming_or_further_gathered_stock'
            gathering.append(summary)

    learning = payload.get('learning') or {}
    dossiers = {row['resident_id']: row for row in _rows(learning.get('dossiers')) if row.get('resident_id')}
    blueprints = _rows(learning.get('blueprints'))
    cited_experiments = {row.get('experiment_id') for row in blueprints}
    sites = _free_sites(projects)
    assembly_slots = max(0, 12 - sum(project.get('kind') == 'assembly' for project in projects))
    designs, excluded = [], {}
    seen_arrangements = set()
    for experiment in _rows(learning.get('experiments')):
        family, ids = experiment.get('family'), experiment.get('subject_ids')
        result = experiment.get('result')
        if (family not in BENEFITS or not isinstance(ids, list) or not ids or actor.get('character_id') not in ids
                or not experiment.get('id') or not isinstance(result, dict) or not result.get('success')):
            continue
        reason = None
        coverage_row = next(row for row in coverage if row['family'] == family)
        if experiment['id'] in cited_experiments:
            reason = 'already_used_by_blueprint'
        elif not _new_benefit_actions(BENEFITS[family], coverage, crew_actions):
            reason = 'no_additional_eligible_action_bonus'
        elif not set(_new_benefit_actions(BENEFITS[family], coverage, crew_actions)) - set(coverage_row['planned_actions']):
            reason = 'matching_project_already_awaits_work'
        elif not assembly_slots or not sites:
            reason = 'no_current_construction_space'
        if reason:
            excluded[reason] = excluded.get(reason, 0) + 1
            continue
        try:
            span = _number((experiment.get('context') or {}).get('span'), .6)
            parts = [{'kind': PRIMARY_KINDS[family][0], 'resident_id': identifier,
                      'position': {'x': 0 if index == 0 else round((index / len(ids) - .5) * span, 4), 'y': 0, 'z': 0},
                      'rotation': 0} for index, identifier in enumerate(ids)]
            validation = validate_blueprint({'name': 'Evidence check', 'purpose': 'Check an existing tested arrangement for council context.',
                'family': family, 'parts': parts, 'experiment_id': experiment['id'], 'position': sites[0]}, dossiers, experiment)
        except (StoreError, ValueError, TypeError, KeyError):
            excluded['evidence_not_valid_for_current_production'] = excluded.get('evidence_not_valid_for_current_production', 0) + 1
            continue
        signature = (family, tuple(ids), tuple(experiment.get('property_fingerprints') or []))
        if signature in seen_arrangements:
            excluded['duplicate_tested_arrangement'] = excluded.get('duplicate_tested_arrangement', 0) + 1
            continue
        seen_arrangements.add(signature)
        cost = validation['maximum_cost_at_base_work']
        designs.append({'experiment_id': experiment['id'], 'finding_id': experiment.get('finding_id'),
            'family': family, 'subject_ids': deepcopy(ids), 'context': deepcopy(validation['context']),
            'evidence_status': 'current_production_validator_passed',
            'primary_kind_options': deepcopy(PRIMARY_KINDS[family]), 'tested_parts': parts,
            'benefit': deepcopy(validation['benefit']), 'work_required': validation['work_required'],
            'cost_per_action': deepcopy(validation['cost_per_action']), 'maximum_cost_at_base_work': deepcopy(cost),
            'funded_from_current_stock': all(_number(resources.get(resource)) >= amount for resource, amount in cost.items()),
            'missing_stock': {resource: amount - _number(resources.get(resource)) for resource, amount in cost.items()
                              if amount > _number(resources.get(resource))}})
    designs.sort(key=lambda row: not row['funded_from_current_stock'])
    research = _research_options(actor, dossiers, _rows(learning.get('experiments')), coverage, sites, assembly_slots, resources)
    return {'authority': 'Current observation facts and independently validated options; the model chooses and peers must explicitly agree. Revalidate at execution.',
        'funded_projects': funded[:8], 'projects_needing_supplies': gathering[:4], 'blocked_projects': blocked[:4],
        'no_additional_benefit_projects': redundant[:6], 'bonus_coverage': coverage,
        'tested_designs': designs[:6], 'omitted_design_counts': excluded,
        'research_options': research[:3],
        'free_sites': sites, 'remaining_assembly_slots': assembly_slots,
        'next_steps': [
            'Existing funded projects can receive a proposal or support with their exact project_id; agreement permits actual build work.',
            'A tested_design can reuse its experiment_id and ordered tested_parts in a named, purposeful blueprint at a free_site. It does not need an identical retest.',
            'After a blueprint is accepted, use its actual returned project_id for proposal/support; a blueprint alone is not agreement or completed work.',
            'Completed matching task bonuses are capped at one. Another matching structure adds no bonus; full storage is not a reason to collect more or invent demand.',
            'Research options are untested, evidence-backed solo benchmark hypotheses for uncovered benefits; success is not promised. Do not repeat an unchanged completed test.',
            'If no useful funded option exists, discuss a different evidence-backed arrangement or state the actual capability/resource constraint. Waiting for changed evidence or a new capability is valid.'],
        'limits': {'funded_projects': 8, 'tested_designs': 6, 'free_sites': 6,
                   'site_scope': 'Independent grounded alternatives, checked against current projects; recheck after any new construction.'}}
