import asyncio
import threading
from pathlib import Path
import pytest

from app.evidence import EvidenceConfig, EvidenceRunner, prominent_detections


@pytest.mark.asyncio
async def test_disabled_and_missing_weights_are_truthful(tmp_path):
    runner = EvidenceRunner(EvidenceConfig(model_dir=tmp_path, yolo_enabled=False, ocr_enabled=False))
    assert (await runner.detect(b''))['status'] == 'skipped'
    assert (await runner.read_text(b''))['status'] == 'skipped'
    runner.close()
    runner = EvidenceRunner(EvidenceConfig(model_dir=tmp_path))
    found = await runner.detect(b'')
    assert found['status'] == 'unavailable'
    assert found['detections'] == []
    runner.close()


@pytest.mark.asyncio
async def test_timeout_does_not_allow_unbounded_background_jobs():
    runner = EvidenceRunner(EvidenceConfig(timeout_seconds=.02))
    release = threading.Event()
    def work():
        release.wait(2)
        return {'status': 'completed'}
    try:
        timed = await runner._run(work)
        assert timed['status'] == 'failed'
        busy = await runner._run(work)
        assert busy['status'] == 'unavailable'
    finally:
        release.set()
        runner.close()


def test_prominence_uses_canonical_box_area_and_suppresses_duplicate_boxes():
    boxes = [{'id': 'first', 'box': {'x': 0, 'y': 0, 'width': 70, 'height': 80}},
             {'id': 'duplicate', 'box': {'x': 1, 'y': 1, 'width': 68, 'height': 78}},
             {'id': 'small', 'box': {'x': 80, 'y': 80, 'width': 2, 'height': 2}}]
    assert [b['id'] for b in prominent_detections(boxes, 100, 100)] == ['first']
