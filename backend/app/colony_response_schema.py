"""Provider-side shapes mirror the SDK's conditional requirements.

Pydantic still validates the full response and the executor still checks evidence.
This only prevents asking the model to fill unrelated nullable fields, or a
support message without the project ID required by the SDK's validator.
"""
from copy import deepcopy

from .agent_sdk import AgentDecision


def _describe_string_limits(node):
    """Gemini ignores min/maxLength; descriptions communicate our real bounds.

    Keep the JSON Schema bounds for local consumers and the Pydantic validator.
    Never shorten a returned hypothesis, identifier or public message to fit.
    """
    if isinstance(node, dict):
        if node.get('type') == 'string' and ('minLength' in node or 'maxLength' in node):
            minimum, maximum = node.get('minLength', 0), node.get('maxLength')
            limit = (f'{minimum} to {maximum} characters' if minimum and maximum else
                     f'at most {maximum} characters' if maximum else f'at least {minimum} characters')
            guidance = f'Application validation requires {limit}; an overlong value is rejected, never truncated.'
            node['description'] = ' '.join(filter(None, [node.get('description'), guidance]))
        for child in node.values():
            _describe_string_limits(child)
    elif isinstance(node, list):
        for child in node:
            _describe_string_limits(child)


def _required_value(value):
    result = deepcopy(value)
    choices = result.get('anyOf')
    if choices:
        non_null = [row for row in choices if row.get('type') != 'null']
        result.pop('anyOf')
        result.update(non_null[0] if len(non_null) == 1 else {'anyOf': non_null})
    result.pop('default', None)
    if result.get('type') == 'string':
        result['minLength'] = max(1, result.get('minLength', 0))
    return result


def council_response_schema(allowed_actions=None):
    schema = AgentDecision.model_json_schema()
    definitions = schema['$defs']
    message = definitions['BoardMessage']
    variants = []
    for kinds, fields, required in (
        (['request'], ['resource', 'quantity', 'project_id'], ['resource', 'quantity']),
        (['offer'], ['request_id'], ['request_id']),
        (['report'], ['receipt_id'], ['receipt_id']),
        (['proposal', 'support', 'objection'], ['project_id', 'proposal_id'], ['project_id']),
        (['question', 'reflection'], ['project_id'], []),
    ):
        properties = {key: deepcopy(message['properties'][key]) for key in ['kind', 'text', *fields]}
        properties['kind'] = {'type': 'string', 'enum': kinds}
        for key in required:
            properties[key] = _required_value(properties[key])
        variants.append({'type': 'object', 'additionalProperties': False,
                         'properties': properties, 'required': ['kind', 'text', *required]})
    definitions['BoardMessage'] = {'anyOf': variants}

    experiment = definitions['ExperimentSpec']
    experiment['properties']['hypothesis']['description'] = (
        'One concise, testable prediction about the specified arrangement and conditions. '
        'Prefer under 240 characters; do not include a discussion transcript or blueprint description.')
    context = definitions['ExperimentContext']
    variants = []
    for family, keys in (('hold', ['wind_force', 'load', 'duration']),
                         ('contain', ['volume', 'distance', 'tilt_degrees']),
                         ('support', ['span', 'load', 'support_count'])):
        variant = deepcopy(experiment)
        variant['properties']['family'] = {'type': 'string', 'enum': [family]}
        variant['properties']['context'] = {'type': 'object', 'additionalProperties': False,
            'properties': {key: deepcopy(context['properties'][key]) for key in keys}, 'required': keys}
        variants.append(variant)
    definitions['ExperimentSpec'] = {'anyOf': variants}
    definitions.pop('ExperimentContext')
    if allowed_actions is not None:
        accepted = schema['properties']['action']['anyOf'][0]['enum']
        actions = [action for action in accepted if action in allowed_actions]
        schema['properties']['action'] = ({'anyOf': [{'type': 'string', 'enum': actions}, {'type': 'null'}]}
                                          if actions else {'type': 'null'})
    _describe_string_limits(schema)
    return schema
