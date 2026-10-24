from copy import deepcopy
from io import BytesIO
from types import SimpleNamespace

import pytest
from PIL import Image

from app.config import Settings
from app.engine import PRESETS
from app.recognition import RecognitionService, identity_support


def jpeg(colour='white', size=(160, 120)):
    buf = BytesIO()
    Image.new('RGB', size, colour).save(buf, 'JPEG')
    return buf.getvalue()


def test_unknown_detector_class_is_distinct_from_missing_recognition_evidence():
    detector = {'status': 'empty', 'supported_labels': ['cup', 'bottle', 'book']}
    microphone = identity_support(detector, [], {'canonical_key': 'microphone', 'aliases': []})
    assert microphone['class_coverage'] == 'not_in_detector_vocabulary'
    assert 'no microphone class' in microphone['detail']
    mug = identity_support(detector, [], {'canonical_key': 'mug', 'aliases': ['coffee mug']})
    assert mug['class_coverage'] == 'supported'
    assert mug['status'] == 'no_detection'


def proposal(**updates):
    return {'status': 'recognized', 'proposed_label': 'mug', 'canonical_type_candidate': 'coffee mug',
            'visible_features': ['rounded white body', 'loop handle'], 'uncertainty': [], 'display_name': 'Mugsy',
            'archetype': 'Guard', 'stats': deepcopy(PRESETS['Guard']),
            'visual_spec': {'template_id': 'mug', 'palette': ['#F5EDDC'], 'scale': 1,
                            'proportions': {'width': 1, 'height': 1}, 'accessories': ['eyes', 'feet'],
                            'animation_style': 'wobbly', 'schema_version': '1', 'appearance_seed': 1}, **updates}


class FakeEvidence:
    def __init__(self, detections=None):
        self.detections = detections or []
        self.ocr_images = []
        self.detector_images = []

    async def detect(self, data):
        self.detector_images.append(data)
        return {'status': 'completed' if self.detections else 'empty', 'detections': self.detections}

    async def read_text(self, data):
        self.ocr_images.append(data)
        return {'status': 'empty', 'text': []}

    def close(self): pass


class FakeClient:
    def __init__(self, proposals):
        self.proposals = list(proposals)
        self.calls = []
        self.aio = SimpleNamespace(interactions=SimpleNamespace(create=self.create))

    async def create(self, **kwargs):
        self.calls.append(deepcopy(kwargs))
        value = self.proposals.pop(0)
        return SimpleNamespace(steps=[{'type': 'thought', 'signature': 'opaque-signature'},
                                     {'type': 'function_call', 'id': f'call-{len(self.calls)}',
                                      'name': 'prepare_fighter', 'arguments': value}])


async def recognize(service, **kwargs):
    return await service.recognize_capture(jpeg(), battle_id='battle-1', player_slot=0,
        capture_id='capture-1', image_hash='a'*64, image_ref='/api/media/'+'a'*64,
        width=160, height=120, source='upload', **kwargs)


@pytest.mark.asyncio
async def test_no_detector_text_evidence_does_not_block_valid_unfamiliar_photo():
    client = FakeClient([proposal()])
    service = RecognitionService(Settings(), client=client, evidence_runner=FakeEvidence())
    observation = await recognize(service)
    assert observation.status == 'recognized'
    assert observation.pending_fighter.canonical_type_id == 'mug'
    assert observation.evidence['detector']['status'] == 'empty'
    assert observation.evidence['identity_support']['status'] == 'no_detection'
    assert observation.evidence['identity_support']['identity_verified'] is False
    assert observation.evidence['ocr']['status'] == 'empty'
    assert [v['tool'] for v in observation.pending_fighter.validation] == [
        'resolve_character_type', 'validate_fighter_config', 'validate_visual_spec', 'simulate_match_preview']
    assert client.calls[0]['store'] is False
    assert client.calls[0]['generation_config'] == {'thinking_level': 'medium', 'max_output_tokens': 4096}
    assert client.calls[0]['input'][0]['content'][1]['type'] == 'image'


@pytest.mark.asyncio
async def test_actual_validation_failure_returns_to_model_and_can_be_repaired():
    bad = proposal(stats={**PRESETS['Guard'], 'attack': 999})
    client = FakeClient([bad, proposal()])
    observation = await recognize(RecognitionService(Settings(), client=client, evidence_runner=FakeEvidence()))
    assert observation.status == 'recognized'
    assert len(client.calls) == 2
    history = client.calls[1]['input']
    assert any(s.get('signature') == 'opaque-signature' for s in history)
    feedback = next(s for s in history if s['type'] == 'function_result')
    assert 'validate_fighter_config' in feedback['result'][0]['text']
    assert 'false' in feedback['result'][0]['text']
    assert observation.evidence['gemini']['repair_attempts'] == 1


@pytest.mark.asyncio
async def test_invalid_executable_visual_spec_exhausts_two_repairs_without_fighter():
    bad = proposal()
    bad['visual_spec']['javascript'] = 'steal()'
    client = FakeClient([bad, bad, bad])
    observation = await recognize(RecognitionService(Settings(), client=client, evidence_runner=FakeEvidence()))
    assert observation.status == 'needs_recapture'
    assert observation.pending_fighter is None
    assert len(client.calls) == 3
    assert any(t['tool'] == 'validate_visual_spec' and not t['valid'] for t in observation.evidence['tools'])


