"""Small, typed capability boundary for colony actors; no model or database authority."""
from __future__ import annotations

from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator

from .island import _affordance
from .repository import StoreError

Resource = Literal['materials', 'water', 'ideas', 'energy']
Action = Literal['forage', 'carry', 'water', 'plan', 'measure', 'charge', 'signal', 'tend', 'build', 'rest', 'explore']
SDK_VERSION = 'colony-capabilities-v2'
MAX_BOARD_QUANTITY = 8


class BoardMessage(BaseModel):
    model_config = ConfigDict(extra='forbid')
    kind: Literal['request', 'offer', 'report', 'proposal', 'support', 'objection']
    text: str = Field(default='', max_length=240)
    request_id: str | None = Field(default=None, max_length=128)
    resource: Resource | None = None
    quantity: int | None = Field(default=None, ge=1, le=MAX_BOARD_QUANTITY)
    project_id: str | None = Field(default=None, max_length=60)
    receipt_id: str | None = Field(default=None, max_length=128)
    proposal_id: str | None = Field(default=None, max_length=128)

    @model_validator(mode='after')
    def typed_payload(self):
        if self.kind == 'request' and (self.resource is None or self.quantity is None):
            raise ValueError('A request needs a resource and quantity.')
        if self.kind == 'offer' and not self.request_id:
            raise ValueError('An offer must answer a request.')
        if self.kind == 'report' and not self.receipt_id:
            raise ValueError('A report requires an executor receipt.')
        if self.kind in ('proposal', 'support', 'objection') and not self.project_id:
            raise ValueError('A project opinion requires a project identifier.')
        return self


class AgentDecision(BaseModel):
    model_config = ConfigDict(extra='forbid')
    action: Action | None = None
    reason: str = Field(default='', max_length=240)
    claim_request_id: str | None = Field(default=None, max_length=128)
    message: BoardMessage | None = None

    @model_validator(mode='after')
    def useful_decision(self):
        if self.action is None and self.message is None and not self.claim_request_id:
            raise ValueError('A decision must propose an action or a typed message.')
        if self.message and self.message.kind == 'offer' and self.claim_request_id and self.message.request_id != self.claim_request_id:
            raise ValueError('An offer and claim must refer to the same request.')
        return self


def capability_profile(character: dict) -> dict:
    """Accepted game affordances. These are declared rules, never learned powers.

    Common movement/gathering only supplies materials. A resident cannot acquire
    water, ideas or energy by selecting generic explore/forage. Containers gather
    water, stationery produces plans, electronics contribute observations, and plants
    tend a material-producing nursery. Batteries collect from a declared charging
    dock. Sentience, walking, gathering loose materials and basic construction
    assistance are explicit shared game attributes, not real-object claims.
    """
    affordance = _affordance(character)
    specialty = affordance['action']
    identity = ' '.join(str(character.get(key, '')) for key in ('canonical_type_id', 'object_type')).lower().replace('_', ' ').replace('-', ' ')
    words = identity.split()
    matches = lambda names: any(any(word.startswith(name) for word in words) for name in names)
    if matches(('pitcher', 'jug', 'kettle')) or 'watering can' in identity:
        specialty = 'water'
    elif matches(('television', 'monitor')) or 'tv' in words:
        specialty = 'signal'
    elif matches(('battery', 'charger', 'powerbank')) or 'power bank' in identity:
        specialty = 'charge'
    elif matches(('lamp', 'torch', 'light')):
        specialty = 'signal'
    actions = ['forage', 'build', 'rest', 'explore']
    yields = {'forage': {'materials': 1}, 'explore': {'materials': 1}}
    capabilities = ['move', 'gather_materials', 'assist_build']
    role, motto, goal = affordance['role'], affordance['motto'], affordance['goal']
    if specialty == 'carry':
        actions.append('carry')
        yields['carry'] = {'materials': 3}
        capabilities += ['carry_materials']
        if matches(('mug', 'cup', 'bowl', 'bucket')):
            actions.append('water')
            yields['water'] = {'water': 1}
            capabilities += ['contain_water', 'pour']
    elif specialty == 'water':
        actions += ['water', 'carry']
        yields.update(water={'water': 4}, carry={'materials': 1})
        capabilities += ['store_water', 'pour', 'carry_materials']
        role, motto, goal = 'Water keeper', 'Small drops make a thriving island.', 'Collect water at the cistern for shared projects.'
    elif specialty in ('plan', 'measure'):
        actions.append(specialty)
        yields[specialty] = {'ideas': 3}
        capabilities += ['draw_plans'] if specialty == 'plan' else ['measure', 'align']
    elif specialty == 'signal':
        actions.append('signal')
        yields['signal'] = {'ideas': 3}
        capabilities += ['observe', 'signal']
        role, motto, goal = 'Observation scout', 'A useful observation helps everyone.', 'Bring observations to the planning desk.'
        if matches(('lamp', 'torch', 'light')):
            capabilities += ['illuminate']
            role, motto, goal = 'Lookout light', 'Help the island see its next step.', 'Illuminate the lookout so useful details can be observed.'
    elif specialty == 'charge':
        actions.append('charge')
        yields['charge'] = {'energy': 3}
        capabilities += ['store_energy', 'transfer_from_dock']
        role, motto, goal = 'Energy courier', 'Bring stored power where it helps.', 'Collect energy from the island charging dock for shared projects.'
    elif specialty == 'tend':
        actions.append('tend')
        yields['tend'] = {'materials': 2}
        capabilities += ['grow', 'nurture']
    return {'version': SDK_VERSION, 'allowed_actions': actions, 'capabilities': list(dict.fromkeys(capabilities)),
            'action_yields': yields, 'preferred_action': specialty if specialty in actions else 'explore',
            'resource_sources': {'materials': 'Island grove and nursery', 'water': 'Island cistern',
                                 'ideas': 'Planning desk and observed signals', 'energy': 'Island charging dock'},
            'authority': 'declared_game_rules', 'role': role, 'motto': motto, 'goal': goal,
            'temperament': affordance['temperament']}


def action_resource(agent: dict, action: str) -> str | None:
    return next(iter(agent.get('action_yields', {}).get(action, {})), None)


def resource_actions(agent: dict, resource: str) -> list[str]:
    return [action for action in agent['allowed_actions'] if action_resource(agent, action) == resource]


def validate_decision(agent: dict, value: dict | AgentDecision) -> AgentDecision:
    from pydantic import ValidationError
    try:
        decision = value if isinstance(value, AgentDecision) else AgentDecision.model_validate(value)
    except ValidationError:
        raise StoreError('The decision does not match the colony capability SDK.', 422, 'invalid_agent_decision') from None
    if decision.action and decision.action not in agent['allowed_actions']:
        raise StoreError('This object cannot perform the proposed action.', 422, 'capability_denied')
    if decision.claim_request_id and decision.action is None:
        raise StoreError('Claiming work requires a capable proposed action.', 422, 'action_required')
    if decision.message and decision.message.kind == 'offer' and decision.action is None:
        raise StoreError('An offer must include the action that will fulfill it.', 422, 'action_required')
    return decision
