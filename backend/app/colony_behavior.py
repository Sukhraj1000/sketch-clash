"""Read-only explanation of available work; no invented powers or outputs."""
from .colony_opportunities import work_opportunities
from .colony_experiments import canonical_digest


def behavior_summary(colony):
    island = colony.get('island') or {}
    agents = island.get('agents') or []
    learning = colony.get('learning') or {}
    resources = island.get('resources') or {}
    projects = island.get('projects') or []
    planning = colony.get('planning') or {}
    funded, gathering, designs, research = set(), set(), set(), []
    funded_designs = set()
    supplyable = {resource for agent in agents for action, yields in (agent.get('action_yields') or {}).items()
                  if action in agent.get('allowed_actions', []) for resource, amount in yields.items() if amount > 0}
    missing = set()
    for agent in agents:
        options = work_opportunities({'actor': agent, 'peers': [a for a in agents if a['id'] != agent['id']],
            'projects': projects, 'resources': resources, 'planning': planning, 'learning': learning})
        funded.update(p['project_id'] for p in options['funded_projects'])
        gathering.update(p['project_id'] for p in options['projects_needing_supplies'])
        for design in options['tested_designs']:
            if design['funded_from_current_stock']:
                funded_designs.add(design['experiment_id'])
                designs.add(design['experiment_id'])
            elif set(design['missing_stock']).issubset(supplyable):
                designs.add(design['experiment_id'])
            else:
                missing.update(set(design['missing_stock']) - supplyable)
        research.extend(options['research_options'])
        for p in options['blocked_projects']:
            missing.update(p.get('missing_capabilities') or [])
    working = [a for a in agents if (a.get('task') or {}).get('kind') != 'rest'
               and (any(v > 0 for v in (a.get('task', {}).get('gain') or {}).values())
                    or a.get('task', {}).get('progress_gain', 0) > 0)]
    if not agents:
        status, reason = 'no_residents', 'This crew has no residents yet.'
    elif working:
        status, reason = 'work_in_progress', 'Saved tasks are gathering supplies or adding construction work. Their receipts will confirm the outcome.'
    elif funded:
        status, reason = 'funded_work', 'Useful unfinished construction is funded. The crew can discuss and agree on one of these projects.'
    elif gathering:
        status, reason = 'gathering_work', 'The crew has the capabilities to supply an unfinished project.'
    elif designs:
        status, reason = 'design_available', 'Current successful tests support a new useful design. It still needs a blueprint, agreement and construction.'
        if not funded_designs:
            reason += ' More supplies must be gathered using existing crew capabilities; stock is not yet reserved.'
    elif research:
        status, reason = 'research_available', 'Current simulation evidence supports testing an uncovered useful function. A test may fail; no improvement is claimed yet.'
    else:
        status = 'waiting_for_change'
        reason = 'No funded useful build, reusable production design or untested solo benchmark is available in the current evidence window.'
        if missing:
            reason += ' Remaining projects need a capability to supply ' + ', '.join(sorted(missing)) + '.'
        reason += ' A changed arrangement can still be proposed manually; repeated idle actions add no output.'
    # Ignore time, XP, idle receipts and animation positions. Changes which can
    # make new work possible wake the automatic council after an honest review.
    fingerprint = canonical_digest({
        'agents': sorted((a['id'], sorted(a.get('allowed_actions', [])), a.get('action_yields', {}),
                          a.get('assignment'), a.get('assignment_origin')) for a in agents),
        'resources': resources,
        'projects': sorted((p['id'], p.get('level'), p.get('progress'), p.get('status'), p.get('benefit')) for p in projects),
        'dossiers': sorted((d.get('resident_id', ''), d.get('property_fingerprint', ''), d.get('evidence_version', '')) for d in learning.get('dossiers', [])),
        'experiments': sorted((e['id'], e.get('status')) for e in learning.get('experiments', [])),
        'blueprints': sorted((b['id'], b.get('status')) for b in learning.get('blueprints', [])),
        'plan': (planning.get('mode'), planning.get('selected_project_id'), planning.get('target_level'))})
    return {'status': status, 'reason': reason, 'missing_capabilities': sorted(missing),
            'funded_project_ids': sorted(funded), 'gathering_project_ids': sorted(gathering),
            'tested_design_ids': sorted(designs), 'research_options': research[:12],
            'working_actor_ids': [a['id'] for a in working], 'fingerprint': fingerprint,
            'wake_on': ['new resident or capability', 'changed usable evidence', 'changed stock or project', 'manual council request'],
            'scope': 'Current supported simulation and supplied evidence window; not an exhaustive search of possible physical inventions.'}