@pytest.mark.asyncio
async def test_multiple_objects_require_selection_without_api_call():
    boxes = [{'id': 'a', 'label': 'cup', 'score': .8, 'box': {'x': 0, 'y': 0, 'width': 60, 'height': 80}},
             {'id': 'b', 'label': 'bottle', 'score': .9, 'box': {'x': 90, 'y': 0, 'width': 60, 'height': 80}}]
    local = FakeEvidence(boxes)
    client = FakeClient([])
    observation = await recognize(RecognitionService(Settings(), client=client, evidence_runner=local))
    assert observation.status == 'needs_selection'
    assert len(observation.candidates) == 2
    assert client.calls == []
    assert local.ocr_images == []


@pytest.mark.asyncio
async def test_selected_crop_is_the_only_ocr_region_and_seed_is_stable():
    local = FakeEvidence()
    client = FakeClient([proposal(), proposal()])
    service = RecognitionService(Settings(), client=client, evidence_runner=local)
    crop = {'x': 20, 'y': 10, 'width': 40, 'height': 60}
    first = await recognize(service, crop=crop)
    second = await recognize(service, crop=crop)
    assert Image.open(BytesIO(local.ocr_images[0])).size == (40, 60)
    assert Image.open(BytesIO(local.detector_images[0])).size == (40, 60)
    import json
    payload = json.loads(client.calls[0]['input'][0]['content'][0]['text'])
    assert payload['detector_evidence']['coordinate_space'] == 'selected_region'
    assert payload['detector_evidence']['dimensions'] == {'width': 40, 'height': 60}
    assert first.pending_fighter.visual_spec.appearance_seed == second.pending_fighter.visual_spec.appearance_seed


@pytest.mark.asyncio
@pytest.mark.parametrize('label,expected', [('cup', 'compatible_label'), ('bottle', 'different_labels')])
async def test_detector_support_never_asserts_identity_or_hides_disagreement(label, expected):
    boxes = [{'id': 'target', 'label': label, 'score': .91,
              'box': {'x': 0, 'y': 0, 'width': 80, 'height': 90}}]
    observed = await recognize(RecognitionService(Settings(), client=FakeClient([proposal()]), evidence_runner=FakeEvidence(boxes)))
    assert observed.status == 'recognized'
    assert observed.pending_fighter.canonical_type_id == 'mug'
    assert observed.evidence['identity_support']['status'] == expected
    assert observed.evidence['identity_support']['identity_verified'] is False
    assert bool(observed.uncertainty) == (expected == 'different_labels')


@pytest.mark.asyncio
async def test_crop_detections_are_returned_in_original_photo_coordinates():
    boxes = [{'id': 'target', 'label': 'cup', 'score': .91,
              'box': {'x': 2, 'y': 3, 'width': 30, 'height': 40}}]
    crop = {'x': 20, 'y': 10, 'width': 40, 'height': 60}
    observed = await recognize(RecognitionService(Settings(), client=FakeClient([proposal()]), evidence_runner=FakeEvidence(boxes)), crop=crop)
    assert observed.candidates[0].box.model_dump() == {'x': 22, 'y': 13, 'width': 30, 'height': 40}
    assert observed.evidence['detector']['detections'][0]['box']['x'] == 2


@pytest.mark.asyncio
async def test_uncertainty_and_unavailable_api_never_fabricate_fighter():
    client = FakeClient([proposal(status='needs_recapture', uncertainty=['The subject is blurred.'])])
    uncertain = await recognize(RecognitionService(Settings(), client=client, evidence_runner=FakeEvidence()))
    assert uncertain.status == 'needs_recapture' and uncertain.pending_fighter is None
    missing = await recognize(RecognitionService(Settings(gemini_api_key=''), evidence_runner=FakeEvidence()))
    assert missing.evidence['gemini']['status'] == 'unavailable'
    assert missing.pending_fighter is None


@pytest.mark.asyncio
@pytest.mark.parametrize('status', [None, 500, 502, 503, 504])
async def test_standalone_uncertain_transport_never_repeats_paid_request(status):
    class ProviderError(Exception):
        status_code = status
    calls = []
    async def uncertain(**kwargs):
        calls.append(kwargs)
        raise TimeoutError() if status is None else ProviderError()
    client = SimpleNamespace(aio=SimpleNamespace(interactions=SimpleNamespace(create=uncertain)))
    service = RecognitionService(Settings(transport_retries=1), client=client, evidence_runner=FakeEvidence())
    with pytest.raises((TimeoutError, ProviderError)):
        await service._request([])
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_semantic_candidates_are_reviewed_without_merging_identity_or_consuming_repair_budget():
    from app.catalog import CharacterCatalog
    class Related:
        async def search(self, description):
            return {'status': 'completed', 'candidates': [{'canonical_type_id': 'mug', 'template_id': 'mug', 'score': .83}]}
    first = proposal(proposed_label='watering can', canonical_type_candidate='watering can')
    first['visual_spec']['template_id'] = 'generic'
    reviewed = deepcopy(first)
    reviewed['visual_spec']['template_id'] = 'mug'
    client = FakeClient([first, reviewed])
    service = RecognitionService(Settings(), client=client, evidence_runner=FakeEvidence(),
                                 catalog=CharacterCatalog(retriever=Related()))
    observed = await recognize(service)
    assert observed.status == 'recognized'
    assert observed.pending_fighter.canonical_type_id == 'watering-can'
    assert observed.pending_fighter.visual_spec.template_id == 'mug'
    assert observed.evidence['gemini']['repair_attempts'] == 0
    assert observed.evidence['gemini']['retrieval_reviewed'] is True
    feedback = next(step for step in client.calls[1]['input'] if step['type'] == 'function_result')
    assert 'related_candidates' in feedback['result'][0]['text']
    assert 'Similarity alone is not identity' in feedback['result'][0]['text']
