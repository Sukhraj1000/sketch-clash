"""Durable, inexpensive object-agent simulation; no model calls or gameplay mutations.

MongoDB stores agent state and an append-only action journal. A local worker may
call ``advance`` every few seconds; all effects and scheduling share one world
transaction. Reading a snapshot never starts, resumes, or advances a world.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
import math
from typing import Any

from .repository import StoreError, key_for, public

SIMULATION_VERSION = 'object-island-v1'
RECEIPT_VERSION = 'island-action-v2'
MAX_AGENTS = 40
MAX_RESOURCE = 1000
MAX_CATCH_UP_SECONDS = 120
MAX_MEMORY = 20
MAX_LEVEL = 20
RESOURCE_KEYS = ('materials', 'water', 'ideas', 'energy')
COMMON_ACTIONS = ('forage', 'build', 'rest', 'explore')
ACTION_LABELS = {
    'auto': 'Choose a useful job', 'forage': 'Gather supplies', 'build': 'Build the priority project',
    'rest': 'Take a breather', 'explore': 'Explore the shoreline', 'carry': 'Carry materials',
    'water': 'Deliver water', 'plan': 'Draw plans', 'measure': 'Survey the island',
    'charge': 'Collect energy', 'signal': 'Scout with signals', 'tend': 'Tend the nursery',
}
ACTION_RESOURCE = {
    'carry': 'materials', 'water': 'water', 'plan': 'ideas', 'measure': 'ideas',
    'charge': 'energy', 'signal': 'energy', 'tend': 'water',
}
RESOURCE_LOCATIONS = {
    'materials': {'x': -3.25, 'z': 1.2}, 'water': {'x': -.25, 'z': -2.9},
    'ideas': {'x': .15, 'z': .7}, 'energy': {'x': 3.65, 'z': .55},
}
PROJECT_DEFINITIONS = (
    {'id': 'garden', 'kind': 'garden', 'name': 'Community garden',
     'description': 'A growing nursery that makes water deliveries more effective.',
     'position': {'x': -2.1, 'z': -1.7}, 'base_progress': 18,
     'cost_per_action': {'materials': 1, 'water': 1},
     'reward': '+1 water per delivery for each garden level'},
    {'id': 'workshop', 'kind': 'workshop', 'name': 'Object workshop',
     'description': 'A shared workshop that improves every materials delivery.',
     'position': {'x': 2.1, 'z': -1.5}, 'base_progress': 22,
     'cost_per_action': {'materials': 2, 'ideas': 1},
     'reward': '+1 materials per delivery for each workshop level'},
    {'id': 'beacon', 'kind': 'beacon', 'name': 'Discovery beacon',
     'description': 'A lookout for new ideas, stories, and useful places to explore.',
     'position': {'x': 0, 'z': 2.5}, 'base_progress': 26,
     'cost_per_action': {'materials': 1, 'ideas': 1, 'energy': 1},
     'reward': '+1 ideas per delivery for each beacon level'},
    {'id': 'boardwalk', 'kind': 'boardwalk', 'name': 'Shoreline boardwalk',
     'description': 'A route around the island that improves energy gathering.',
     'position': {'x': 3.3, 'z': 1.6}, 'base_progress': 22,
     'cost_per_action': {'materials': 2, 'water': 1},
     'reward': '+1 energy per delivery for each boardwalk level'},
)
AFFORDANCES = (
    (('mug', 'cup', 'bowl', 'bucket', 'basket', 'bag', 'box'), 'carry', ['carry', 'contain'],
     'Quartermaster', 'Dependable and sociable', 'A little help carries a long way.', 'Keep our builders supplied.'),
    (('bottle', 'watering', 'jug', 'kettle'), 'water', ['store_water', 'pour'],
     'Water keeper', 'Patient and generous', 'Small drops make a thriving island.', 'Keep the nursery and builders watered.'),
    (('pencil', 'pen', 'marker', 'crayon', 'book', 'notebook'), 'plan', ['draw', 'plan'],
     'Island architect', 'Inventive and thoughtful', 'Every good place begins with a sketch.', 'Turn the island’s next idea into a useful plan.'),
    (('ruler', 'tape measure', 'measuring', 'level', 'caliper'), 'measure', ['measure', 'align'],
     'Surveyor', 'Precise and quietly curious', 'A careful measure makes a steady home.', 'Help each project fit its place.'),
    (('phone', 'radio', 'camera', 'computer', 'tablet', 'watch'), 'signal', ['observe', 'signal'],
     'Signal scout', 'Observant and adventurous', 'There is always something beyond the shore.', 'Find useful signals for our next discovery.'),
    (('battery', 'lamp', 'torch', 'light', 'charger'), 'charge', ['store_energy', 'illuminate'],
     'Energy keeper', 'Bright and encouraging', 'Let’s keep a little light for everyone.', 'Keep enough energy for the island to explore.'),
    (('plant', 'flower', 'leaf', 'seed', 'tree'), 'tend', ['grow', 'nurture'],
     'Nursery keeper', 'Gentle and persistent', 'Good things grow one day at a time.', 'Make the island a greener place to live.'),
)
def _time(value: str | datetime | float | int) -> datetime:
    if isinstance(value, datetime):
        result = value
    elif isinstance(value, (float, int)):
        result = datetime.fromtimestamp(value, timezone.utc)
    else:
        result = datetime.fromisoformat(value.replace('Z', '+00:00'))
    return result.replace(tzinfo=timezone.utc) if result.tzinfo is None else result.astimezone(timezone.utc)


def _iso(value: datetime) -> str:
    return value.isoformat()


def _position(value: dict | None) -> dict:
    value = value or {}
    x, z = float(value.get('x', 0)), float(value.get('z', 0))
    if not math.isfinite(x) or not math.isfinite(z):
        x, z = 0., 0.
    radius = math.hypot(x, z)
    if radius > 4.6:
        x, z = x * 4.6 / radius, z * 4.6 / radius
    return {'x': round(x, 3), 'z': round(z, 3)}


def _affordance(character: dict) -> dict:
    identity = ' '.join(str(character.get(k, '')) for k in ('canonical_type_id', 'object_type')).lower().replace('_', ' ').replace('-', ' ')
    # Word starts avoid matching "pen" in "open" while allowing pencils / bottles.
    words = identity.split()
    for tokens, action, capabilities, role, temperament, motto, goal in AFFORDANCES:
        if any(any(word.startswith(token) for word in words) if ' ' not in token else token in identity for token in tokens):
            return {'action': action, 'capabilities': capabilities, 'role': role,
                    'temperament': temperament, 'motto': motto, 'goal': goal}
    return {'action': 'explore', 'capabilities': ['explore', 'gather'], 'role': 'Resource scout',
            'temperament': 'Curious and adaptable', 'motto': 'I wonder what we could make from that.',
            'goal': 'Find the small things our next project needs.'}


class IslandStore:
    def __init__(self, repo):
        self.repo = repo
        self.world_id = repo.world_id
        self.state_id = key_for(self.world_id, 'island-state')

    def _now(self, now=None) -> datetime:
        return _time(self.repo.clock() if now is None else now)

    def ensure_indexes(self) -> None:
        """Explicit startup setup, never part of GET/snapshot or a model action."""
        if hasattr(self.repo, 'db'):
            self.repo.db.islandAgents.create_index([('world_id', 1), ('character_id', 1)], unique=True)
            self.repo.db.islandEvents.create_index([('world_id', 1), ('at', -1)])
            self.repo.db.islandEvents.create_index([('world_id', 1), ('character_id', 1), ('at', -1)])

    def _agents(self, tx) -> list[dict]:
        return sorted(tx.find('islandAgents', {'world_id': self.world_id}, limit=MAX_AGENTS + 1), key=lambda a: a['character_id'])[:MAX_AGENTS]

    def _snapshot(self, tx, now: datetime) -> dict:
        state = tx.get('islandState', self.state_id)
        limits = {'max_active_agents': MAX_AGENTS, 'offline_catchup_seconds': MAX_CATCH_UP_SECONDS,
                  'resource_capacity': MAX_RESOURCE, 'max_agent_level': MAX_LEVEL, 'max_project_level': 3}
        if not state:
            return {'enabled': False, 'world_id': self.world_id, 'persistence': self.repo.persistence,
                    'server_time': _iso(now), 'revision': 0, 'paused': False, 'paused_at': None,
                    'last_tick_at': None, 'active_project_id': None, 'growth_level': 0,
                    'resources': {key: 0 for key in RESOURCE_KEYS}, 'projects': [], 'agents': [], 'events': [],
                    'expeditions': 0, 'discoveries': [], 'limits': limits,
                    'catch_up': {'simulated_seconds': 0, 'discarded_seconds': 0}, 'inactive_residents': 0,
                    'simulation_version': SIMULATION_VERSION}
        result = public(state)
        result.pop('command_count', None)
        result['agents'] = [public(agent) for agent in self._agents(tx)]
        events = tx.find('islandEvents', {'world_id': self.world_id}, sort='at', limit=40)
        result['events'] = list(reversed([public(event) for event in events if event.get('kind') != 'command'][:24]))
        for project in result['projects']:
            project['cost_per_action'] = self._cost(project)
        result.update({'enabled': True, 'server_time': _iso(now), 'persistence': self.repo.persistence, 'limits': limits})
        return result

    def snapshot(self) -> dict:
        now = self._now()
        return self.repo.read(lambda tx: self._snapshot(tx, now))

    def initialize(self, now=None) -> dict:
        now = self._now(now)
        def operation(tx):
            state = tx.get('islandState', self.state_id)
            if state is not None:
                self._advance(tx, now)
                state = tx.get('islandState', self.state_id)
            changed = False
            if state is None:
                projects = [{**deepcopy(definition), 'level': 0, 'max_level': 3, 'progress': 0,
                             'required_progress': definition['base_progress'], 'status': 'planned',
                             'reserved_progress': 0, 'workers': [], 'completed_at': None}
                            for definition in PROJECT_DEFINITIONS]
                state = {'_id': self.state_id, 'id': self.state_id, 'world_id': self.world_id,
                         'simulation_version': SIMULATION_VERSION, 'revision': 0, 'paused': False, 'paused_at': None,
                         'created_at': _iso(now), 'last_tick_at': _iso(now), 'active_project_id': 'garden',
                         'resources': {'materials': 8, 'water': 4, 'ideas': 3, 'energy': 3},
                         'projects': projects, 'growth_level': 1, 'completed_actions': 0,
                         'expeditions': 0, 'discoveries': [], 'inactive_residents': 0,
                         'catch_up': {'simulated_seconds': 0, 'discarded_seconds': 0}}
                changed = True
            characters = sorted(tx.find('worldCharacters', {'world_id': self.world_id}, limit=501),
                                key=lambda c: (c.get('unlocked_at', ''), c['id']))
            agents = self._agents(tx)
            existing = {agent['character_id'] for agent in agents}
            # Keep existing residents stable when a newer unlock sorts differently.
            available = [character for character in characters if character['id'] not in existing]
            for character in available[:max(0, MAX_AGENTS - len(agents))]:
                agent = self._new_agent(character, now)
                agents.append(agent)
                tx.put('islandAgents', agent)
                changed = True
            inactive = max(0, len(characters) - len(agents))
            if state['inactive_residents'] != inactive:
                state['inactive_residents'] = inactive
                changed = True
            start = _time(state['paused_at']) if state['paused'] else now
            for agent in sorted(agents, key=lambda a: a['character_id']):
                if not agent.get('task'):
                    self._schedule(state, agent, start)
                    tx.put('islandAgents', agent)
                    changed = True
            if changed:
                state['revision'] += 1
                tx.put('islandState', state)
            return self._snapshot(tx, now)
        return self.repo.transaction(operation)

    def _new_agent(self, character: dict, now: datetime) -> dict:
        affordance = _affordance(character)
        actions = list(COMMON_ACTIONS)
        if affordance['action'] not in actions:
            actions.append(affordance['action'])
        persona = {'name': character.get('display_name', character['object_type']), 'role': affordance['role'],
                   'temperament': affordance['temperament'], 'motto': affordance['motto'],
                   'goal': affordance['goal'], 'preferred_action': affordance['action'],
                   'lesson': '', 'basis_event_ids': []}
        agent_id = key_for(self.world_id, 'island-agent', character['id'])
        return {'_id': agent_id, 'id': agent_id, 'world_id': self.world_id, 'character_id': character['id'],
                'display_name': character.get('display_name', character['object_type']),
                'object_type': character['object_type'], 'canonical_type_id': character['canonical_type_id'],
                'persona': persona, 'capabilities': affordance['capabilities'], 'allowed_actions': actions,
                'available_assignments': [{'id': action, 'label': ACTION_LABELS[action]} for action in ['auto', *actions]],
                'assignment': 'auto', 'xp': 0, 'level': 1, 'completed_actions': 0,
                'position': _position(character.get('home_position')), 'task': None, 'memory': [],
                'created_at': _iso(now), 'updated_at': _iso(now),
                'persona_provenance': {'origin': 'rules', 'generated_at': _iso(now), 'basis': 'object_affordances'}}

    def _project(self, state: dict, project_id: str | None = None) -> dict | None:
        return next((project for project in state['projects'] if project['id'] == (project_id or state['active_project_id'])), None)

    def _choose_project(self, state: dict) -> dict | None:
        active = self._project(state)
        if active and active['level'] < active['max_level']:
            return active
        incomplete = [project for project in state['projects'] if project['level'] < project['max_level']]
        selected = min(incomplete, key=lambda p: (p['level'], [d['id'] for d in PROJECT_DEFINITIONS].index(p['id']))) if incomplete else None
        state['active_project_id'] = selected['id'] if selected else None
        return selected

    def _cost(self, project: dict) -> dict:
        return {key: value + project['level'] for key, value in project['cost_per_action'].items()}

    def _needed_resource(self, state: dict, project: dict | None) -> str:
        if project:
            costs = self._cost(project)
            return min(costs, key=lambda key: (state['resources'][key] / costs[key], RESOURCE_KEYS.index(key)))
        return min(RESOURCE_KEYS, key=lambda key: state['resources'][key])

    def _can_build(self, state: dict, project: dict | None) -> bool:
        return bool(project and len(project['workers']) < 2
                    and project['progress'] + project['reserved_progress'] < project['required_progress']
                    and all(state['resources'][key] >= value for key, value in self._cost(project).items()))

    def _choose_action(self, state: dict, agent: dict, project: dict | None) -> str:
        assignment = agent['assignment']
        if assignment != 'auto':
            return assignment if assignment != 'build' or self._can_build(state, project) else 'forage'
        preferred = agent['persona']['preferred_action']
        resource = ACTION_RESOURCE.get(preferred)
        costs = self._cost(project) if project else {}
        if resource and state['resources'][resource] < costs.get(resource, 1) * 4:
            return preferred
        if preferred == 'build' and self._can_build(state, project):
            return 'build'
        if agent['completed_actions'] % 3 == 1 and resource and state['resources'][resource] < 60:
            return preferred
        if self._can_build(state, project):
            return 'build'
        if project and any(state['resources'][key] < value * 2 for key, value in costs.items()):
            # Every resident can gather a missing supply slowly, so any object set is viable.
            return preferred if resource == self._needed_resource(state, project) else 'forage'
        if resource and state['resources'][resource] < 60:
            return preferred
        return 'explore'

    def _resource_bonus(self, state: dict, resource: str) -> int:
        project_id = {'water': 'garden', 'materials': 'workshop', 'ideas': 'beacon', 'energy': 'boardwalk'}[resource]
        return next(project['level'] for project in state['projects'] if project['id'] == project_id)

    def _schedule(self, state: dict, agent: dict, start: datetime) -> None:
        resources_before_reservation = deepcopy(state['resources'])
        project = self._choose_project(state)
        action = self._choose_action(state, agent, project)
        expedition_cost = {'materials': 2, 'water': 1, 'energy': 2} if action == 'explore' and project is None else {}
        missing_supply = None
        if expedition_cost and any(state['resources'][key] < amount for key, amount in expedition_cost.items()):
            missing_supply = min(expedition_cost, key=lambda key: state['resources'][key] / expedition_cost[key])
            action = 'forage'
            expedition_cost = {}
        sequence = agent['completed_actions'] + 1
        task_id = key_for(self.world_id, 'action', agent['character_id'], str(sequence))
        seed = int(task_id[:8], 16)
        duration = 14 + seed % 5
        task = {'id': task_id, 'kind': action, 'title': ACTION_LABELS[action], 'started_at': _iso(start),
                'ends_at': _iso(start + timedelta(seconds=duration)), 'duration_seconds': duration,
                'from': deepcopy(agent['position']), 'to': deepcopy(agent['position']),
                'gain': {}, 'progress_gain': 0, 'project_id': None, 'resource': None, 'xp_gain': 3,
                'decision_origin': 'player' if agent['assignment'] == action else 'deterministic', 'decision_id': None}
        if expedition_cost:
            for key, amount in expedition_cost.items():
                state['resources'][key] -= amount
            task['cost'] = expedition_cost
        if action == 'build' and project:
            progress = min(2 + ('measure' in agent['allowed_actions']) + (agent['level'] - 1) // 5,
                           project['required_progress'] - project['progress'] - project['reserved_progress'])
            costs = self._cost(project)
            for key, value in costs.items():
                state['resources'][key] -= value
            project['reserved_progress'] += progress
            project['workers'].append(agent['character_id'])
            project['status'] = 'building'
            workspot = {'x': project['position']['x'] + (seed % 3 - 1) * .25,
                        'z': project['position']['z'] + (.8 if project['kind'] == 'beacon' else 1.0)}
            task.update({'title': f"Build {project['name'].lower()}", 'to': _position(workspot),
                         'project_id': project['id'], 'project_level': project['level'], 'progress_gain': progress,
                         'cost': costs, 'xp_gain': 5})
        elif action == 'rest':
            task.update({'title': 'Take a quiet breather', 'to': {'x': -.7, 'z': 1.1}, 'xp_gain': 0})
        else:
            resource = missing_supply or ACTION_RESOURCE.get(action) or self._needed_resource(state, project)
            base = {'carry': 4, 'water': 4, 'plan': 3, 'measure': 3, 'charge': 3, 'signal': 3, 'tend': 3}.get(action, 2)
            if action == 'forage' and resource != 'materials':
                base = 1
            amount = base + self._resource_bonus(state, resource) + (agent['level'] - 1) // 5
            amount = min(amount, max(0, MAX_RESOURCE - state['resources'][resource]))
            destination = deepcopy(RESOURCE_LOCATIONS[resource])
            if action == 'explore':
                angle = (seed % 360) * math.tau / 360
                destination = {'x': round(math.cos(angle) * 4.15, 3), 'z': round(math.sin(angle) * 4.15, 3)}
                task['title'] = 'Explore the shoreline'
            elif action == 'forage':
                task['title'] = f'Gather {resource} for the island'
            destination['x'] = round(destination['x'] + ((seed >> 6) % 5 - 2) * .10, 3)
            destination['z'] = round(destination['z'] + ((seed >> 9) % 5 - 2) * .10, 3)
            task.update({'resource': resource, 'gain': {resource: amount}, 'to': _position(destination)})
        self._record_reservation(task, agent, resources_before_reservation, state['resources'])
        agent['task'] = task
        agent['updated_at'] = _iso(start)

    def _record_reservation(self, task: dict, agent: dict, before: dict, after: dict) -> None:
        """Freeze the scheduling evidence; subsequent decisions cannot relabel it."""
        task.update(resources_before_reservation=deepcopy(before), resources_after_reservation=deepcopy(after),
                    capability_basis={'object_type': agent['object_type'],
                                      'capabilities': deepcopy(agent['capabilities']),
                                      'allowed_action': task['kind'] in agent['allowed_actions'],
                                      'declared_yield': deepcopy(agent.get('action_yields', {}).get(task['kind'], {})),
                                      'resource_sources': deepcopy(agent.get('resource_sources', {})),
                                      'sdk_version': agent.get('sdk_version')})

    @staticmethod
    def _project_evidence(project: dict | None) -> dict | None:
        if project is None:
            return None
        return {key: deepcopy(project.get(key)) for key in
                ('id', 'name', 'level', 'progress', 'required_progress', 'reserved_progress', 'status')}

    def _memory(self, agent: dict, entry: dict) -> None:
        agent['memory'] = [*agent['memory'], entry][-MAX_MEMORY:]

    def _complete(self, tx, state: dict, agent: dict, at: datetime) -> None:
        task = agent['task']
        # This journal key is also the durable idempotency boundary for every resource effect.
        if tx.get('islandEvents', task['id']):
            raise StoreError('The action journal and current task disagree.', 503, 'island_invariant')
        resources_before = deepcopy(state['resources'])
        project_before = self._project_evidence(self._project(state, task['project_id'])) if task.get('project_id') else None
        agent_before = {'xp': agent['xp'], 'level': agent['level'], 'position': deepcopy(agent['position'])}
        deltas = {}
        for key, amount in task['gain'].items():
            before = state['resources'][key]
            state['resources'][key] = min(MAX_RESOURCE, max(0, before + amount))
            deltas[key] = state['resources'][key] - before
        title = task['title']
        description = f"{agent['display_name']} finished {title.lower()}."
        progress_delta = 0
        milestone = None
        if task['kind'] == 'build':
            project = self._project(state, task['project_id'])
            if project is None or project['level'] != task['project_level']:
                raise StoreError('A reserved project changed unexpectedly.', 503, 'island_invariant')
            project['workers'].remove(agent['character_id'])
            project['reserved_progress'] -= task['progress_gain']
            progress_delta = task['progress_gain']
            project['progress'] += progress_delta
            description = f"{agent['display_name']} added {progress_delta} work to {project['name'].lower()}."
            if project['progress'] >= project['required_progress']:
                if project['reserved_progress'] or project['workers']:
                    raise StoreError('Project work exceeded its reserved target.', 503, 'island_invariant')
                project['level'] += 1
                project['completed_at'] = _iso(at)
                project['progress'] = 0
                project['required_progress'] = project['base_progress'] + project['level'] * 12
                project['status'] = 'complete' if project['level'] >= project['max_level'] else 'planned'
                state['growth_level'] = 1 + sum(p['level'] for p in state['projects'])
                milestone = {'id': key_for(task['id'], 'milestone'), 'at': _iso(at), 'kind': 'milestone',
                             'character_id': agent['character_id'], 'project_id': project['id'],
                             'title': f"{project['name']} reached level {project['level']}",
                             'description': project['reward'], 'resource_delta': {}, 'progress_delta': 0}
                if state['active_project_id'] == project['id']:
                    state['active_project_id'] = None
                    self._choose_project(state)
        elif task['kind'] == 'explore':
            state['expeditions'] += 1
            discovery_id = key_for(task['id'], 'discovery')
            gains = ', '.join(f'{amount} {key}' for key, amount in deltas.items() if amount)
            discovery = {'id': discovery_id, 'at': _iso(at), 'character_id': agent['character_id'],
                         'title': f'Shoreline survey: {gains}' if gains else 'Shoreline survey: storage full',
                         'receipt_id': task['id'], 'origin': 'local_executor',
                         'position': deepcopy(task['to']), 'resource_delta': deepcopy(deltas)}
            state['discoveries'] = [*state['discoveries'], discovery][-24:]
            description = (f"{agent['display_name']} completed a shoreline survey and added {gains} to shared stock."
                           if gains else f"{agent['display_name']} completed a shoreline survey; full storage prevented a resource gain.")
        if deltas and task['kind'] != 'explore':
            gains = ', '.join(f'{amount} {key}' for key, amount in deltas.items() if amount)
            description = (f"{agent['display_name']} completed {title.lower()} and added {gains} to shared stock."
                           if gains else f"{agent['display_name']} completed {title.lower()}; full storage prevented a resource gain.")
        if task['kind'] == 'rest':
            description = f"{agent['display_name']} rested; no resources or construction work were added."
            if task.get('scheduling_reason'):
                description += ' ' + task['scheduling_reason']
        old_level = agent['level']
        agent['xp'] = min(1000000, agent['xp'] + task['xp_gain'])
        agent['level'] = min(MAX_LEVEL, 1 + math.isqrt(agent['xp'] // 24))
        agent['completed_actions'] += 1
        agent['position'] = deepcopy(task['to'])
        state['completed_actions'] += 1
        event = {'_id': task['id'], 'id': task['id'], 'world_id': self.world_id, 'at': _iso(at),
                 'kind': task['kind'], 'character_id': agent['character_id'], 'title': title,
                 'description': description, 'resource_delta': deltas, 'project_id': task.get('project_id'),
                 'progress_delta': progress_delta, 'xp_gain': task['xp_gain'], 'sequence': agent['completed_actions'],
                 'receipt_version': RECEIPT_VERSION, 'execution_origin': 'local_executor',
                 'action_id': task['id'], 'actor_id': agent['id'], 'actor_name': agent['display_name'],
                 'decision_origin': task.get('decision_origin', 'deterministic'), 'decision_id': task.get('decision_id'),
                 'started_at': task['started_at'], 'duration_seconds': task['duration_seconds'],
                 'resources_before': resources_before, 'resources_after': deepcopy(state['resources']),
                 'reserved_cost': deepcopy(task.get('cost', {})),
                 'resource_net_delta': {key: deltas.get(key, 0) - task.get('cost', {}).get(key, 0)
                                        for key in RESOURCE_KEYS if deltas.get(key, 0) or task.get('cost', {}).get(key, 0)},
                 'resources_before_reservation': deepcopy(task.get('resources_before_reservation')),
                 'resources_after_reservation': deepcopy(task.get('resources_after_reservation')),
                 'reservation_evidence': 'recorded' if 'resources_before_reservation' in task else 'legacy_task',
                 'project_before': project_before,
                 'project_after': self._project_evidence(self._project(state, task['project_id'])) if task.get('project_id') else None,
                 'agent_before': agent_before,
                 'agent_after': {'xp': agent['xp'], 'level': agent['level'], 'position': deepcopy(agent['position'])},
                 'capability_basis': deepcopy(task.get('capability_basis')),
                 'scheduling_reason': task.get('scheduling_reason'),
                 'requested_action': task.get('requested_action'),
                 'requested_decision_id': task.get('requested_decision_id'),
                 'action_switched': task.get('action_switched', False),
                 'effect_scope': 'abstract_island_ledger',
                 'effect_note': 'The local executor applies declared action yields and project work; this is not an observed real-world discovery.'}
        tx.put('islandEvents', event)
        self._memory(agent, {'id': task['id'], 'at': _iso(at), 'text': description, 'kind': task['kind']})
        if milestone:
            tx.put('islandEvents', {'_id': milestone['id'], 'world_id': self.world_id, **milestone})
            self._memory(agent, {'id': milestone['id'], 'at': _iso(at), 'text': milestone['title'], 'kind': 'milestone'})
        if agent['level'] > old_level:
            level_id = key_for(task['id'], 'level')
            tx.put('islandEvents', {'_id': level_id, 'id': level_id, 'world_id': self.world_id,
                    'at': _iso(at), 'kind': 'level', 'character_id': agent['character_id'],
                    'title': f"{agent['display_name']} reached level {agent['level']}",
                    'description': 'Experience stays with this resident across visits.', 'resource_delta': {}})
        self._schedule(state, agent, at)
        tx.put('islandAgents', agent)

    def _advance(self, tx, now: datetime) -> None:
        state = tx.get('islandState', self.state_id)
        if state is None or state['paused']:
            return
        elapsed = (now - _time(state['last_tick_at'])).total_seconds()
        if elapsed <= 0:
            return
        discarded = max(0, elapsed - MAX_CATCH_UP_SECONDS)
        agents = self._agents(tx)
        if discarded:
            # Shift unfinished tasks forward, discarding old time once, never banking it.
            for agent in agents:
                if agent.get('task'):
                    for field in ('started_at', 'ends_at'):
                        agent['task'][field] = _iso(_time(agent['task'][field]) + timedelta(seconds=discarded))
                    tx.put('islandAgents', agent)
        completed = 0
        while True:
            ready = [agent for agent in agents if agent.get('task') and _time(agent['task']['ends_at']) <= now]
            if not ready:
                break
            agent = min(ready, key=lambda item: (item['task']['ends_at'], item['character_id']))
            self._complete(tx, state, agent, _time(agent['task']['ends_at']))
            completed += 1
            if completed > MAX_AGENTS * (MAX_CATCH_UP_SECONDS // 14 + 2):
                raise StoreError('Simulation step exceeded its bounded action budget.', 503, 'island_budget')
        state['last_tick_at'] = _iso(now)
        state['catch_up'] = {'simulated_seconds': round(min(elapsed, MAX_CATCH_UP_SECONDS), 3),
                             'discarded_seconds': round(discarded, 3)}
        state['revision'] += 1
        tx.put('islandState', state)

    def advance(self, now=None) -> dict:
        now = self._now(now)
        def operation(tx):
            self._advance(tx, now)
            return self._snapshot(tx, now)
        return self.repo.transaction(operation)

    def command(self, body: dict, now=None) -> dict:
        now = self._now(now)
        allowed = {'idempotency_key', 'kind', 'project_id', 'character_id', 'assignment', 'expected_revision'}
        if not isinstance(body, dict) or set(body) - allowed:
            raise StoreError('The island command contains unsupported fields.', 422, 'invalid_island_command')
        request_id = body.get('idempotency_key')
        if not isinstance(request_id, str) or not 8 <= len(request_id) <= 128:
            raise StoreError('An island command needs an idempotency key of 8–128 characters.', 422, 'invalid_island_command')
        kind = body.get('kind')
        if kind not in ('pause', 'resume', 'priority', 'assign'):
            raise StoreError('Choose pause, resume, priority, or assign.', 422, 'invalid_island_command')
        fingerprint = sha256(json.dumps(body, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
        event_id = key_for(self.world_id, 'island-command', request_id)
        def operation(tx):
            previous = tx.get('islandEvents', event_id)
            if previous:
                if previous['fingerprint'] != fingerprint:
                    raise StoreError('That command key was already used for a different instruction.', 409, 'island_command_mismatch')
                return self._snapshot(tx, now)
            state = tx.get('islandState', self.state_id)
            if state is None:
                raise StoreError('Start island life before giving a direction.', 409, 'island_not_started')
            if body.get('expected_revision') is not None and body['expected_revision'] != state['revision']:
                raise StoreError('The island changed. Refresh before giving this direction.', 409, 'island_revision_conflict')
            self._advance(tx, now)
            state = tx.get('islandState', self.state_id)
            if kind == 'pause':
                if not state['paused']:
                    state.update({'paused': True, 'paused_at': _iso(now)})
            elif kind == 'resume':
                if state['paused']:
                    offset = max(0, (now - _time(state['paused_at'])).total_seconds())
                    for agent in self._agents(tx):
                        if agent.get('task'):
                            for field in ('started_at', 'ends_at'):
                                agent['task'][field] = _iso(_time(agent['task'][field]) + timedelta(seconds=offset))
                            tx.put('islandAgents', agent)
                    state.update({'paused': False, 'paused_at': None, 'last_tick_at': _iso(now)})
            elif kind == 'priority':
                project = self._project(state, body.get('project_id'))
                if not body.get('project_id') or project is None or project['level'] >= project['max_level']:
                    raise StoreError('Choose an island project with an unfinished upgrade.', 422, 'invalid_project')
                state['active_project_id'] = project['id']
            elif kind == 'assign':
                agent_id = key_for(self.world_id, 'island-agent', str(body.get('character_id', '')))
                agent = tx.get('islandAgents', agent_id)
                if agent is None or agent['world_id'] != self.world_id:
                    raise StoreError('That resident is not an active island agent.', 404, 'agent_not_found')
                if body.get('assignment') not in ['auto', *agent['allowed_actions']]:
                    raise StoreError('That task does not match this object’s capabilities.', 422, 'invalid_assignment')
                agent['assignment'] = body['assignment']
                agent['updated_at'] = _iso(now)
                tx.put('islandAgents', agent)
            state['revision'] += 1
            tx.put('islandState', state)
            tx.put('islandEvents', {'_id': event_id, 'id': event_id, 'world_id': self.world_id, 'kind': 'command',
                    'at': _iso(now), 'fingerprint': fingerprint, 'command': kind, 'title': ACTION_LABELS.get(body.get('assignment'), kind.title()),
                    'description': 'A player direction was saved. Ongoing tasks finish before a new assignment.',
                    'resource_delta': {}, 'character_id': body.get('character_id')})
            return self._snapshot(tx, now)
        return self.repo.transaction(operation)

    def set_persona(self, character_id: str, persona: dict, provenance: dict) -> dict:
        """Apply already generated, bounded persona/plan data; capabilities remain fixed."""
        fields = {'name': 60, 'role': 60, 'temperament': 140, 'motto': 180, 'goal': 240, 'lesson': 300}
        if not isinstance(persona, dict) or set(persona) - {*fields, 'preferred_action', 'basis_event_ids'}:
            raise StoreError('The persona contains unsupported fields.', 422, 'invalid_persona')
        for key, limit in fields.items():
            if key in persona and (not isinstance(persona[key], str) or len(persona[key]) > limit):
                raise StoreError('A persona field exceeds its text limit.', 422, 'invalid_persona')
        basis = persona.get('basis_event_ids', [])
        if not isinstance(basis, list) or len(basis) > 8 or any(not isinstance(item, str) or len(item) > 128 for item in basis):
            raise StoreError('A persona needs bounded source-event references.', 422, 'invalid_persona')
        if not isinstance(provenance, dict) or not isinstance(provenance.get('run_id'), str) or not 1 <= len(provenance['run_id']) <= 128:
            raise StoreError('Generated personas need a durable run identifier.', 422, 'invalid_persona')
        if set(provenance) - {'run_id', 'origin', 'model', 'model_version', 'generated_at', 'basis_event_ids'}:
            raise StoreError('Persona provenance contains unsupported fields.', 422, 'invalid_persona')
        for key, value in provenance.items():
            if key == 'basis_event_ids':
                continue
            if not isinstance(value, str) or len(value) > 180:
                raise StoreError('Persona provenance is invalid.', 422, 'invalid_persona')
        now = self._now()
        event_id = key_for(self.world_id, 'persona', character_id, provenance['run_id'])
        payload_hash = sha256(json.dumps({'persona': persona, 'provenance': provenance}, sort_keys=True).encode()).hexdigest()
        def operation(tx):
            state = tx.get('islandState', self.state_id)
            agent = tx.get('islandAgents', key_for(self.world_id, 'island-agent', character_id))
            if state is None or agent is None:
                raise StoreError('The resident agent is unavailable.', 404, 'agent_not_found')
            previous = tx.get('islandEvents', event_id)
            if previous:
                if previous['payload_hash'] != payload_hash:
                    raise StoreError('This persona run has already been applied with different data.', 409, 'persona_run_mismatch')
                return public(agent)
            if persona.get('preferred_action', agent['persona']['preferred_action']) not in agent['allowed_actions']:
                raise StoreError('The proposed plan is outside this object’s capabilities.', 422, 'invalid_persona')
            for source_id in basis:
                source = tx.get('islandEvents', source_id)
                if source is None or source['world_id'] != self.world_id:
                    raise StoreError('A persona cites an unavailable island event.', 422, 'invalid_persona')
            agent['persona'] = {**agent['persona'], **deepcopy(persona)}
            agent['persona_provenance'] = deepcopy(provenance)
            agent['updated_at'] = _iso(now)
            text = persona.get('lesson') or persona.get('goal') or agent['persona']['goal']
            self._memory(agent, {'id': event_id, 'at': _iso(now), 'text': text, 'kind': 'reflection'})
            tx.put('islandAgents', agent)
            tx.put('islandEvents', {'_id': event_id, 'id': event_id, 'world_id': self.world_id, 'at': _iso(now),
                    'kind': 'reflection', 'character_id': character_id, 'title': f"{agent['display_name']} made a plan",
                    'description': text, 'resource_delta': {}, 'payload_hash': payload_hash,
                    'provenance': deepcopy(provenance)})
            state['revision'] += 1
            tx.put('islandState', state)
            return public(agent)
        return self.repo.transaction(operation)
