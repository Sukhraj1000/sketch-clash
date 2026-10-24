"""Provider shapes and server validation agree without discarding public dialogue."""
from copy import deepcopy
import json
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.agent_sdk import AgentDecision, PUBLIC_TEXT_LIMIT
from app.colony_response_schema import council_response_schema
from test_colony_planner import fixture


def test_provider_shape_requires_real_identifiers_and_omits_unrelated_test_inputs():
    before = deepcopy(AgentDecision.model_json_schema())
    schema = council_response_schema(['build', 'rest'])
    assert schema['properties']['action']['anyOf'][0]['enum'] == ['build', 'rest']
    assert council_response_schema([])['properties']['action'] == {'type': 'null'}
    messages = schema['$defs']['BoardMessage']['anyOf']
    for kinds, required in [(('proposal', 'support', 'objection'), 'project_id'), (('request',), 'quantity'), (('report',), 'receipt_id'), (('offer',), 'request_id')]:
        branch = next(row for row in messages if row['properties']['kind']['enum'] == list(kinds))
        assert required in branch['required']
        assert 'anyOf' not in branch['properties'][required], 'Mandatory identifiers/quantities cannot be null'
        if required.endswith('_id'):
            assert branch['properties'][required]['minLength'] == 1
        assert branch['additionalProperties'] is False
    for branch in schema['$defs']['ExperimentSpec']['anyOf']:
        family = branch['properties']['family']['enum'][0]
        context = branch['properties']['context']
        assert set(context['properties']) == {'hold': {'wind_force', 'load', 'duration'}, 'contain': {'volume', 'distance', 'tilt_degrees'}, 'support': {'span', 'load', 'support_count'}}[family]
        assert context['additionalProperties'] is False
        assert set(context['required']) == set(context['properties'])
    assert AgentDecision.model_json_schema() == before, 'Per-turn schemas cannot alter server authority or leak the previous actor permissions'


@pytest.mark.parametrize('family,context', [('hold', {'wind_force': 1, 'load': 1, 'duration': 10}), ('contain', {'volume': .3, 'distance': 2, 'tilt_degrees': 0}), ('support', {'span': .6, 'load': .2, 'support_count': 2})])
def test_family_specific_provider_payloads_remain_valid_sdk_decisions(family, context):
    value = {'experiment': {'family': family, 'subject_ids': ['actual-participant'], 'hypothesis': 'Test a useful supported function.', 'expected_success': True, 'context': context}, 'message': {'kind': 'reflection', 'text': 'Testing our existing arrangement.'}}
    assert AgentDecision.model_validate(value).experiment.family == family
    bad = deepcopy(value)
    bad['message'] = {'kind': 'support', 'text': 'I agree.'}
    with pytest.raises(ValidationError): AgentDecision.model_validate(bad)
    bad = deepcopy(value)
    bad['experiment']['context']['volume'] = 0
    with pytest.raises(ValidationError): AgentDecision.model_validate(bad)


@pytest.mark.asyncio
async def test_valid_longer_dialogue_survives_actual_planner_dispatch_unchanged(fixture):
    repo, colonies, provider, _, worker = fixture
    text = 'We can use the materials already in storage to build the tested support and help our crew move supplies. ' * 4
    assert 240 < len(text) < PUBLIC_TEXT_LIMIT
    async def propose(**kwargs):
        provider.calls.append(kwargs)
        return SimpleNamespace(output_text=json.dumps({'action': 'carry', 'reason': text, 'message': {'kind': 'reflection', 'text': text}}), model_dump=lambda **kw: {'usage': {'total_tokens': 400}, 'status': 'completed'})
    provider.aio.interactions.create = propose
    run = worker.request('longer-public-reason', 'winners')
    await worker.run(run['id'])
    assert repo._data['colonyReasoning'][run['id']]['status'] == 'completed'
    assert colonies.applied[run['id']]['decision']['reason'] == text
    assert colonies.applied[run['id']]['decision']['message']['text'] == text
    call = provider.calls[0]
    assert call['response_format']['schema'] == council_response_schema(['carry', 'build', 'rest'])
    payload = json.loads(call['input'])
    assert 'work_opportunities' in payload
    assert payload['work_opportunities']['funded_projects'] == []
    assert payload['work_opportunities']['tested_designs'] == []
    assert len(provider.calls) == 1
    with pytest.raises(ValidationError): AgentDecision.model_validate({'reason': 'x' * (PUBLIC_TEXT_LIMIT + 1), 'action': 'rest'})
