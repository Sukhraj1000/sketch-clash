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

from .agent_sdk import SDK_VERSION, AgentDecision, action_resource, capability_profile, resource_actions, validate_decision
from .island import (IslandStore, ACTION_LABELS, RESOURCE_LOCATIONS, RESOURCE_KEYS, MAX_AGENTS, MAX_RESOURCE,
                     _position, _iso, _time)
from .repository import StoreError, key_for, public

COLONY_IDS = ('winners', 'losers')
COLONY_NAMES = {'winners': 'Winner Island', 'losers': 'Loser Island'}
BOARD_SECONDS = 300
BOARD_LIMIT = 80
BACKFILL_LIMIT = 1000


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
        if not isinstance(body, dict) or body.get('kind') != 'assign':
            return super().command(body, now)
        allowed = {'idempotency_key', 'kind', 'project_id', 'character_id', 'assignment', 'expected_revision'}
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

    def _choose_action(self, state, agent, project):
        assigned = agent['assignment']
        if assigned != 'auto':
            if assigned not in agent['allowed_actions']:
                raise StoreError('Saved assignment exceeds accepted capabilities.', 503, 'capability_invariant')
            if assigned != 'build' or self._can_build(state, project):
                return assigned
        costs = self._cost(project) if project else {}
        shortages = sorted(costs, key=lambda resource: state['resources'][resource] / costs[resource])
        for resource in shortages:
            actions = resource_actions(agent, resource)
            if actions and state['resources'][resource] < costs[resource] * 3:
                return max(actions, key=lambda action: agent['action_yields'][action][resource])
        if self._can_build(state, project):
            return 'build'
        if project and any(state['resources'][resource] < cost for resource, cost in costs.items()):
            return 'rest'  # A missing capability is a visible dependency, never a new power.
        preferred = agent['persona']['preferred_action']
        resource = action_resource(agent, preferred)
        if resource and state['resources'][resource] < 40:
            return preferred
        return 'explore'

    def _schedule(self, state, agent, start):
        project = self._choose_project(state)
        action = self._choose_action(state, agent, project)
        if action not in agent['allowed_actions']:
            raise StoreError('Scheduler proposed an unsupported capability.', 503, 'capability_invariant')
        sequence = agent['completed_actions'] + 1
        task_id = key_for(self.world_id, 'action', agent['character_id'], str(sequence))
        seed = int(task_id[:8], 16)
        duration = 14 + seed % 5
        task = {'id': task_id, 'kind': action, 'title': ACTION_LABELS[action], 'started_at': _iso(start),
                'ends_at': _iso(start + timedelta(seconds=duration)), 'duration_seconds': duration,
                'from': deepcopy(agent['position']), 'to': deepcopy(agent['position']), 'gain': {},
                'progress_gain': 0, 'project_id': None, 'resource': None, 'xp_gain': 3,
                'sdk_version': SDK_VERSION, 'decision_origin': 'deterministic', 'decision_id': None}
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
            task.update(title='Wait for a useful contribution' if project else 'Take a quiet breather',
                        to={'x': -.7, 'z': 1.1}, xp_gain=0)
        else:
            resource = action_resource(agent, action)
            if resource is None:
                raise StoreError('A production action has no accepted yield.', 503, 'capability_invariant')
            amount = agent['action_yields'][action][resource] + self._resource_bonus(state, resource) + (agent['level'] - 1) // 5
            task['gain'] = {resource: min(amount, max(0, MAX_RESOURCE - state['resources'][resource]))}
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
        agent['task'], agent['updated_at'] = task, _iso(start)

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
        return value

    def _request(self, tx, state, agent, resource, quantity, project_id, now, identifier, origin='deterministic', note=''):
        requests = self._requests(tx)
        existing = next((row for row in requests if row['resource'] == resource and row.get('project_id') == project_id), None)
        if existing:
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
            self._coordinate(tx, state, self._agents(tx), now)
            tx.put('islandState', state)

    def _complete(self, tx, state, agent, at):
        task = deepcopy(agent['task'])
        super()._complete(tx, state, agent, at)
        receipt = tx.get('islandEvents', task['id'])
        receipt.update(colony_id=self.repo.colony_id, sdk_version=SDK_VERSION,
                       decision_origin=task.get('decision_origin', 'deterministic'), decision_id=task.get('decision_id'),
                       request_id=task.get('request_id'), commitment_id=task.get('commitment_id'))
        tx.put('islandEvents', receipt)
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


