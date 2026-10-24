"""Bound a council's public observation without altering its evidence or powers."""
import json
from .repository import StoreError


def _strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for child in value.values():
            yield from _strings(child)
    elif isinstance(value, list):
        for child in value:
            yield from _strings(child)


def _complete(project):
    return isinstance(project, dict) and project.get('level', 0) >= project.get('max_level', 1)


def _compact_current_facts(payload, notes):
    """Remove copies/rendering of completed work, never operational constraints."""
    count = notes.setdefault('omitted_fields', {})
    for project in payload.get('projects', []):
        if not _complete(project):
            continue
        assembly = project.get('assembly')
        if isinstance(assembly, dict) and isinstance(assembly.get('parts'), list):
            # Completed geometry cannot be proposed as new production evidence.
            # Keep the actual source residents, tested conditions and real bonus.
            assembly['source_resident_ids'] = [part['resident_id'] for part in assembly['parts'] if part.get('resident_id')]
            assembly.pop('parts')
            count['completed_project_render_parts'] = count.get('completed_project_render_parts', 0) + 1
    planning = payload.get('planning', {})
    for candidate in planning.get('candidates', []):
        if not isinstance(candidate, dict) or not candidate.get('complete'):
            continue
        # Completed candidates are not actionable. Their repeated stock maps and
        # hypothetical next-upgrade costs are redundant (and misleading at max).
        for field in ('remaining_work', 'reserved_work', 'remaining_actions', 'required_resources',
                      'available_resources', 'incoming_resources', 'gatherable_resources',
                      'gathering_needed', 'missing_capabilities'):
            if field in candidate:
                candidate.pop(field)
                count['completed_candidate_fields'] = count.get('completed_candidate_fields', 0) + 1


