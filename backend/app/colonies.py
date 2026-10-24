"""Two isolated persistent colonies and a capability-checked cooperation board.

Battle outcomes route accepted fighters; neither price nor generated dialogue
sets routing, powers, stock or rewards. The existing shared island is untouched.
The economy is an abstract resource ledger, not physical cargo simulation.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import timedelta
from hashlib import sha256
import json
import math
from typing import Any

from .agent_sdk import SDK_VERSION, PUBLIC_TEXT_LIMIT, AgentDecision, action_resource, capability_profile, resource_actions, validate_decision
from .island import (IslandStore, ACTION_LABELS, RESOURCE_LOCATIONS, RESOURCE_KEYS, MAX_AGENTS, MAX_RESOURCE,
                     _position, _iso, _time)
from .repository import StoreError, key_for, public
from .colony_deliberation import DeliberationMixin, model_controlled, review_model_plan
from .colony_learning import ColonyLearningStore
from .observability import record_event, agent_span
from .board_presentation import board_text, report_commentary

COLONY_IDS = ('winners', 'losers')
COLONY_NAMES = {'winners': 'Winner Island', 'losers': 'Loser Island'}
BOARD_SECONDS = 300
PROJECT_OPINION_SECONDS = 6 * 60 * 60
BOARD_LIMIT = 80
BACKFILL_LIMIT = 1000
COUNCIL_SECONDS = 45
COUNCIL_HISTORY_LIMIT = 8
AUTOMATIC_RESERVE = 40
IDLE_CHECK_SECONDS = 60


def colony_world_id(world_id: str, colony_id: str) -> str:
    if colony_id not in COLONY_IDS:
        raise StoreError('Choose Winner Island or Loser Island.', 422, 'invalid_colony')
    return key_for(world_id, 'colony-world', colony_id)[:32]


def route_completed_battle(tx, battle: dict, root_world_id: str) -> list[str]:
    """Called in the battle completion transaction; safe for historical replay."""
    if battle.get('status') != 'completed' or battle.get('world_id') != root_world_id:
        return []
    if battle.get('winner_slot') not in (0, 1) or len(battle.get('fighters', [])) != 2:
        raise StoreError('Completed battle cannot be routed without its accepted fighters and winner.', 409, 'routing_evidence_missing')
    ids = []
    for fighter in sorted(battle['fighters'], key=lambda item: item['player_slot']):
        slot = fighter['player_slot']
        colony_id = 'winners' if slot == battle['winner_slot'] else 'losers'
        scope = colony_world_id(root_world_id, colony_id)
        placement_id = key_for(root_world_id, 'colony-placement', battle['id'], str(slot))
        resident_id = key_for(scope, fighter['canonical_type_id'])[:32]
        ids.append(placement_id)
        existing = tx.get('colonyPlacements', placement_id)
        if existing:
            if existing['colony_id'] != colony_id or existing['resident_id'] != resident_id:
                raise StoreError('An immutable battle placement disagrees with the result.', 409, 'placement_conflict')
            continue
        timestamp = battle['completed_at']
        resident = tx.get('colonyResidents', resident_id)
        if resident is None:
            seed = int(key_for(scope, fighter['canonical_type_id'])[:8], 16)
            angle, radius = (seed % 360) * math.tau / 360, 1 + (seed // 360 % 220) / 100
            resident = {'_id': resident_id, 'id': resident_id, 'world_id': scope, 'root_world_id': root_world_id,
                        'colony_id': colony_id, 'canonical_type_id': fighter['canonical_type_id'],
                        'object_type': fighter['object_type'], 'display_name': fighter['display_name'],
                        'image_ref': fighter['image_ref'], 'visual_spec': deepcopy(fighter['visual_spec']),
                        'archetype': fighter['archetype'], 'first_battle_id': battle['id'],
                        'first_player_slot': slot, 'unlocked_at': timestamp,
                        'home_position': {'x': round(math.cos(angle) * radius, 3), 'y': 0, 'z': round(math.sin(angle) * radius, 3)},
                        'state': {'activity': 'wander', 'mood': 'curious'}, 'distinct_battle_count': 0,
                        'market_price': None, 'estimated_value_gbp': None, 'valuation_status': 'unknown',
                        'valuation_provenance': None}
            resident['observed_object'] = deepcopy(fighter.get('observed_object', {}))
            resident['capture_id'] = fighter.get('capture_id')
            resident['validation'] = deepcopy(fighter.get('validation', {}))
            record_event(tx, root_world_id, event_id=key_for(placement_id, 'arrival'), kind='resident.arrived',
                         island_id=colony_id, actor_id=resident_id, actor_name=resident['display_name'],
                         message=f"{resident['display_name']} arrived. The crew will reassess what it can build.",
                         data={'resident_id': resident_id, 'canonical_type_id': resident['canonical_type_id']})
        resident['distinct_battle_count'] += 1
        resident['last_battle_at'] = timestamp
        tx.put('colonyResidents', resident)
        tx.put('colonyPlacements', {'_id': placement_id, 'id': placement_id, 'world_id': root_world_id,
                'battle_id': battle['id'], 'player_slot': slot, 'winner_slot': battle['winner_slot'],
                'colony_id': colony_id, 'resident_id': resident_id, 'canonical_type_id': fighter['canonical_type_id'],
                'accepted_fighter': deepcopy(fighter), 'created_at': timestamp, 'immutable': True,
                'basis': 'authoritative_completed_battle', 'market_price': None})
    return ids


class _ScopedTransaction:
    def __init__(self, tx):
        self.tx = tx
    def _name(self, collection):
        return {'worldCharacters': 'colonyResidents', 'worlds': 'colonyWorlds'}.get(collection, collection)
    def get(self, collection, key):
        return self.tx.get(self._name(collection), key)
    def put(self, collection, value):
        return self.tx.put(self._name(collection), value)
    def find(self, collection, query, sort=None, limit=501):
        return self.tx.find(self._name(collection), query, sort, limit)


class _ScopedRepository:
    def __init__(self, repo, colony_id):
        self.parent = repo
        self.root_world_id = repo.world_id
        self.colony_id = colony_id
        self.world_id = colony_world_id(repo.world_id, colony_id)
        self.clock, self.settings, self.persistence = repo.clock, repo.settings, repo.persistence
        if hasattr(repo, 'db'):
            self.db = repo.db
    def read(self, operation):
        return self.parent.read(lambda tx: operation(_ScopedTransaction(tx)))
    def transaction(self, operation):
        return self.parent.transaction(lambda tx: operation(_ScopedTransaction(tx)))


class _ColonyIsland(IslandStore):
    def _new_agent(self, character, now):
        agent = super()._new_agent(character, now)
        profile = capability_profile(character)
        agent.update({key: deepcopy(profile[key]) for key in ('allowed_actions', 'capabilities', 'action_yields', 'resource_sources')})
        agent.update(sdk_version=SDK_VERSION, assignment_origin='deterministic', active_commitment=None,
                     contributions={'resources': {key: 0 for key in RESOURCE_KEYS}, 'work': 0, 'cooperative_units': 0},
                     decision_origin='deterministic', decision_reason='Follow declared capabilities and colony needs.')
        agent['available_assignments'] = [{'id': action, 'label': ACTION_LABELS[action]} for action in ['auto', *agent['allowed_actions']]]
        agent['persona'].update({key: profile[key] for key in ('preferred_action', 'role', 'motto', 'goal', 'temperament')})
        return agent

    def command(self, body, now=None):
        if not isinstance(body, dict) or body.get('kind') not in ('assign', 'priority', 'council'):
            return super().command(body, now)
        allowed = {'idempotency_key', 'kind', 'project_id', 'character_id', 'assignment', 'expected_revision', 'mode'}
        request_id = body.get('idempotency_key')
        if set(body) - allowed or not isinstance(request_id, str) or not 8 <= len(request_id) <= 128:
            raise StoreError('An assignment needs supported fields and a durable request key.', 422, 'invalid_island_command')
        timestamp = self._now(now)
        fingerprint = sha256(json.dumps(body, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
        event_id = key_for(self.world_id, 'island-command', request_id)
        def assign(tx):
            previous = tx.get('islandEvents', event_id)
            if previous:
                if previous['fingerprint'] != fingerprint:
                    raise StoreError('That command key has another instruction.', 409, 'island_command_mismatch')
                return self._snapshot(tx, timestamp)
            state = tx.get('islandState', self.state_id)
            if state is None:
                raise StoreError('Start colony life before giving a direction.', 409, 'island_not_started')
            if body.get('expected_revision') is not None and body['expected_revision'] != state['revision']:
                raise StoreError('The colony changed. Refresh before giving this direction.', 409, 'island_revision_conflict')
            self._advance(tx, timestamp)
            state = tx.get('islandState', self.state_id)
            if body['kind'] in ('priority', 'council'):
                mode = 'manual' if body['kind'] == 'priority' else body.get('mode')
                if mode not in ('crew', 'manual'):
                    raise StoreError('Choose crew or manual project control.', 422, 'invalid_council_mode')
                project = self._project(state, body.get('project_id')) if body.get('project_id') else None
                if mode == 'manual' and (project is None or project['level'] >= project['max_level']):
                    raise StoreError('Choose an unfinished project for manual control.', 422, 'invalid_project')
                state.setdefault('planning', {})['mode'] = mode
                state['planning']['manual_project_id'] = project['id'] if mode == 'manual' else None
                self._run_council(tx, state, self._agents(tx), timestamp, force=True)
                state['revision'] += 1
                tx.put('islandState', state)
                tx.put('islandEvents', {'_id': event_id, 'id': event_id, 'world_id': self.world_id, 'kind': 'command',
                        'at': _iso(timestamp), 'fingerprint': fingerprint, 'command': body['kind'],
                        'title': 'Crew project control' if mode == 'crew' else 'Player project override',
                        'description': 'Project direction changed; work already in flight remains reserved.', 'resource_delta': {}})
                return self._snapshot(tx, timestamp)
            agent = tx.get('islandAgents', key_for(self.world_id, 'island-agent', str(body.get('character_id', ''))))
            if agent is None or agent['world_id'] != self.world_id:
                raise StoreError('That resident is not an active colony agent.', 404, 'agent_not_found')
            if agent.get('active_commitment'):
                raise StoreError('Finish the accepted contribution before changing work.', 409, 'commitment_busy')
            if body.get('assignment') not in ['auto', *agent['allowed_actions']]:
                raise StoreError('That task exceeds this object’s capabilities.', 422, 'invalid_assignment')
            agent.update(assignment=body['assignment'], assignment_origin='player', updated_at=_iso(timestamp))
            agent.pop('pending_decision_action', None)
            agent.pop('pending_decision_id', None)
            tx.put('islandAgents', agent)
            state['revision'] += 1
            tx.put('islandState', state)
            tx.put('islandEvents', {'_id': event_id, 'id': event_id, 'world_id': self.world_id, 'kind': 'command',
                    'at': _iso(timestamp), 'fingerprint': fingerprint, 'command': 'assign',
                    'title': ACTION_LABELS[body['assignment']], 'description': 'A player direction was saved. Ongoing work finishes first.',
                    'resource_delta': {}, 'character_id': agent['character_id']})
            return self._snapshot(tx, timestamp)
        return self.repo.transaction(assign)

    def initialize(self, now=None):
        timestamp = self._now(now)
        super().initialize(timestamp)
        def plan(tx):
            state = tx.get('islandState', self.state_id)
            self._run_council(tx, state, self._agents(tx), timestamp)
            tx.put('islandState', state)
            return self._snapshot(tx, timestamp)
        return self.repo.transaction(plan)

    def _choose_project(self, state):
        # A council owns selection in colony mode. The legacy island's sequential
        # fallback must not silently commit resources to an impossible next upgrade.
        planning = state.get('planning', {})
        project = self._project(state, planning.get('selected_project_id')) if planning.get('selected_project_id') else None
        if project is None or project['level'] >= project['max_level']:
            return None
        if planning.get('mode', 'crew') == 'crew' and project['level'] >= planning.get('target_level', project['level'] + 1):
            return None
        state['active_project_id'] = project['id']
        return project

    def _assess_projects(self, state, agents):
        producers = {resource for agent in agents for action in agent['allowed_actions']
                     if (resource := action_resource(agent, action)) is not None}
        incoming = {resource: 0 for resource in RESOURCE_KEYS}
        for agent in agents:
            for resource, amount in (agent.get('task') or {}).get('gain', {}).items():
                incoming[resource] += amount
        available = {resource: min(MAX_RESOURCE, state['resources'][resource] + incoming[resource]) for resource in RESOURCE_KEYS}
        workers = [agent for agent in agents if 'build' in agent['allowed_actions']]
        # Use the least productive eligible builder, not an optimistic best actor:
        # any valid future schedule must be able to finish with this admission budget.
        work_per_action = min((2 + ('measure' in a['allowed_actions']) + (a['level'] - 1) // 5 for a in workers), default=2)
        candidates = []
        for project in state['projects']:
            remaining = max(0, project['required_progress'] - project['progress'] - project['reserved_progress'])
            actions = math.ceil(remaining / work_per_action)
            required = {resource: cost * actions for resource, cost in self._cost(project).items()}
            missing = [resource for resource, amount in required.items() if amount > available[resource] and resource not in producers]
            complete = project['level'] >= project['max_level']
            feasible = not complete and bool(workers) and not missing
            shortages = [resource for resource, amount in required.items() if amount > available[resource] and resource in producers]
            if complete:
                reason = 'All upgrades are complete.'
            elif not workers:
                reason = 'The colony needs an active resident before construction can begin.'
            elif missing:
                reason = 'Cannot finish this upgrade: no resident can supply ' + ', '.join(missing) + ', and stored plus incoming stock is insufficient.'
            elif shortages:
                reason = 'Feasible after gathering ' + ', '.join(shortages) + '; the crew has the required abilities.'
            else:
                reason = 'Stored and already scheduled supplies cover the remaining upgrade.'
            candidates.append({'project_id': project['id'], 'name': project['name'], 'target_level': min(project['level'] + 1, project['max_level']),
                    'feasible': feasible, 'complete': complete, 'remaining_work': remaining, 'reserved_work': project['reserved_progress'],
                    'remaining_actions': actions, 'required_resources': required, 'available_resources': deepcopy(available),
                    'incoming_resources': deepcopy(incoming), 'gatherable_resources': sorted(producers),
                    'gathering_needed': shortages, 'missing_capabilities': missing, 'reason': reason})
        return candidates

    def _project_opinions(self, tx, now):
        state = tx.get('islandState', self.state_id)
        unfinished = {project['id'] for project in (state or {}).get('projects', []) if project['level'] < project['max_level']}
        # Peers on the same shore normally take turns thirty minutes apart.
        # Project preferences outlive a supply claim, survive individual upgrades,
        # and stop voting when superseded, six hours old, or fully completed.
        return sorted((row for row in tx.find('colonyProjectOpinions', {'world_id': self.world_id}, limit=MAX_AGENTS)
                       if _time(row['expires_at']) > now and row['project_id'] in unfinished),
                      key=lambda row: (row['created_at'], row['actor_id']), reverse=True)

    def _project_discussion(self, tx, now):
        discussion = []
        for stance in self._project_opinions(tx, now):
            message = tx.get('colonyBoard', stance['message_id'])
            if message is None or message.get('world_id') != self.world_id:
                continue
            discussion.append({'id': message['id'], 'actor_id': message['actor_id'], 'actor_name': message['actor_name'],
                    'kind': message['kind'], 'project_id': message['project_id'],
                    'proposal_id': message.get('proposal_id'), 'text': message.get('interpretation') or message['text'],
                    'origin': message['origin'], 'expires_at': stance['expires_at']})
        return discussion

    def _planning_view(self, tx, state, agents, now):
        candidates = self._assess_projects(state, agents) if state else []
        planning = deepcopy((state or {}).get('planning', {}))
        selected = next((item for item in candidates if item['project_id'] == planning.get('selected_project_id')), None)
        project = self._project(state, planning.get('selected_project_id')) if state and planning.get('selected_project_id') else None
        if not planning:
            status = 'waiting'
        elif project and project['workers']:
            status = 'building'
        elif selected and not selected['feasible'] and not selected['complete']:
            status = 'blocked'
        elif project and planning.get('mode') == 'crew' and project['level'] >= planning.get('target_level', 999):
            status = 'waiting'
        elif selected and selected['feasible']:
            status = 'gathering' if selected['gathering_needed'] else 'building'
        else:
            status = 'complete' if candidates and all(row['complete'] for row in candidates) else 'blocked' if agents else 'waiting'
        return {'mode': planning.get('mode', 'crew'), 'status': status,
                'selected_project_id': planning.get('selected_project_id'),
                'target_level': planning.get('target_level'), 'reason': planning.get('reason', 'The crew will assess its first project when colony life starts.'),
                'last_council_at': planning.get('last_council_at'), 'next_council_at': planning.get('next_council_at'),
                'cooldown_seconds': COUNCIL_SECONDS, 'candidates': candidates}

    def _run_council(self, tx, state, agents, now, force=False):
        if state is None:
            return
        if model_controlled(self, state):
            review_model_plan(self, tx, state, agents, now)
            return
        previous_plan = state.get('planning', {})
        if state['paused'] and previous_plan and not force:
            return
        if not force and previous_plan.get('next_council_at') and now < _time(previous_plan['next_council_at']):
            return
        candidates = self._assess_projects(state, agents)
        feasible = [row for row in candidates if row['feasible']]
        by_id = {row['project_id']: row for row in candidates}
        stances = {row['actor_id']: row for row in self._project_opinions(tx, now)}
        participants, votes = [], {row['project_id']: 0 for row in feasible}
        model_votes = {row['project_id']: 0 for row in feasible}
        for agent in agents:
            resources = sorted({resource for action in agent['allowed_actions'] if (resource := action_resource(agent, action)) is not None})
            stance = stances.get(agent['id'])
            options = [row for row in feasible if not (stance and stance['kind'] == 'objection' and stance['project_id'] == row['project_id'])]
            if not options:
                options = feasible
            def preference(row):
                project = self._project(state, row['project_id'])
                relevance = sum(max((agent['action_yields'][a].get(resource, 0) for a in agent['action_yields']), default=0) / cost
                                for resource, cost in self._cost(project).items())
                return (-relevance, project['level'], sum(row['required_resources'].values()), row['project_id'])
            preferred = min(options, key=preference) if options else None
            origin, message_id = 'deterministic', None
            if stance:
                message_id = stance['message_id']
                proposed = by_id.get(stance['project_id'])
                if stance['kind'] in ('proposal', 'support') and proposed and proposed['feasible']:
                    preferred, origin = proposed, 'model'
                    model_votes[proposed['project_id']] += 1
                elif stance['kind'] == 'objection':
                    origin = 'model'
            project_id = preferred['project_id'] if preferred else None
            contributes = [resource for resource in resources if preferred and resource in preferred['required_resources']]
            reason = ('Can contribute ' + ', '.join(contributes) + ' and construction work.' if preferred else
                      'No remaining upgrade is feasible with the current crew and stock.')
            if stance and stance['kind'] == 'objection':
                reason = 'The actor objected to this project; its capability-based alternative is ' + (preferred['name'].lower() if preferred else 'not yet feasible') + '.'
            elif stance:
                reason = ('Accepted model preference; ' + reason if origin == 'model' else
                          'The model suggestion did not pass feasibility; ' + reason)
            opinion = {'agent_id': agent['id'], 'character_id': agent['character_id'], 'actor_name': agent['display_name'],
                    'project_id': stance['project_id'] if stance and stance['kind'] == 'objection' else project_id,
                    'vote_project_id': project_id, 'kind': 'objection' if stance and stance['kind'] == 'objection' else 'support' if preferred else 'objection', 'reason': reason,
                    'contributes': contributes, 'origin': origin, 'message_id': message_id}
            participants.append(opinion)
            if project_id:
                votes[project_id] += 1
        previous_id = previous_plan.get('selected_project_id')
        mode = previous_plan.get('mode', 'crew')
        selected = None
        if mode == 'manual':
            selected = by_id.get(previous_plan.get('manual_project_id'))
            if selected and selected['complete']:
                selected = None
            reason = 'Player project override is active. Return control to the crew for automatic selection.'
        else:
            current = by_id.get(previous_id)
            current_project = self._project(state, previous_id) if previous_id else None
            model_majority = next((row for row in feasible if model_votes[row['project_id']] > len(agents) / 2), None)
            if model_majority:
                selected = model_majority
                reason = 'A majority of individual model preferences selected a feasible upgrade.'
            elif current and current['feasible'] and current_project['level'] < previous_plan.get('target_level', -1):
                selected = current
                reason = 'Finish the agreed upgrade before changing projects; temporary shortages can be gathered.'
            elif feasible:
                selected = min(feasible, key=lambda row: (-votes[row['project_id']], self._project(state, row['project_id'])['level'],
                                                          sum(row['required_resources'].values()), row['project_id']))
                reason = f"The crew selected {selected['name'].lower()} with {votes[selected['project_id']]} of {len(agents)} capability-based votes."
                if current and current['missing_capabilities']:
                    reason += ' Switched away from missing ' + ', '.join(current['missing_capabilities']) + '.'
            else:
                reason = ('Every building is fully upgraded; the crew can maintain supplies and explore.' if all(row['complete'] for row in candidates)
                          else 'No whole upgrade is feasible. A new capability or more externally supplied stock is needed; unfinished work stays safe.')
        selected_id = selected['project_id'] if selected else None
        discussion_signature = sha256(json.dumps({'mode': mode, 'selected': selected_id,
                'target_level': selected['target_level'] if selected else None, 'reason': reason,
                'feasibility': [(c['project_id'], c['target_level'], c['feasible'], c['complete'], c['missing_capabilities']) for c in candidates],
                'opinions': [(p['agent_id'], p['project_id'], p['kind'], p['message_id']) for p in participants]}, sort_keys=True).encode()).hexdigest()
        if not force and previous_plan.get('discussion_signature') == discussion_signature:
            # Recheck feasibility on schedule without inventing repetitive dialogue.
            state['planning']['next_council_at'] = _iso(now + timedelta(seconds=COUNCIL_SECONDS))
            state['planning']['last_checked_at'] = _iso(now)
            tx.put('islandState', state)
            return
        sequence = state.get('council_sequence', 0) + 1
        identifier = key_for(self.world_id, 'council', str(sequence))
        decision = {'id': identifier, 'at': _iso(now), 'chosen_project_id': selected_id, 'previous_project_id': previous_id,
                    'reason': reason, 'origin': 'deterministic', 'mode': mode, 'participants': participants,
                    'candidates': candidates, 'model_message_ids': sorted({p['message_id'] for p in participants if p['message_id']}),
                    'votes': votes, 'authority': 'Feasibility checked by the executor; model text cannot create stock or abilities.'}
        state['planning'] = {'mode': mode, 'manual_project_id': previous_plan.get('manual_project_id'),
                'selected_project_id': selected_id, 'target_level': selected['target_level'] if selected else None,
                'reason': reason, 'discussion_signature': discussion_signature, 'last_checked_at': _iso(now),
                'last_council_at': _iso(now), 'next_council_at': _iso(now + timedelta(seconds=COUNCIL_SECONDS))}
        state['active_project_id'] = selected_id
        state['council_sequence'] = sequence
        state['council'] = [*state.get('council', []), decision][-COUNCIL_HISTORY_LIMIT:]
        state['revision'] += 1
        # Each published opinion is attributed to its real actor. Text here is a
        # rule explanation, never fabricated dialogue from a model or another actor.
        for opinion in participants:
            agent = next(a for a in agents if a['id'] == opinion['agent_id'])
            self._new_board(tx, agent, opinion['kind'], now, key_for(identifier, agent['id']),
                    project_id=opinion['project_id'], council_id=identifier, origin='deterministic',
                    text=opinion['reason'], evidence=deepcopy(opinion), verified=True)
        if agents:
            self._new_board(tx, agents[0], 'decision', now, key_for(identifier, 'decision'), actor_id='council',
                    character_id='', actor_name='Crew council', project_id=selected_id, council_id=identifier,
                    text=reason, verified=True, origin='deterministic', participants=[p['agent_id'] for p in participants])
        tx.put('islandState', state)

    def _production_yield(self, state, agent, action):
        resource = action_resource(agent, action)
        if resource is None:
            return {}, False
        earned_bonus = any(p.get('kind') == 'assembly' and p['level'] >= p['max_level']
                           and action in p.get('benefit', {}).get('eligible_actions', [])
                           and p['benefit'].get('resource') == resource for p in state['projects'])
        amount = (agent['action_yields'][action][resource] + self._resource_bonus(state, resource)
                  + (agent['level'] - 1) // 5 + int(earned_bonus))
        return {resource: min(amount, max(0, MAX_RESOURCE - state['resources'][resource]))}, earned_bonus

    def _work_options(self, state, agent, project):
        """Explain executable actions using current stock and declared powers only."""
        available, blocked, yields = [], [], {}
        costs = self._cost(project) if project else {}
        for action in agent['allowed_actions']:
            reason, resource = None, action_resource(agent, action)
            if action == 'build':
                if project is None:
                    reason = 'No unfinished project has been agreed by the crew.'
                elif any(state['resources'][key] < cost for key, cost in costs.items()):
                    missing = ', '.join(f"{key} ({cost - state['resources'][key]} short)"
                                        for key, cost in costs.items() if state['resources'][key] < cost)
                    reason = 'Construction needs ' + missing + '.'
                elif not self._can_build(state, project):
                    reason = 'The available construction places or remaining work are already reserved.'
            elif action != 'rest':
                gain, _ = self._production_yield(state, agent, action)
                yields[action] = gain
                if resource is None:
                    reason = 'This action has no declared resource yield.'
                elif not gain.get(resource):
                    reason = f'Shared {resource} storage is full ({MAX_RESOURCE}/{MAX_RESOURCE}); this action cannot add stock.'
            if reason:
                blocked.append({'action': action, 'reason': reason, 'resource': resource})
            else:
                available.append(action)
        useful = [action for action in available if action == 'build' or
                  (action_resource(agent, action) is not None and
                   state['resources'][action_resource(agent, action)] <
                   max(AUTOMATIC_RESERVE, costs.get(action_resource(agent, action), 0) * 3))]
        build_block = next((row['reason'] for row in blocked if row['action'] == 'build'), '')
        idle_reason = ('' if useful else
                       'Supported supplies are already stocked to the automatic reserve or full. ' + build_block)
        return {'available_actions': available, 'useful_actions': useful, 'blocked_actions': blocked,
                'action_yields': yields, 'resource_capacity': MAX_RESOURCE,
                'full_resources': [key for key in RESOURCE_KEYS if state['resources'][key] >= MAX_RESOURCE],
                'automatic_buffer_target': AUTOMATIC_RESERVE,
                'selected_project_id': project['id'] if project else None, 'idle_reason': idle_reason,
                'authority': 'Current executor admission facts, not model reasoning. Explicit gathering may use remaining capacity; automatic work stops at its reserve.'}

    def _choose_action(self, state, agent, project):
        options = self._work_options(state, agent, project)
        assigned = agent['assignment']
        if assigned != 'auto':
            if assigned not in agent['allowed_actions']:
                raise StoreError('Saved assignment exceeds accepted capabilities.', 503, 'capability_invariant')
            # A model's idle choice is a fallback for the observation it saw,
            # not an instruction to ignore newly agreed, funded work. Explicit
            # player rest remains authoritative until the player changes it.
            stale_model_rest = (assigned == 'rest' and agent.get('assignment_origin') == 'model'
                                and bool(options['useful_actions']))
            if assigned in options['available_actions'] and not stale_model_rest:
                return assigned
        if 'build' in options['useful_actions']:
            return 'build'
        costs = self._cost(project) if project else {}
        shortages = sorted(costs, key=lambda resource: state['resources'][resource] / costs[resource])
        for resource in shortages:
            actions = [action for action in resource_actions(agent, resource) if action in options['useful_actions']]
            if actions and state['resources'][resource] < costs[resource] * 3:
                return max(actions, key=lambda action: agent['action_yields'][action][resource])
        preferred = agent['persona']['preferred_action']
        if preferred in options['useful_actions']:
            return preferred
        production = [action for action in options['useful_actions'] if action_resource(agent, action)]
        if production:
            return min(production, key=lambda action: (state['resources'][action_resource(agent, action)],
                                                       -next(iter(options['action_yields'][action].values())), action))
        return 'rest'  # A missing capability or full reserve never creates a new power.

    def _schedule(self, state, agent, start):
        resources_before_reservation = deepcopy(state['resources'])
        project = self._choose_project(state)
        options = self._work_options(state, agent, project)
        requested = agent['assignment'] if agent['assignment'] != 'auto' else None
        action = self._choose_action(state, agent, project)
        if action not in agent['allowed_actions']:
            raise StoreError('Scheduler proposed an unsupported capability.', 503, 'capability_invariant')
        sequence = agent['completed_actions'] + 1
        task_id = key_for(self.world_id, 'action', agent['character_id'], str(sequence))
        seed = int(task_id[:8], 16)
        duration = IDLE_CHECK_SECONDS if action == 'rest' else 14 + seed % 5
        switched = requested is not None and requested != action
        blocked_reason = next((row['reason'] for row in options['blocked_actions'] if row['action'] == requested), '')
        if switched and requested == 'rest':
            blocked_reason = 'Useful work became available after the earlier idle decision.'
        reason = (f'{requested} was not useful now: {blocked_reason} Switched to {action}.' if switched else
                  options['idle_reason'] if action == 'rest' and options['idle_reason'] else
                  f'Executing the accepted {action} assignment.' if requested else
                  'Construction is funded and an agreed work place is available.' if action == 'build' else
                  f'Replenish {action_resource(agent, action)} within the project need or automatic reserve.')
        task = {'id': task_id, 'kind': action, 'title': ACTION_LABELS[action], 'started_at': _iso(start),
                'ends_at': _iso(start + timedelta(seconds=duration)), 'duration_seconds': duration,
                'from': deepcopy(agent['position']), 'to': deepcopy(agent['position']), 'gain': {},
                'progress_gain': 0, 'project_id': None, 'resource': None, 'xp_gain': 3,
                'sdk_version': SDK_VERSION,
                'scheduling_reason': reason, 'requested_action': requested, 'action_switched': switched,
                'requested_decision_id': agent.get('pending_decision_id') or (agent.get('active_commitment') or {}).get('decision_id'),
                'decision_origin': 'player' if agent.get('assignment_origin') == 'player' and agent['assignment'] == action else 'deterministic',
                'decision_id': None}
        if action == 'build' and project:
            work = min(2 + ('measure' in agent['allowed_actions']) + (agent['level'] - 1) // 5,
                       project['required_progress'] - project['progress'] - project['reserved_progress'])
            costs = self._cost(project)
            for key, amount in costs.items():
                state['resources'][key] -= amount
            project['reserved_progress'] += work
            project['workers'].append(agent['character_id'])
            project['status'] = 'building'
            task.update(title=f"Build {project['name'].lower()}", project_id=project['id'], project_level=project['level'],
                        progress_gain=work, cost=costs, xp_gain=5,
                        to=_position({'x': project['position']['x'] + (seed % 3 - 1) * .25,
                                      'z': project['position']['z'] + (.8 if project['kind'] == 'beacon' else 1)}))
        elif action == 'rest':
            task.update(title='Wait for useful work',
                        to={'x': -.7, 'z': 1.1}, xp_gain=0)
        else:
            resource = action_resource(agent, action)
            if resource is None:
                raise StoreError('A production action has no accepted yield.', 503, 'capability_invariant')
            gain, earned_bonus = self._production_yield(state, agent, action)
            task['tested_structure_bonus'] = int(earned_bonus)
            task['gain'] = gain
            task['resource'] = resource
            destination = deepcopy(RESOURCE_LOCATIONS[resource])
            if action == 'explore':
                angle = (seed % 360) * math.tau / 360
                destination = {'x': math.cos(angle) * 4.15, 'z': math.sin(angle) * 4.15}
            if action == 'tend':
                task['title'] = 'Grow materials in the nursery'
            elif action == 'charge':
                task['title'] = 'Collect energy at the charging dock'
            elif action == 'signal':
                task['title'] = 'Observe signals for useful ideas'
            destination['x'] += ((seed >> 6) % 5 - 2) * .10
            destination['z'] += ((seed >> 9) % 5 - 2) * .10
            task['to'] = _position(destination)
        commitment = agent.get('active_commitment')
        if commitment and commitment['action'] == action:
            task['commitment_id'] = commitment['id']
            task['request_id'] = commitment['request_id']
            task['decision_origin'] = commitment['origin']
            task['decision_id'] = commitment.get('decision_id')
        elif agent.get('pending_decision_action') == action:
            task.update(decision_id=agent.get('pending_decision_id'), decision_origin=agent.get('assignment_origin', 'model'))
            agent.pop('pending_decision_action', None)
            agent.pop('pending_decision_id', None)
            agent['assignment'] = 'auto'
            agent['assignment_origin'] = 'deterministic'
        elif switched and agent.get('pending_decision_action') == requested:
            # Retain the rejected request as evidence on this task, without
            # attributing the fallback to Gemini or retrying a stale choice forever.
            agent.pop('pending_decision_action', None)
            agent.pop('pending_decision_id', None)
            agent['assignment'] = 'auto'
            agent['assignment_origin'] = 'deterministic'
        self._record_reservation(task, agent, resources_before_reservation, state['resources'])
        agent['task'], agent['updated_at'] = task, _iso(start)

    def _wake_idle_workers(self, tx, state, agents, now, council_id):
        """Replace uncommitted idle slots after agreement, never complete them early.

        The next sequence/id stays the same because no action was completed.
        Reservations happen through the ordinary scheduler inside the council's
        transaction, whose outcome is the replay boundary for this handoff.
        """
        if state['paused'] or state.get('planning', {}).get('mode') == 'manual':
            return []
        started = []
        for agent in sorted(agents, key=lambda row: row['id']):
            task = agent.get('task') or {}
            if (task.get('kind') != 'rest' or agent.get('active_commitment')
                    or agent.get('assignment_origin') == 'player' and agent['assignment'] != 'auto'):
                continue
            project = self._choose_project(state)
            if project is None or self._choose_action(state, agent, project) == 'rest':
                continue
            previous_task = deepcopy(task)
            self._schedule(state, agent, now)
            task = agent['task']
            task.update(council_id=council_id, superseded_idle_started_at=previous_task.get('started_at'),
                        scheduling_reason='The crew agreed on a project. The executor replaced an idle wait with useful work. '
                                          + task['scheduling_reason'])
            tx.put('islandAgents', agent)
            started.append({'actor_id': agent['id'], 'character_id': agent['character_id'],
                            'actor_name': agent['display_name'], 'task_id': task['id'], 'kind': task['kind'],
                            'project_id': task.get('project_id'), 'reserved_cost': deepcopy(task.get('cost', {})),
                            'status': 'scheduled', 'execution_origin': 'local_executor'})
        return started

    def _board(self, tx):
        return tx.find('colonyBoard', {'world_id': self.world_id}, sort='created_at', limit=256)

    def _requests(self, tx):
        # Active commitments must remain visible even when the recent feed fills
        # with reports; a recent-history limit is not an authority boundary.
        rows = []
        for status in ('open', 'claimed'):
            rows.extend(tx.find('colonyBoard', {'world_id': self.world_id, 'kind': 'request', 'status': status},
                                sort='created_at', limit=17))
        return sorted(rows, key=lambda row: (row['created_at'], row['id']), reverse=True)

    def _new_board(self, tx, agent, kind, now, identifier, **fields):
        value = {'_id': identifier, 'id': identifier, 'world_id': self.world_id,
                 'root_world_id': self.repo.root_world_id, 'colony_id': self.repo.colony_id,
                 'kind': kind, 'actor_id': agent['id'], 'character_id': agent['character_id'],
                 'actor_name': agent['display_name'], 'created_at': _iso(now),
                 'expires_at': _iso(now + timedelta(seconds=BOARD_SECONDS)),
                 'status': 'recorded', 'receipt_ids': [], 'origin': 'deterministic', **fields}
        tx.put('colonyBoard', value)
        record_event(tx, self.repo.root_world_id, event_id=key_for(identifier, 'published'), kind='board.message',
                     island_id=self.repo.colony_id, actor_id=value['actor_id'], actor_name=value['actor_name'],
                     session_id=value.get('session_id'),
                     message=board_text(value),
                     data={'message_id': identifier, 'message_kind': kind, 'origin': value['origin'],
                           'reply_to_id': value.get('reply_to_id'), 'project_id': value.get('project_id'),
                           'receipt_ids': deepcopy(value.get('receipt_ids', [])),
                           'evidence_kind': 'execution_report' if value.get('receipt_ids') else 'board_message',
                           **report_commentary(value)})
        return value

    def _request(self, tx, state, agent, resource, quantity, project_id, now, identifier, origin='deterministic', note=''):
        requests = self._requests(tx)
        existing = next((row for row in requests if row['resource'] == resource and row.get('project_id') == project_id), None)
        if existing:
            if origin == 'model':
                # The work request has one owner; a later speaker gets a separate
                # immutable message, not permission to rewrite the owner's turn.
                return self._new_board(tx, agent, 'reflection', now, identifier,
                        request_id=existing['id'], project_id=existing.get('project_id'),
                        resource=resource, text=note or f'Requested {quantity} {resource} for the shared project.',
                        origin=origin, request_reused=True, verified=False,
                        effect='References an existing shared request. No new request, offer or delivery was created.')
            return existing
        if len(requests) >= 16:
            raise StoreError('The colony board has enough open work. Finish or expire an existing request.', 429, 'board_full')
        project = self._project(state, project_id) if project_id else None
        title = project['name'].lower() if project else 'our colony'
        return self._new_board(tx, agent, 'request', now, identifier, resource=resource, quantity=quantity,
                remaining=quantity, project_id=project_id, status='open', claimed_by=None,
                text=f"I need {quantity} {resource} for {title}.", interpretation=note, origin=origin)

    def _claim(self, tx, state, agent, request, action, now, identifier, origin='deterministic', decision_id=None, note=''):
        if request['world_id'] != self.world_id or request['kind'] != 'request' or request['status'] != 'open' or _time(request['expires_at']) <= now:
            raise StoreError('This request is no longer open in this colony.', 409, 'request_unavailable')
        if request['actor_id'] == agent['id']:
            raise StoreError('A cooperation request must be answered by another resident.', 422, 'self_claim')
        if action not in agent['allowed_actions'] or action_resource(agent, action) != request['resource']:
            raise StoreError('This object cannot supply the requested resource.', 422, 'capability_denied')
        if agent.get('active_commitment'):
            raise StoreError('Finish the current commitment before accepting another.', 409, 'commitment_busy')
        commitment_id = key_for(identifier, 'commitment')
        commitment = {'_id': commitment_id, 'id': commitment_id, 'world_id': self.world_id, 'request_id': request['id'],
                      'agent_id': agent['id'], 'character_id': agent['character_id'], 'action': action,
                      'resource': request['resource'], 'quantity': request['remaining'], 'remaining': request['remaining'],
                      'status': 'accepted', 'created_at': _iso(now), 'expires_at': request['expires_at'],
                      'origin': origin, 'decision_id': decision_id, 'receipt_ids': []}
        request.update(status='claimed', claimed_by=agent['id'], commitment_id=commitment_id)
        agent.update(active_commitment=public(commitment), assignment=action, assignment_origin='board')
        tx.put('colonyCommitments', commitment)
        tx.put('colonyBoard', request)
        tx.put('islandAgents', agent)
        offer = self._new_board(tx, agent, 'offer', now, identifier, request_id=request['id'], resource=request['resource'],
                quantity=request['remaining'], claimed_by=agent['id'], commitment_id=commitment_id,
                text=f"I will supply {request['remaining']} {request['resource']} using {action}.", interpretation=note, origin=origin)
        return offer

    def _coordinate(self, tx, state, agents, now):
        board = self._requests(tx)
        for row in board:
            if row['status'] not in ('open', 'claimed') or state['resources'][row['resource']] < MAX_RESOURCE:
                continue
            # Other real production can satisfy the storage need while a model
            # offer waits. Cancel the obsolete obligation, never fabricate delivery.
            reason = f"Shared {row['resource']} storage is full; this request can no longer add stock."
            row.update(status='superseded', resolution_reason=reason)
            tx.put('colonyBoard', row)
            if row.get('commitment_id'):
                commitment = tx.get('colonyCommitments', row['commitment_id'])
                if commitment:
                    commitment.update(status='cancelled', reason='storage_full')
                    tx.put('colonyCommitments', commitment)
                for agent in agents:
                    if (agent.get('active_commitment') or {}).get('id') == row['commitment_id']:
                        agent.update(active_commitment=None, assignment='auto', assignment_origin='deterministic')
                        tx.put('islandAgents', agent)
                        self._new_board(tx, agent, 'reflection', now, key_for(row['id'], 'storage-full'),
                                actor_id='executor', actor_name='Island executor', text=reason,
                                request_id=row['id'], origin='executor', verified=True)
        for row in board:
            if row['kind'] != 'request' or row['status'] not in ('open', 'claimed') or _time(row['expires_at']) > now:
                continue
            row['status'] = 'expired'
            tx.put('colonyBoard', row)
            if row.get('commitment_id'):
                commitment = tx.get('colonyCommitments', row['commitment_id'])
                if commitment:
                    commitment['status'] = 'expired'
                    tx.put('colonyCommitments', commitment)
                for agent in agents:
                    if (agent.get('active_commitment') or {}).get('id') == row['commitment_id']:
                        agent.update(active_commitment=None, assignment='auto', assignment_origin='deterministic')
                        tx.put('islandAgents', agent)
        if model_controlled(self, state):
            return  # Actual agents publish requests and volunteer; expiry above remains authoritative.
        project = self._choose_project(state)
        if not project or not agents:
            return
        for resource, cost in self._cost(project).items():
            if state['resources'][resource] >= cost * 3:
                continue
            requester = next((agent for agent in agents if not resource_actions(agent, resource)), agents[0])
            quantity = min(8, max(1, cost * 3 - state['resources'][resource]))
            state['board_sequence'] = state.get('board_sequence', 0) + 1
            request = self._request(tx, state, requester, resource, quantity, project['id'], now,
                                    key_for(self.world_id, 'request', str(state['board_sequence'])))
            if request['status'] != 'open':
                continue
            candidates = [agent for agent in agents if agent['id'] != request['actor_id'] and not agent.get('active_commitment')
                          and agent['assignment'] == 'auto' and resource_actions(agent, resource)]
            if not candidates:
                continue
            supplier = min(candidates, key=lambda agent: (agent['completed_actions'], agent['id']))
            action = max(resource_actions(supplier, resource), key=lambda candidate: supplier['action_yields'][candidate][resource])
            self._claim(tx, state, supplier, request, action, now, key_for(request['id'], supplier['id'], 'offer'))

    def _ensure_profiles(self, tx, state, now):
        """Explicit version migration, scoped to colony actors; committed history is immutable."""
        changed = False
        for agent in self._agents(tx):
            if agent.get('sdk_version') == SDK_VERSION:
                continue
            character = tx.get('worldCharacters', agent['character_id'])
            if character is None or character['world_id'] != self.world_id:
                raise StoreError('An actor lost its accepted source identity.', 503, 'actor_identity_invariant')
            profile = capability_profile(character)
            allowed, yields = profile['allowed_actions'], profile['action_yields']
            active = agent.get('active_commitment')
            if active and (active['action'] not in allowed or active['resource'] not in yields.get(active['action'], {})):
                commitment = tx.get('colonyCommitments', active['id'])
                request = tx.get('colonyBoard', active['request_id'])
                if commitment and commitment['status'] == 'accepted':
                    commitment.update(status='cancelled', reason='capability_profile_updated')
                    tx.put('colonyCommitments', commitment)
                if request and request.get('commitment_id') == active['id'] and request['status'] == 'claimed':
                    request.update(status='open', claimed_by=None, commitment_id=None)
                    tx.put('colonyBoard', request)
                agent.update(active_commitment=None, assignment='auto', assignment_origin='deterministic')
            if agent['assignment'] not in ['auto', *allowed]:
                agent.update(assignment='auto', assignment_origin='deterministic')
            if agent.get('pending_decision_action') not in allowed:
                agent.pop('pending_decision_action', None)
                agent.pop('pending_decision_id', None)
            agent.update({key: deepcopy(profile[key]) for key in ('allowed_actions', 'capabilities', 'action_yields', 'resource_sources')})
            agent['sdk_version'] = SDK_VERSION
            agent['available_assignments'] = [{'id': action, 'label': ACTION_LABELS[action]} for action in ['auto', *allowed]]
            if agent.get('persona_provenance', {}).get('origin') == 'rules':
                agent['persona'].update({key: profile[key] for key in ('preferred_action', 'role', 'motto', 'goal', 'temperament')})
            elif agent['persona']['preferred_action'] not in allowed:
                agent['persona']['preferred_action'] = profile['preferred_action']
            task = agent.get('task')
            valid = task and task['kind'] in allowed and (task['kind'] in ('build', 'rest') or
                     set(task['gain']) == set(yields.get(task['kind'], {})))
            if not valid:
                # Production reserves no stock. Unsupported unfinished production is
                # replaced before it can mint an effect; supported in-flight work stays.
                self._schedule(state, agent, _time(state['paused_at']) if state['paused'] else now)
            event_id = key_for(self.world_id, 'capability-profile', agent['id'], SDK_VERSION)
            description = f"{agent['display_name']}'s accepted object capabilities were updated to {SDK_VERSION}."
            tx.put('islandEvents', {'_id': event_id, 'id': event_id, 'world_id': self.world_id,
                    'kind': 'capability_profile', 'at': _iso(now), 'character_id': agent['character_id'],
                    'title': 'Object capabilities updated', 'description': description,
                    'resource_delta': {}, 'sdk_version': SDK_VERSION})
            self._memory(agent, {'id': event_id, 'at': _iso(now), 'text': description, 'kind': 'capability_profile'})
            tx.put('islandAgents', agent)
            changed = True
        if changed:
            state['revision'] += 1
            tx.put('islandState', state)

    def _advance(self, tx, now):
        before = tx.get('islandState', self.state_id)
        if before:
            self._ensure_profiles(tx, before, now)
        super()._advance(tx, now)
        if before and not before['paused'] and now > _time(before['last_tick_at']):
            state = tx.get('islandState', self.state_id)
            agents = self._agents(tx)
            self._run_council(tx, state, agents, now)
            self._coordinate(tx, state, agents, now)
            tx.put('islandState', state)

    def _complete(self, tx, state, agent, at):
        decision = tx.get('colonyDecisions', agent['task'].get('decision_id')) if agent['task'].get('decision_id') else None
        with agent_span('task.complete', island_id=self.repo.colony_id, actor_id=agent['id'],
                        link_trace_id=(decision or {}).get('trace_id'), link_span_id=(decision or {}).get('span_id')):
            return self._complete_work(tx, state, agent, at)

    def _complete_work(self, tx, state, agent, at):
        task = deepcopy(agent['task'])
        super()._complete(tx, state, agent, at)
        if task.get('project_id'):
            completed_project = self._project(state, task['project_id'])
            if completed_project and completed_project.get('kind') == 'assembly' and completed_project['level'] >= completed_project['max_level']:
                ColonyLearningStore(self.repo.parent).complete_blueprint_tx(tx, self.world_id, completed_project)
        receipt = tx.get('islandEvents', task['id'])
        if (not receipt or receipt.get('world_id') != self.world_id
                or receipt.get('character_id') != agent['character_id'] or receipt.get('action_id') != task['id']):
            raise StoreError('Completed work has no matching committed action receipt.', 503, 'island_receipt_invariant')
        decision = tx.get('colonyDecisions', task['decision_id']) if task.get('decision_id') else None
        accepted_decision = bool(decision and decision.get('world_id') == self.world_id
                                 and decision.get('actor_id') == agent['id']
                                 and decision.get('character_id') == agent['character_id']
                                 and decision.get('status') == 'accepted')
        receipt.update(colony_id=self.repo.colony_id, sdk_version=SDK_VERSION,
                       decision_origin=task.get('decision_origin', 'deterministic'), decision_id=task.get('decision_id'),
                       council_id=task.get('council_id'),
                       decision_run_id=decision.get('run_id') if accepted_decision else None,
                       decision_evidence='accepted_decision' if accepted_decision else
                                         'missing_reference' if task.get('decision_id') else 'not_applicable',
                       request_id=task.get('request_id'), commitment_id=task.get('commitment_id'))
        tx.put('islandEvents', receipt)
        record_event(tx, self.repo.root_world_id, event_id=key_for(receipt['id'], 'completed'), kind='task.completed',
                     island_id=self.repo.colony_id, actor_id=agent['id'], actor_name=agent['display_name'],
                     message=receipt['description'], data={'receipt_id': receipt['id'], 'resource_delta': receipt['resource_delta'],
                         'project_id': task.get('project_id'), 'decision_id': task.get('decision_id'),
                         'council_id': task.get('council_id'),
                         'decision_origin': receipt['decision_origin'], 'execution_origin': receipt['execution_origin'],
                         'receipt_version': receipt['receipt_version'], 'reserved_cost': receipt['reserved_cost'],
                         'resource_net_delta': receipt['resource_net_delta'],
                         'scheduling_reason': receipt.get('scheduling_reason'), 'action_switched': receipt.get('action_switched', False),
                         'progress_delta': receipt.get('progress_delta', 0)}, at=_iso(at))
        notice = {'kind': task['kind'], 'reason': task.get('scheduling_reason', '')}
        if (task.get('decision_origin') == 'model' or task.get('action_switched') or task.get('council_id') or
                (task['kind'] == 'rest' and agent.get('last_executor_notice') != notice)):
            self._new_board(tx, agent, 'report', at, key_for(receipt['id'], 'execution-report'),
                    text=receipt['description'], interpretation=task.get('scheduling_reason', ''),
                    receipt_ids=[receipt['id']], origin='executor', verified=True,
                    decision_id=task.get('decision_id'), requested_decision_id=task.get('requested_decision_id'),
                    council_id=task.get('council_id'),
                    session_id=decision.get('session_id') if accepted_decision else None,
                    resource_delta=deepcopy(receipt['resource_delta']), progress_delta=receipt.get('progress_delta', 0))
        agent['last_executor_notice'] = notice
        contributions = agent['contributions']
        for resource, quantity in receipt['resource_delta'].items():
            contributions['resources'][resource] += quantity
        contributions['work'] += receipt.get('progress_delta', 0)
        if task.get('commitment_id'):
            commitment = tx.get('colonyCommitments', task['commitment_id'])
            request = tx.get('colonyBoard', task['request_id'])
            if commitment and request and commitment['status'] == 'accepted' and request['status'] == 'claimed' and at <= _time(commitment['expires_at']):
                delivered = min(commitment['remaining'], receipt['resource_delta'].get(commitment['resource'], 0))
                if delivered:
                    commitment['remaining'] -= delivered
                    commitment['receipt_ids'] = [*commitment['receipt_ids'], receipt['id']][-24:]
                    request['remaining'] = commitment['remaining']
                    request['receipt_ids'] = [*request['receipt_ids'], receipt['id']][-24:]
                    contributions['cooperative_units'] += delivered
                    state['cooperative_deliveries'] = state.get('cooperative_deliveries', 0) + 1
                    link_id = key_for(receipt['id'], commitment['id'], 'contribution')
                    tx.put('colonyContributions', {'_id': link_id, 'id': link_id, 'world_id': self.world_id,
                            'request_id': request['id'], 'requester_id': request['actor_id'], 'supplier_id': agent['id'],
                            'commitment_id': commitment['id'], 'receipt_id': receipt['id'], 'resource': commitment['resource'],
                            'quantity': delivered, 'project_id': request.get('project_id'), 'created_at': _iso(at),
                            'meaning': 'Produced into shared colony stock in answer to a request; not physical delivery.'})
                    self._new_board(tx, agent, 'report', at, key_for(receipt['id'], 'board-report'),
                            text=f"I supplied {delivered} {commitment['resource']} for {request['actor_name']}'s request.",
                            request_id=request['id'], resource=commitment['resource'], quantity=delivered,
                            receipt_ids=[receipt['id']], origin='deterministic', verified=True)
                    if commitment['remaining'] == 0:
                        commitment['status'], request['status'] = 'fulfilled', 'fulfilled'
                        state['fulfilled_requests'] = state.get('fulfilled_requests', 0) + 1
                        if (agent.get('active_commitment') or {}).get('id') == commitment['id']:
                            agent.update(active_commitment=None, assignment='auto', assignment_origin='deterministic')
                            if agent['task'].get('commitment_id') == commitment['id']:
                                for key in ('commitment_id', 'request_id'):
                                    agent['task'].pop(key, None)
                    else:
                        agent['active_commitment'] = public(commitment)
                    tx.put('colonyCommitments', commitment)
                    tx.put('colonyBoard', request)
        tx.put('islandAgents', agent)


class ColoniesStore(DeliberationMixin):
    def __init__(self, repo):
        self.repo, self.world_id = repo, repo.world_id
        self.state_id = key_for(self.world_id, 'colonies-mode')
        self.learning = ColonyLearningStore(repo)
        self.islands = {side: _ColonyIsland(_ScopedRepository(repo, side)) for side in COLONY_IDS}

    def ensure_indexes(self):
        self.learning.ensure_indexes()
        if not hasattr(self.repo, 'db'):
            return
        db = self.repo.db
        db.colonyResidents.create_index([('world_id', 1), ('canonical_type_id', 1)], unique=True)
        db.colonyPlacements.create_index([('world_id', 1), ('battle_id', 1), ('player_slot', 1)], unique=True)
        db.colonyBoard.create_index([('world_id', 1), ('kind', 1), ('status', 1), ('created_at', -1)])
        db.colonyProjectOpinions.create_index([('world_id', 1), ('actor_id', 1)], unique=True)
        for collection in ('colonyBoard', 'colonyCommitments', 'colonyDecisions', 'colonyContributions'):
            db[collection].create_index([('world_id', 1), ('created_at', -1)])
        for island in self.islands.values():
            island.ensure_indexes()

    def initialize(self):
        def enroll(tx):
            battles = tx.find('battles', {'world_id': self.world_id, 'status': 'completed'}, sort='completed_at', limit=BACKFILL_LIMIT + 1)
            if len(battles) > BACKFILL_LIMIT:
                raise StoreError('Historical enrollment exceeds this bounded backfill batch.', 422, 'backfill_limit')
            for battle in sorted(battles, key=lambda row: (row['completed_at'], row['id'])):
                route_completed_battle(tx, battle, self.world_id)
            if not tx.get('colonyModes', self.state_id):
                tx.put('colonyModes', {'_id': self.state_id, 'world_id': self.world_id, 'enabled': True, 'created_at': self.repo.clock()})
        self.repo.transaction(enroll)
        for island in self.islands.values():
            island.initialize()
            self._refresh_learning(island)
        return self.snapshot()

    def advance(self):
        enabled = self.repo.read(lambda tx: bool(tx.get('colonyModes', self.state_id)))
        if not enabled:
            return self.snapshot()
        for island in self.islands.values():
            # Explicitly enabled colony mode enrolls newly routed battle residents.
            with agent_span('island.advance', island_id=island.repo.colony_id):
                island.initialize()
                self._refresh_learning(island)
        return self.snapshot()

    def _refresh_learning(self, island):
        def refresh(tx):
            residents = tx.find('colonyResidents', {'world_id': island.world_id}, limit=501)
            for resident in residents:
                placement = tx.get('colonyPlacements', key_for(self.world_id, 'colony-placement', resident['first_battle_id'], str(resident['first_player_slot'])))
                self.learning.initialize_resident(tx, resident, accepted_fighter=(placement or {}).get('accepted_fighter'),
                                                 placement_id=(placement or {}).get('id'))
            result = self.learning.refresh_arrivals(tx, island.world_id, island.repo.colony_id, residents)
            if result.get('changed'):
                record_event(tx, self.world_id, event_id=key_for(island.world_id, 'capabilities', result['fingerprint']),
                             kind='capabilities.changed', island_id=island.repo.colony_id,
                             message='The roster changed. Reconsider blocked projects, experiments and collaborators.', data=result)
            return result
        return self.repo.transaction(refresh)

    def _side(self, colony_id):
        if colony_id not in self.islands:
            raise StoreError('Choose Winner Island or Loser Island.', 422, 'invalid_colony')
        return self.islands[colony_id]

    def _metrics(self, characters, snapshot):
        agents = snapshot['agents']
        produced = {resource for agent in agents for action in agent['allowed_actions']
                    if (resource := action_resource(agent, action)) is not None}
        values = [character['estimated_value_gbp'] for character in characters if character.get('estimated_value_gbp') is not None]
        return {'resident_count': len(characters), 'active_agents': len(agents), 'completed_actions': snapshot.get('completed_actions', 0),
                'project_levels': sum(project['level'] for project in snapshot['projects']),
                'resource_total': sum(snapshot['resources'].values()), 'fulfilled_requests': snapshot.get('fulfilled_requests', 0),
                'cooperative_deliveries': snapshot.get('cooperative_deliveries', 0),
                'capability_gaps': [resource for resource in RESOURCE_KEYS if resource not in produced],
                'market_value': None, 'valuation_status': 'user_estimates' if values else 'unknown',
                'estimated_total_gbp': round(sum(values), 2) if values else None,
                'estimated_mean_gbp': round(sum(values) / len(values), 2) if values else None,
                'valued_residents': len(values), 'unknown_value_residents': len(characters) - len(values)}

    def snapshot(self):
        mode = self.repo.read(lambda tx: tx.get('colonyModes', self.state_id))
        colonies = []
        for colony_id, island in self.islands.items():
            snapshot = island.snapshot()
            characters = island.repo.read(lambda tx: tx.find('worldCharacters', {'world_id': island.world_id}, sort='unlocked_at', limit=501))
            board = island.repo.read(lambda tx: island._board(tx))[:BOARD_LIMIT]
            planning = island.repo.read(lambda tx: island._planning_view(tx, tx.get('islandState', island.state_id), island._agents(tx), island._now()))
            metrics = self._metrics(characters, snapshot)
            metrics['open_requests'] = island.repo.read(lambda tx: len(island._requests(tx)))
            colonies.append({'id': colony_id, 'name': COLONY_NAMES[colony_id], 'characters': [public(row) for row in characters[:500]],
                             'island': snapshot, 'board': [public(row) for row in reversed(board)], 'metrics': metrics,
                             'planning': planning, 'council': deepcopy(snapshot.get('council', [])),
                             'learning': self.learning.snapshot(island.world_id),
                             'world': {'id': island.world_id, 'name': COLONY_NAMES[colony_id], 'layout_seed': 4127}})
        left, right = (colony['metrics']['project_levels'] for colony in colonies)
        return {'enabled': bool(mode), 'server_time': self.repo.clock(), 'persistence': self.repo.persistence, 'colonies': colonies,
                'placement_policy': 'one_resident_per_side_and_canonical_type', 'sdk_version': SDK_VERSION,
                'decision_mode': 'model_councils_with_validated_execution' if self.repo.settings.gemini_api_key else 'explicit_rule_preview',
                'comparison': {'project_level_leader': 'tie' if left == right else 'winners' if left > right else 'losers',
                    'price_comparison': 'unavailable', 'note': 'Battle outcomes determine placement. User estimates are descriptive, never powers or rewards. This is not a controlled experiment.'}}

    def _actor(self, tx, island, agent_id):
        agent = tx.get('islandAgents', agent_id)
        if agent is None:
            agent = tx.get('islandAgents', key_for(island.world_id, 'island-agent', agent_id))
        if agent is None or agent.get('world_id') != island.world_id:
            raise StoreError('That actor does not belong to this colony.', 404, 'actor_not_found')
        return agent

    def observation(self, colony_id, agent_id):
        island = self._side(colony_id)
        def read(tx):
            state = tx.get('islandState', island.state_id)
            if state is None:
                raise StoreError('Start the colonies before requesting an actor observation.', 409, 'colonies_not_started')
            agent = self._actor(tx, island, agent_id)
            board = island._requests(tx)[:12]
            receipts = tx.find('islandEvents', {'world_id': island.world_id, 'character_id': agent['character_id']}, sort='at', limit=6)
            all_agents = island._agents(tx)
            return {'colony_id': colony_id, 'sdk_version': SDK_VERSION, 'revision': state['revision'], 'paused': state['paused'],
                    'actor': {key: deepcopy(agent.get(key)) for key in ('id', 'character_id', 'display_name', 'object_type', 'allowed_actions',
                              'capabilities', 'action_yields', 'resource_sources', 'persona', 'assignment', 'task', 'memory', 'active_commitment', 'contributions')},
                    'resources': deepcopy(state['resources']), 'projects': deepcopy(state['projects']), 'active_project_id': state['active_project_id'],
                    'work_options': island._work_options(state, agent, island._choose_project(deepcopy(state))),
                    'board': [public(row) for row in board], 'last_receipts': [public(row) for row in receipts if 'sequence' in row][:4],
                    'planning': island._planning_view(tx, state, all_agents, island._now()),
                    'council': [{key: deepcopy(row[key]) for key in ('id', 'at', 'chosen_project_id', 'reason', 'origin', 'votes', 'model_message_ids')} for row in state.get('council', [])[-1:]],
                    'project_discussion': island._project_discussion(tx, island._now()),
                    'known_capability_gaps': [resource for resource in RESOURCE_KEYS if not any(resource_actions(other, resource) for other in all_agents)],
                    'limits': {'message_characters': PUBLIC_TEXT_LIMIT, 'request_quantity': 8, 'board_expiry_seconds': BOARD_SECONDS,
                               'project_opinion_expiry_seconds': PROJECT_OPINION_SECONDS},
                    'authority': 'Propose only accepted actions; requests and offers do not create resources. Shared stock is abstract, not physical cargo. Sentience, walking, loose-material gathering and basic construction are shared game attributes.'}
        result = island.repo.read(read)
        result['learning'] = self.learning.snapshot(island.world_id)
        result['peers'] = [{k: deepcopy(a.get(k)) for k in ('id', 'character_id', 'display_name', 'capabilities', 'allowed_actions', 'action_yields', 'active_commitment')}
                           for a in island.snapshot()['agents'] if a['id'] != agent_id]
        return result

    def apply_decision(self, colony_id, agent_id, decision, run_id, provenance=None):
        island = self._side(colony_id)
        if not isinstance(run_id, str) or not 1 <= len(run_id) <= 160:
            raise StoreError('A decision needs a durable reasoning run identifier.', 422, 'invalid_run_id')
        now = island._now()
        def apply(tx):
            agent = self._actor(tx, island, agent_id)
            value = validate_decision(agent, decision)
            fingerprint = sha256(json.dumps(value.model_dump(), sort_keys=True, separators=(',', ':')).encode()).hexdigest()
            decision_id = key_for(island.world_id, 'decision', agent['id'], run_id)
            existing = tx.get('colonyDecisions', decision_id)
            if existing:
                if existing['fingerprint'] != fingerprint:
                    # New optional SDK fields must not invalidate replay of an old
                    # accepted turn. Normalize both DTOs without rewriting history.
                    prior = validate_decision(agent, existing['decision'])
                    if prior.model_dump() != value.model_dump():
                        raise StoreError('That actor turn already has a different immutable decision.', 409, 'decision_conflict')
                return public(existing)
            if provenance and provenance.get('session_id'):
                from .colony_planner import population_fingerprint
                session = tx.get('colonyCouncilSessions', provenance['session_id'])
                run = tx.get('colonyReasoning', run_id)
                if (not session or session.get('world_id') != self.world_id or session.get('colony_id') != colony_id
                        or agent['id'] not in {a['id'] for a in session.get('participants', [])}
                        or session.get('status') != 'running' or not run
                        or run.get('world_id') != self.world_id or run.get('session_id') != session['id']
                        or run.get('agent_id') != agent['id'] or run.get('status') != 'applying'
                        or run_id not in session.get('run_ids', [])):
                    raise StoreError('The model turn is outside its active durable council.', 409, 'invalid_council_session')
                expected = {key: run.get(key) for key in ('session_id', 'reply_to_id', 'seen_message_ids', 'model', 'turn_index')}
                if any(provenance.get(key) != value for key, value in expected.items()):
                    raise StoreError('The council message provenance does not match its saved model turn.', 409, 'invalid_council_session')
                if population_fingerprint({'island': {'agents': island._agents(tx)}}) != session['population_fingerprint']:
                    raise StoreError('New residents or capabilities changed this island. Reopen the council before committing this turn.', 409, 'population_changed')
            state = tx.get('islandState', island.state_id)
            if state is None or state['paused']:
                raise StoreError('The colony must be running to accept a new decision.', 409, 'colony_paused')
            # Settle overdue work before a new decision can influence future tasks.
            island._advance(tx, now)
            state = tx.get('islandState', island.state_id)
            agent = self._actor(tx, island, agent_id)
            value = validate_decision(agent, decision)
            if (value.action or value.claim_request_id) and agent.get('assignment_origin') == 'player' and agent['assignment'] != 'auto':
                raise StoreError('This resident has a player-selected assignment.', 409, 'player_assignment')
            if agent.get('last_decision_at') and (now - _time(agent['last_decision_at'])).total_seconds() < 2:
                raise StoreError('Wait for the previous actor turn to settle.', 429, 'actor_rate_limit')
            request_id = value.claim_request_id or (value.message.request_id if value.message and value.message.kind == 'offer' else None)
            records = []
            learning_results = {}
            if value.experiment:
                learning_results['experiment'] = self.learning.run_experiment_tx(tx, island.world_id, agent['id'], value.experiment.model_dump(), key_for(decision_id, 'experiment'))
                state = tx.get('islandState', island.state_id)
            if value.blueprint:
                blueprint = self.learning.propose_blueprint_tx(tx, island.world_id, agent['id'], value.blueprint.model_dump(), key_for(decision_id, 'blueprint'))
                learning_results['blueprint'] = blueprint
                project = blueprint.get('project')
                if project and not any(p['id'] == project['id'] for p in state['projects']):
                    state['projects'].append(deepcopy(project))
            if value.message and value.message.kind in ('question', 'reflection'):
                records.append(island._new_board(tx, agent, value.message.kind, now, key_for(decision_id, value.message.kind),
                                                text=value.message.text, origin='model', project_id=value.message.project_id))
            if request_id:
                request = tx.get('colonyBoard', request_id)
                if request is None or request.get('world_id') != island.world_id:
                    raise StoreError('The request is outside this colony.', 404, 'request_not_found')
                records.append(island._claim(tx, state, agent, request, value.action, now, key_for(decision_id, 'offer'),
                                            origin='model', decision_id=decision_id, note=value.message.text if value.message else value.reason))
            elif value.action:
                if agent.get('active_commitment') and value.action != agent['active_commitment']['action']:
                    raise StoreError('Finish the accepted contribution before changing work.', 409, 'commitment_busy')
                agent.update(assignment=value.action, assignment_origin='model', pending_decision_action=value.action,
                             pending_decision_id=decision_id)
            if value.message and value.message.kind == 'request':
                if value.message.project_id and not any(project['id'] == value.message.project_id for project in state['projects']):
                    raise StoreError('The requested project is not part of this colony.', 422, 'invalid_project')
                records.append(island._request(tx, state, agent, value.message.resource, value.message.quantity,
                        value.message.project_id or state['active_project_id'], now, key_for(decision_id, 'request'), 'model', value.message.text))
            elif value.message and value.message.kind == 'report':
                receipt = tx.get('islandEvents', value.message.receipt_id)
                if receipt is None or receipt.get('world_id') != island.world_id or receipt.get('character_id') != agent['character_id'] or 'sequence' not in receipt:
                    raise StoreError('A report requires this actor’s committed action receipt.', 422, 'invalid_report_evidence')
                records.append(island._new_board(tx, agent, 'report', now, key_for(decision_id, 'report'),
                        text=receipt['description'], receipt_ids=[receipt['id']], verified=True,
                        interpretation=value.message.text, origin='model'))
            if value.message and value.message.kind in ('proposal', 'support', 'objection'):
                message = value.message
                project = island._project(state, message.project_id)
                if project is None or project['level'] >= project['max_level']:
                    raise StoreError('Project opinions need an unfinished project in this colony.', 422, 'invalid_project')
                if message.proposal_id:
                    proposal = tx.get('colonyBoard', message.proposal_id)
                    if proposal is None or proposal['world_id'] != island.world_id or proposal['kind'] != 'proposal' or proposal.get('project_id') != project['id']:
                        raise StoreError('The proposal is outside this colony or project.', 422, 'invalid_proposal_evidence')
                candidate = next(row for row in island._assess_projects(state, island._agents(tx)) if row['project_id'] == project['id'])
                record_id = key_for(decision_id, 'project-opinion')
                opinion_expiry = _iso(now + timedelta(seconds=PROJECT_OPINION_SECONDS))
                row = island._new_board(tx, agent, message.kind, now, record_id,
                        project_id=project['id'], proposal_id=message.proposal_id, expires_at=opinion_expiry,
                        text=f"{agent['display_name']} submitted a project {message.kind} for {project['name'].lower()}. " + candidate['reason'],
                        interpretation=message.text, origin='model', feasibility=candidate, verified=False,
                        effect='One actor opinion for the next due crew council; it is not a direct project command.')
                records.append(row)
                tx.put('colonyProjectOpinions', {'_id': key_for(island.world_id, 'project-opinion', agent['id']),
                        'world_id': island.world_id, 'actor_id': agent['id'], 'character_id': agent['character_id'],
                        'project_id': project['id'], 'kind': message.kind, 'message_id': record_id, 'decision_id': decision_id,
                        'created_at': _iso(now), 'expires_at': opinion_expiry, 'origin': 'model'})
            agent.update(last_decision_at=_iso(now), decision_origin='model', decision_reason=value.reason)
            if learning_results and not records:
                records.append(island._new_board(tx, agent, 'reflection', now, key_for(decision_id, 'research'),
                    text=value.reason or 'The executor recorded this resident’s research submission. Inspect the attached evidence for its outcome.',
                    origin='model' if value.reason else 'executor', evidence=learning_results))
            for row in records:
                if provenance:
                    if row['actor_id'] != agent['id'] or row['world_id'] != island.world_id:
                        raise StoreError('A published turn must own its board message.', 503, 'board_author_invariant')
                    row.update({key: deepcopy(provenance[key]) for key in ('session_id', 'reply_to_id', 'seen_message_ids', 'model', 'turn_index', 'trace_id', 'span_id') if key in provenance})
                    row['council_id'] = provenance.get('session_id')
                    row['run_id'] = run_id
                    tx.put('colonyBoard', row)
                    record_event(tx, self.world_id, event_id=key_for(row['id'], 'model-publication'),
                                 kind='agent.message' if row.get('origin') == 'model' else 'research.recorded',
                                 island_id=colony_id, actor_id=agent['id'], actor_name=agent['display_name'],
                                 session_id=provenance.get('session_id'), message=board_text(row),
                                 data={'message_id': row['id'], 'reply_to_id': row.get('reply_to_id'), 'model': row.get('model'),
                                       'origin': row.get('origin'), 'run_id': run_id, 'message_kind': row['kind'],
                                       'receipt_ids': deepcopy(row.get('receipt_ids', [])),
                                       'evidence_kind': 'execution_report' if row.get('receipt_ids') else 'board_message',
                                       **report_commentary(row)})
            tx.put('islandAgents', agent)
            state['revision'] += 1
            tx.put('islandState', state)
            record = {'_id': decision_id, 'id': decision_id, 'world_id': island.world_id, 'colony_id': colony_id,
                      'actor_id': agent['id'], 'character_id': agent['character_id'], 'run_id': run_id,
                      'fingerprint': fingerprint, 'created_at': _iso(now), 'decision': value.model_dump(),
                      'status': 'accepted', 'board_ids': [row['id'] for row in records], 'learning_results': learning_results,
                      'trace_id': (provenance or {}).get('trace_id'), 'span_id': (provenance or {}).get('span_id'),
                      'assignment_effect': 'Current task is preserved; accepted action applies when the next task is scheduled.'}
            tx.put('colonyDecisions', record)
            return public(record)
        with agent_span('agent.validate_apply', island_id=colony_id, actor_id=agent_id, session_id=(provenance or {}).get('session_id'),
                        link_trace_id=(provenance or {}).get('trace_id'), link_span_id=(provenance or {}).get('span_id')):
            accepted = island.repo.transaction(apply)
        return {'decision': accepted, 'message_ids': accepted['board_ids'], 'message_id': next(iter(accepted['board_ids']), None)}

    def command(self, body):
        body = deepcopy(body)
        island = self._side(body.pop('colony_id', None))
        if body.get('kind') == 'value':
            self._value(island, body)
        else:
            island.command(body)
        return self.snapshot()

    def _value(self, island, body):
        if set(body) - {'kind', 'idempotency_key', 'character_id', 'estimated_value_gbp'}:
            raise StoreError('Unsupported estimate fields.', 422, 'invalid_estimate')
        amount = body.get('estimated_value_gbp')
        if isinstance(amount, bool) or not isinstance(amount, (int, float)) or not math.isfinite(amount) or not 0 <= amount <= 1000000:
            raise StoreError('Enter a finite GBP estimate between zero and one million.', 422, 'invalid_estimate')
        request_id = body.get('idempotency_key')
        if not isinstance(request_id, str) or not 8 <= len(request_id) <= 128:
            raise StoreError('An estimate needs a durable request key.', 422, 'invalid_estimate')
        identifier = key_for(island.world_id, 'estimate', request_id)
        fingerprint = sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()
        def apply(tx):
            existing = tx.get('colonyEstimates', identifier)
            if existing:
                if existing['fingerprint'] != fingerprint:
                    raise StoreError('This estimate key already holds different data.', 409, 'estimate_conflict')
                return
            resident = tx.get('worldCharacters', body.get('character_id', ''))
            if resident is None or resident['world_id'] != island.world_id:
                raise StoreError('The resident is outside this colony.', 404, 'resident_not_found')
            estimate = round(amount, 2)
            resident.update(estimated_value_gbp=estimate, valuation_status='user_estimate',
                            valuation_provenance={'kind': 'user_estimate', 'currency': 'GBP', 'recorded_at': self.repo.clock()})
            tx.put('worldCharacters', resident)
            tx.put('colonyEstimates', {'_id': identifier, 'id': identifier, 'world_id': island.world_id,
                    'character_id': resident['id'], 'estimated_value_gbp': estimate, 'fingerprint': fingerprint,
                    'created_at': self.repo.clock(), 'kind': 'user_estimate', 'changes_capabilities': False})
        island.repo.transaction(apply)
