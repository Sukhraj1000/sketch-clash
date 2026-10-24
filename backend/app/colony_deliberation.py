"""Validated council outcomes. Only published model stances can select a project."""
from copy import deepcopy
from datetime import timedelta

from .island import _iso
from .repository import StoreError, key_for


def model_controlled(island, state):
    return bool(getattr(island.repo.settings, 'gemini_api_key', '') or
                (state or {}).get('planning', {}).get('decision_authority') == 'model')


def review_model_plan(island, tx, state, agents, now):
    previous = state.get('planning', {})
    project_id = previous.get('manual_project_id') if previous.get('mode') == 'manual' else previous.get('selected_project_id')
    # _project(None) falls back to the legacy world's default garden. A new
    # model-led island must wait for explicit agreement before selecting work.
    project = island._project(state, project_id) if project_id else None
    target = previous.get('target_level')
    if project and (previous.get('mode') == 'manual' or not isinstance(target, int)):
        target = project['level'] + 1
    selected = project['id'] if project and project['level'] < target and project['level'] < project['max_level'] else None
    state['planning'] = {**previous, 'mode': previous.get('mode', 'crew'), 'decision_authority': 'model',
        'selected_project_id': selected, 'target_level': target if selected else None, 'last_checked_at': _iso(now),
        'next_council_at': _iso(now + timedelta(seconds=45)),
        'reason': previous.get('reason', 'Waiting for the residents to discuss their first shared project.') if selected else
                  'The residents need to agree on their next useful project. Their actual conversation appears on the board.'}
    state['active_project_id'] = selected
    tx.put('islandState', state)


class DeliberationMixin:
    def resolve_council(self, session_id, colony_id, participant_ids, population_fingerprint):
        from .colony_planner import population_fingerprint as fingerprint
        from .observability import record_event
        island = self._side(colony_id)
        now = island._now()
        def resolve(tx):
            decision_id = key_for(island.world_id, 'council-outcome', session_id)
            old = tx.get('colonyCouncilOutcomes', decision_id)
            if old:
                return {k: v for k, v in old.items() if k != '_id'}
            session = tx.get('colonyCouncilSessions', session_id)
            if not session or session.get('world_id') != self.world_id or session.get('colony_id') != colony_id:
                raise StoreError('This council does not belong to the island.', 409, 'invalid_council_session')
            cohort = {actor['id'] for actor in session.get('participants', [])}
            if set(participant_ids) != cohort or session.get('population_fingerprint') != population_fingerprint:
                raise StoreError('Council participants or population evidence do not match the durable session.', 409, 'invalid_council_session')
            if session.get('status') != 'resolving' or session.get('completed_turns', 0) < session.get('max_turns', 1):
                raise StoreError('The council has not finished its discussion.', 409, 'council_incomplete')
            state = tx.get('islandState', island.state_id)
            if state is None or state['paused']:
                return {'status': 'stale', 'reason': 'The island is paused or unavailable.'}
            agents = island._agents(tx)
            # Recheck under the same transaction as selection so arrivals cannot
            # race the external snapshot and silently approve an outdated plan.
            if fingerprint({'island': {'agents': agents}}) != population_fingerprint:
                return {'status': 'stale', 'reason': 'New residents or changed capabilities require a fresh discussion.'}
            allowed = {a['id'] for a in agents} & set(participant_ids)
            messages = tx.find('colonyBoard', {'world_id': island.world_id, 'session_id': session_id, 'origin': 'model'}, sort='created_at', limit=64)
            latest = {}
            for row in sorted(messages, key=lambda r: (r.get('turn_index', 0), r['created_at'])):
                if row['actor_id'] in allowed and row['kind'] in ('proposal', 'support', 'objection'):
                    latest[row['actor_id']] = row
            candidates = island._assess_projects(state, agents)
            votes = {}
            for row in latest.values():
                if row['kind'] in ('proposal', 'support'):
                    votes.setdefault(row.get('project_id'), []).append(row)
            quorum = 1 if len(agents) == 1 else 2
            eligible = [c for c in candidates if c['feasible'] and len(votes.get(c['project_id'], [])) >= quorum]
            selected = sorted(eligible, key=lambda c: (-len(votes[c['project_id']]), c['project_id']))[0] if eligible else None
            if state.get('planning', {}).get('mode') == 'manual':
                selected = None
                reason = 'Player override remains active; the crew discussion is saved without changing the project.'
            else:
                reason = (f"{len(votes[selected['project_id']])} residents agreed on {selected['name']}; resources and capabilities were rechecked."
                          if selected else 'No feasible project received explicit agreement from enough residents. The discussion remains open research.')
            outcome = {'_id': decision_id, 'id': decision_id, 'world_id': island.world_id, 'session_id': session_id,
                       'status': 'agreed' if selected else 'no_agreement', 'project_id': selected['project_id'] if selected else None,
                       'reason': reason, 'created_at': _iso(now)}
            participants = [{'agent_id': a['id'], 'character_id': a['character_id'], 'actor_name': a['display_name'],
                             'kind': latest[a['id']]['kind'], 'project_id': latest[a['id']].get('project_id'),
                             'reason': latest[a['id']].get('interpretation') or latest[a['id']]['text'],
                             'contributes': [], 'origin': 'model', 'message_id': latest[a['id']]['id']}
                            for a in agents if a['id'] in latest]
            council = {'id': decision_id, 'at': _iso(now), 'chosen_project_id': outcome['project_id'],
                       'previous_project_id': state.get('active_project_id'), 'reason': reason, 'origin': 'model',
                       'mode': 'crew', 'participants': participants, 'candidates': candidates,
                       'model_message_ids': [m['id'] for m in messages], 'votes': {k: len(v) for k, v in votes.items()}}
            state['council'] = [*state.get('council', []), council][-8:]
            if selected:
                state['planning'] = {**state.get('planning', {}), 'mode': 'crew', 'decision_authority': 'model',
                    'selected_project_id': selected['project_id'], 'target_level': selected['target_level'],
                    'reason': reason, 'last_council_at': _iso(now), 'next_council_at': _iso(now + timedelta(seconds=45))}
                state['active_project_id'] = selected['project_id']
            state['revision'] += 1
            tx.put('islandState', state)
            tx.put('colonyCouncilOutcomes', outcome)
            if agents:
                island._new_board(tx, agents[0], 'decision', now, key_for(decision_id, 'board'), actor_id='executor',
                    character_id='', actor_name='Island executor', session_id=session_id, council_id=session_id,
                    text=reason, verified=True, origin='executor', project_id=outcome['project_id'])
            record_event(tx, self.world_id, event_id=decision_id, kind='council.resolved', island_id=colony_id,
                         session_id=session_id, message=reason, data={'status': outcome['status'], 'project_id': outcome['project_id']})
            return {k: v for k, v in outcome.items() if k != '_id'}
        return island.repo.transaction(resolve)
