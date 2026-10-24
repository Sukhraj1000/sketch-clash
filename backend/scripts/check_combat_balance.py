"""Local seeded combat audit. Never connects to Gemini, Atlas or a marketplace."""
import argparse
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.combat_fixtures import get_catalog
from app.combat_v2 import ENGINE_VERSION, _simulate


def audit(seeds: int) -> dict:
    catalog = get_catalog()
    fixtures = catalog['fixtures']
    matrix = {}
    knockout = points = ties = seeded_ties = impact_ties = 0
    for i, a in enumerate(fixtures):
        for j, b in enumerate(fixtures):
            if j < i:
                continue
            wins = 0
            for seed in range(seeds):
                result = _simulate([a, b], seed, with_price=True, with_interactions=True)
                wins += result['winner_slot'] == 0
                knockout += result['outcome'] == 'knockout'
                points += result['outcome'] == 'points'
                ties += result['outcome'] == 'tiebreak'
                seeded_ties += result['tiebreak_reason'] == 'seed'
                impact_ties += result['tiebreak_reason'] == 'impact_points'
            matrix[f"{a['id']}:{b['id']}"] = round(wins / seeds, 6)
            if i != j:
                matrix[f"{b['id']}:{a['id']}"] = round(1 - wins / seeds, 6)
    roster = {a['id']: round(sum(matrix[f"{a['id']}:{b['id']}"] for b in fixtures if a['id'] != b['id']) / (len(fixtures) - 1), 6) for a in fixtures}
    # A stronger ablation than sample prices: every subject goes from £0 to the full capped £250.
    uplift = {}
    flips = 0
    comparisons = 0
    for a in fixtures:
        low, high = deepcopy(a), deepcopy(a)
        low['price']['amount_gbp'], high['price']['amount_gbp'] = 0, 250
        difference = 0
        for b in fixtures:
            if a['id'] == b['id']:
                continue
            for seed in range(seeds):
                before = _simulate([low, b], seed, with_price=True, with_interactions=True)['winner_slot']
                after = _simulate([high, b], seed, with_price=True, with_interactions=True)['winner_slot']
                difference += int(after == 0) - int(before == 0)
                flips += before != after
                comparisons += 1
        uplift[a['id']] = round(difference / ((len(fixtures) - 1) * seeds), 6)
    return {'engine_version': ENGINE_VERSION, 'seeds_per_matchup': seeds,
            'configuration_sha256': sha256(json.dumps(catalog, sort_keys=True).encode()).hexdigest(),
            'simulated_matches': (len(fixtures) * (len(fixtures) + 1) // 2 + 2 * len(fixtures) * (len(fixtures) - 1)) * seeds,
            'fixtures': len(fixtures), 'fixture_provenance': 'curated examples; not an exhaustive object distribution',
            'matchup_win_rates': matrix, 'uniform_roster_win_rates': roster,
            'max_price_only_win_rate_uplift': uplift,
            'mean_price_only_win_rate_uplift': round(sum(uplift.values()) / len(uplift), 6),
            'price_only_changed_winner_fraction': round(flips / comparisons, 6),
            'outcomes': {'knockout': knockout, 'points': points, 'tiebreak': ties,
                         'impact_points_tiebreak': impact_ties, 'seeded_tiebreak': seeded_ties},
            'checks': {'uniform_roster_max_under_60_percent': max(roster.values()) < .60,
                       'uniform_roster_min_over_40_percent': min(roster.values()) > .40,
                       'all_fixture_price_uplifts_under_5_percentage_points': max(uplift.values()) <= .05},
            'interpretation': 'Empirical local audit for these fixtures and seeds. Not a guarantee of balance for arbitrary objects. Price uplift holds all other inputs and random draws fixed.'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--seeds', type=int, default=1000)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    if args.seeds < 1:
        parser.error('--seeds must be positive')
    result = audit(args.seeds)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({key: value for key, value in result.items() if key != 'matchup_win_rates'}, indent=2))

    if not all(result['checks'].values()):
        raise SystemExit(1)
