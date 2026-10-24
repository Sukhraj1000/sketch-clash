"""Bound a council's public observation without altering its evidence or powers."""
import json
from .repository import StoreError


def bounded_council_context(payload, system_characters, *, target=36000, maximum=48000):
    """Trim optional whole records; mandatory constraints and dialogue survive.

    Caller owns this observation copy. Durable board/research documents are never
    mutated. This runs again after recall, since recall consumes context too.
    """
    notes = payload.setdefault('context_window', {'omitted_records': {}, 'authority':
        'Incomplete observation window. Omitted history is not evidence of absence or failure. '
        'Cite only evidence supplied here; backend validators remain authoritative.'})
    omitted = notes['omitted_records']
    learning = payload.get('learning', {})
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

    def encode(): return json.dumps(payload, ensure_ascii=True, separators=(',', ':'))
    encoded = encode()
    actor = payload.get('actor', {})
    optional = [(payload, 'project_discussion', 4), (payload, 'board', 4),
        (payload, 'last_receipts', 1), (payload, 'recent_validation_feedback', 1),
        (actor, 'memory', 1), (learning, 'research', 0), (learning, 'blueprints', 0),
        (learning, 'experiments', 2), (learning, 'findings', 3),
        (learning, 'dossiers', 2), (recall, 'findings', 1)]
    for parent, field, minimum in optional:
        rows = parent.get(field, []) if isinstance(parent, dict) else []
        threshold = min(target, 20000) if parent is payload and field in ('project_discussion', 'board', 'last_receipts') else target
        while isinstance(rows, list) and len(rows) > minimum and len(encoded)+system_characters > threshold:
            # Actor memory is chronological; evidence lists are newest/relevant
            # first and dossiers have already been sorted with the actor first.
            index = 0 if parent is actor and field == 'memory' else -1
            rows.pop(index)
            name = ('learning.' if parent is learning else 'recall.' if parent is recall else 'actor.' if parent is actor else '')+field
            omitted[name] = omitted.get(name, 0)+1
            encoded = encode()
    if len(encoded)+system_characters > maximum:
        raise StoreError('The bounded council context is full.', 422, 'planner_context_limit')
    return encoded