class ColoniesStore:
    def __init__(self, repo):
        self.repo, self.world_id = repo, repo.world_id
        self.state_id = key_for(self.world_id, 'colonies-mode')
        self.islands = {side: _ColonyIsland(_ScopedRepository(repo, side)) for side in COLONY_IDS}

    def ensure_indexes(self):
        if not hasattr(self.repo, 'db'):
            return
        db = self.repo.db
        db.colonyResidents.create_index([('world_id', 1), ('canonical_type_id', 1)], unique=True)
        db.colonyPlacements.create_index([('world_id', 1), ('battle_id', 1), ('player_slot', 1)], unique=True)
        db.colonyBoard.create_index([('world_id', 1), ('kind', 1), ('status', 1), ('created_at', -1)])
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
        return self.snapshot()

    def advance(self):
        enabled = self.repo.read(lambda tx: bool(tx.get('colonyModes', self.state_id)))
        if not enabled:
            return self.snapshot()
        for island in self.islands.values():
            # Explicitly enabled colony mode enrolls newly routed battle residents.
            island.initialize()
        return self.snapshot()

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
            metrics = self._metrics(characters, snapshot)
            metrics['open_requests'] = island.repo.read(lambda tx: len(island._requests(tx)))
            colonies.append({'id': colony_id, 'name': COLONY_NAMES[colony_id], 'characters': [public(row) for row in characters[:500]],
                             'island': snapshot, 'board': [public(row) for row in reversed(board)], 'metrics': metrics,
                             'world': {'id': island.world_id, 'name': COLONY_NAMES[colony_id], 'layout_seed': 4127}})
        left, right = (colony['metrics']['project_levels'] for colony in colonies)
        return {'enabled': bool(mode), 'server_time': self.repo.clock(), 'persistence': self.repo.persistence, 'colonies': colonies,
                'placement_policy': 'one_resident_per_side_and_canonical_type', 'sdk_version': SDK_VERSION,
                'decision_mode': 'capability_rules_with_optional_validated_agent_decisions',
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
                    'board': [public(row) for row in board], 'last_receipts': [public(row) for row in receipts if 'sequence' in row][:4],
                    'known_capability_gaps': [resource for resource in RESOURCE_KEYS if not any(resource_actions(other, resource) for other in all_agents)],
                    'limits': {'message_characters': 240, 'request_quantity': 8, 'board_expiry_seconds': BOARD_SECONDS},
                    'authority': 'Propose only accepted actions; requests and offers do not create resources. Shared stock is abstract, not physical cargo. Sentience, walking, loose-material gathering and basic construction are shared game attributes.'}
        return island.repo.read(read)

    def apply_decision(self, colony_id, agent_id, decision, run_id):
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
                    raise StoreError('That actor turn already has a different immutable decision.', 409, 'decision_conflict')
                return public(existing)
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
            agent.update(last_decision_at=_iso(now), decision_origin='model', decision_reason=value.reason)
            tx.put('islandAgents', agent)
            state['revision'] += 1
            tx.put('islandState', state)
            record = {'_id': decision_id, 'id': decision_id, 'world_id': island.world_id, 'colony_id': colony_id,
                      'actor_id': agent['id'], 'character_id': agent['character_id'], 'run_id': run_id,
                      'fingerprint': fingerprint, 'created_at': _iso(now), 'decision': value.model_dump(),
                      'status': 'accepted', 'board_ids': [row['id'] for row in records],
                      'assignment_effect': 'Current task is preserved; accepted action applies when the next task is scheduled.'}
            tx.put('colonyDecisions', record)
            return public(record)
        accepted = island.repo.transaction(apply)
        return {'decision': accepted}

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