def bounded_council_context(payload, system_characters, *, target=36000, maximum=48000):
    """Trim optional whole records; mandatory constraints and dialogue survive.

    Caller owns this observation copy. Durable board/research documents are never
    mutated. This runs again after recall, since recall consumes context too.
    """
    notes = payload.setdefault('context_window', {})
    notes.setdefault('authority',
        'Incomplete observation window. Omitted history is not evidence of absence or failure. '
        'Cite only evidence supplied here; backend validators remain authoritative. '
        'Completed project rendering and completed candidates\' hypothetical costs may be omitted; '
        'their identity, position, completion and actual benefit remain supplied.')
    omitted = notes.setdefault('omitted_records', {})
    learning = payload.get('learning', {})
    _compact_current_facts(payload, notes)
    project_ids = {p.get('id') for p in payload.get('projects', [])}
    for blueprint in learning.get('blueprints', []):
        project = blueprint.get('project')
        if isinstance(project, dict) and project.get('id') in project_ids:
            blueprint['project_id'] = project['id']
            blueprint.pop('project')
    # Cumulative seen-message lists grow quadratically. Keep every public message,
    # its author, exact text, ordering, reply target and evidence; provenance lists
    # remain available in the durable board/turn record.
    for message in payload.get('council_session', {}).get('conversation', []):
        message.pop('seen_message_ids', None)
    recall = learning.get('retrieved_memory', {})

    # Current dialogue is never truncated. Preserve the records it cites too,
    # including IDs written in the public message rather than typed references.
    session = payload.get('council_session', {})
    references = set(_strings([session, payload.get('work_opportunities', {}),
                               payload.get('active_project_id'), payload.get('actor', {}).get('task')]))
    dialogue = '\n'.join(_strings(session.get('conversation', [])))
    own_id = payload.get('actor', {}).get('character_id')
    if own_id:
        references.add(own_id)

    def cited(row):
        identifier = row.get('id') if isinstance(row, dict) else None
        return bool(identifier and (identifier in references or identifier in dialogue))

    # Directly cited experiments/blueprints must retain their current object
    # evidence. This does not turn any recalled claim into an executable power.
    for _ in range(3):  # Blueprint -> experiment -> finding/subjects, independent of list order.
        for field in ('blueprints', 'experiments', 'findings', 'historical_findings'):
            for row in learning.get(field, []):
                if cited(row):
                    references.update(row.get('subject_ids', []))
                    references.update(part.get('resident_id') for part in row.get('parts', []) if part.get('resident_id'))
                    references.update(row.get(key) for key in ('experiment_id', 'finding_id') if row.get(key))

    def protected(parent, field, row):
        if parent is learning and field == 'dossiers':
            return row.get('resident_id', row.get('id')) in references
        return cited(row)

    def encode(): return json.dumps(payload, ensure_ascii=True, separators=(',', ':'))
    encoded = encode()
    actor = payload.get('actor', {})
    optional = [(payload, 'project_discussion', 4), (payload, 'board', 4),
        (payload, 'last_receipts', 1), (payload, 'recent_validation_feedback', 1),
        (actor, 'memory', 1), (learning, 'research', 0), (learning, 'blueprints', 0),
        (learning, 'historical_findings', 0),
        (learning, 'experiments', 2), (learning, 'findings', 3),
        (learning, 'dossiers', 2), (recall, 'findings', 1)]
    for parent, field, minimum in optional:
        rows = parent.get(field, []) if isinstance(parent, dict) else []
        threshold = min(target, 20000) if parent is payload and field in ('project_discussion', 'board', 'last_receipts') else target
        while isinstance(rows, list) and len(rows) > minimum and len(encoded)+system_characters > threshold:
            # Actor memory is chronological; evidence lists are newest/relevant
            # first and dossiers have already been sorted with the actor first.
            order = range(len(rows)) if parent is actor and field == 'memory' else range(len(rows)-1, -1, -1)
            index = next((i for i in order if not protected(parent, field, rows[i])), None)
            if index is None:
                break
            rows.pop(index)
            name = ('learning.' if parent is learning else 'recall.' if parent is recall else 'actor.' if parent is actor else '')+field
            omitted[name] = omitted.get(name, 0)+1
            encoded = encode()

    # Mature residents accumulate up to 32 capability summaries and 64 finding
    # IDs each. Keep current citations plus a recent window of these optional
    # indexes, with explicit counts; the full tested records remain in Atlas.
    for dossier in learning.get('dossiers', []):
        for field, minimum in (('tested_capabilities', 3), ('finding_ids', 3)):
            rows = dossier.get(field, [])
            while len(rows) > minimum and len(encoded)+system_characters > target:
                index = next((i for i, row in enumerate(rows)
                              if (row.get('finding_id') if isinstance(row, dict) else row) not in references
                              and (row.get('finding_id', '') if isinstance(row, dict) else str(row)) not in dialogue), None)
                if index is None:
                    break
                rows.pop(index)
                name = 'dossier.' + field
                omitted[name] = omitted.get(name, 0) + 1
                encoded = encode()

    # The preferred recent-history minimum is a convenience, not authority.
    # Drop remaining uncited optional records before rejecting a mature island;
    # preserve actor/object evidence, tools, all current facts and cited history.
    for parent, field, _ in optional:
        if field == 'dossiers':
            continue
        rows = parent.get(field, []) if isinstance(parent, dict) else []
        while isinstance(rows, list) and rows and len(encoded)+system_characters > target:
            order = range(len(rows)) if parent is actor and field == 'memory' else range(len(rows)-1, -1, -1)
            index = next((i for i in order if not protected(parent, field, rows[i])), None)
            if index is None:
                break
            rows.pop(index)
            name = ('learning.' if parent is learning else 'recall.' if parent is recall else 'actor.' if parent is actor else '')+field
            omitted[name] = omitted.get(name, 0)+1
            encoded = encode()
    if len(encoded)+system_characters > maximum:
        raise StoreError('The bounded council context is full.', 422, 'planner_context_limit')
    return encoded
