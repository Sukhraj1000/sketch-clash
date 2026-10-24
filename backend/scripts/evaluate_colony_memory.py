"""Matched deterministic memory evaluation; no Atlas, Gemini, live saves or keys.

Run: .venv/bin/python backend/scripts/evaluate_colony_memory.py
This evaluates evidence reuse and transfer boundaries, not model intelligence.
"""
from __future__ import annotations

import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.colonies import colony_world_id
from app.colony_experiments import RULE_VERSION, canonical_digest, context_for, physical_properties, simulate_experiment
from app.colony_learning import ColonyLearningStore, FINDINGS
from app.config import Settings
from app.repository import MemoryRepository


def evaluate():
    repo = MemoryRepository(Settings(repository='memory', world_id='isolated-learning-evaluation'),
                            lambda: '2026-10-24T12:00:00+00:00')
    store = ColonyLearningStore(repo)
    scope = colony_world_id(repo.world_id, 'winners')
    beam = physical_properties(['flat wooden strip'])
    support = physical_properties(['solid metal rectangular body'])
    seed_cases = [
        {'id': 'unsupported-span', 'family': 'support', 'subject_ids': ['beam'], 'properties': [beam],
         'context': {'span': .6, 'load': .2, 'support_count': 2}},
        {'id': 'supported-span', 'family': 'support', 'subject_ids': ['beam', 'support'], 'properties': [beam, support],
         'context': {'span': .6, 'load': .2, 'support_count': 3}},
    ]
    def remember(tx):
        for case in seed_cases:
            result = simulate_experiment(case['family'], case['properties'], case['context'])
            tx.put(FINDINGS, {'_id': case['id'], 'id': case['id'], 'world_id': scope,
                             'family': case['family'], 'subject_ids': case['subject_ids'],
                             'rule_version': RULE_VERSION, 'status': 'tested_in_sim',
                             'context': result['context'], 'success': result['success'],
                             'claim': result['summary'], 'measurements': result['measurements'],
                             'property_fingerprints': [canonical_digest(properties) for properties in case['properties']],
                             'updated_at': repo.clock(), 'supporting_experiment_ids': [f"training-{case['id']}"]})
    repo.transaction(remember)
    scenarios = [
        {**seed_cases[0], 'id': 'remembered-failed-span'},
        {**seed_cases[1], 'id': 'remembered-useful-support'},
        {**seed_cases[1], 'id': 'held-out-heavier-load', 'context': {'span': .6, 'load': 8, 'support_count': 3}},
        {**seed_cases[1], 'id': 'new-object-arrival', 'subject_ids': ['beam', 'new-support']},
    ]
    rows = []
    totals = {mode: {'experiments_run': 0, 'findings_reused': 0, 'known_failures_avoided': 0,
                     'successful_outcomes': 0} for mode in ('memory_off', 'memory_on')}
    for scenario in scenarios:
        row = {'scenario': scenario['id'], 'conditions': context_for(scenario['family'], scenario['context'])}
        for mode in ('memory_off', 'memory_on'):
            candidates = store.knowledge(scope, 'support span')['findings'] if mode == 'memory_on' else []
            matching = next((finding for finding in candidates
                             if finding['family'] == scenario['family']
                             and finding['subject_ids'] == scenario['subject_ids']
                             and finding['context'] == row['conditions']
                             and finding['property_fingerprints'] == [canonical_digest(properties) for properties in scenario['properties']]), None)
            if matching:
                success = matching['success']
                action = 'reuse_tested_result' if success else 'avoid_known_failed_arrangement'
                totals[mode]['findings_reused'] += 1
                totals[mode]['known_failures_avoided'] += int(not success)
            else:
                success = simulate_experiment(scenario['family'], scenario['properties'], scenario['context'])['success']
                action = 'run_new_experiment'
                totals[mode]['experiments_run'] += 1
            totals[mode]['successful_outcomes'] += int(success)
            row[mode] = {'action': action, 'success': success, 'finding_id': matching['id'] if matching else None}
        row['outcomes_agree'] = row['memory_on']['success'] == row['memory_off']['success']
        rows.append(row)
    return {'evaluation': 'matched_evidence_reuse_and_transfer_boundary', 'rule_version': RULE_VERSION,
            'authority': 'isolated_deterministic_fixture', 'model_calls': 0, 'live_database_writes': 0,
            'limitation': 'Measures memory plumbing with a fixed policy; does not measure Gemini reasoning quality or prove general learning.',
            'training_experiments': len(seed_cases), 'scenarios': rows, 'totals': totals,
            'all_outcomes_agree': all(row['outcomes_agree'] for row in rows)}


if __name__ == '__main__':
    print(json.dumps(evaluate(), indent=2))
