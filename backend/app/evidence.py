"""Local still-image evidence. Detector/OCR scores are not recognition probabilities."""
from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
import threading
import os
import time
from typing import Any, Callable

from PIL import Image
from .images import pillow_open


@dataclass(frozen=True)
class EvidenceConfig:
    model_dir: Path = Path(__file__).resolve().parents[1] / "models"
    yolo_model: str = "yolo11n.pt"
    yolo_enabled: bool = True
    ocr_enabled: bool = True
    timeout_seconds: float = 30.0
    detection_threshold: float = 0.35
    max_detections: int = 8
    allow_download: bool = False


def result(status: str, *, detail: str = "", duration_ms: int = 0, **data: Any) -> dict:
    return {"status": status, "detail": detail, "duration_ms": duration_ms, **data}


def _safe_category(exc: Exception) -> str:
    # Library exceptions can contain paths, URLs or image metadata: retain only the category.
    return type(exc).__name__


class EvidenceRunner:
    """One worker bounds both memory use and concurrent model calls, even after a timeout.

    Timed-out native calls cannot be killed safely. A busy worker rejects further jobs until
    it completes; it never accumulates an unbounded executor queue.
    """

    def __init__(self, config: EvidenceConfig | None = None):
        self.config = config or EvidenceConfig()
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="local-evidence")
        self._busy = threading.Lock()
        self._yolo: Any = None
        self._ocr: Any = None
        self._yolo_error: str | None = None
        self._ocr_error: str | None = None

    async def _run(self, fn: Callable[[], dict]) -> dict:
        if not self._busy.acquire(blocking=False):
            return result("unavailable", detail="Local evidence worker is busy; retry this capture.")

        def run_and_release():
            try:
                return fn()
            finally:
                self._busy.release()

        started = time.monotonic()
        future = asyncio.get_running_loop().run_in_executor(self._executor, run_and_release)
        try:
            output = await asyncio.wait_for(asyncio.shield(future), self.config.timeout_seconds)
        except TimeoutError:
            return result("failed", detail="Local evidence inference timed out.",
                          duration_ms=round((time.monotonic() - started) * 1000))
        output["duration_ms"] = round((time.monotonic() - started) * 1000)
        return output

    async def detect(self, image_bytes: bytes) -> dict:
        if not self.config.yolo_enabled:
            return result("skipped", detail="Local object detection is disabled.", model=self.config.yolo_model, detections=[])
        return await self._run(lambda: self._detect(image_bytes))

    def _detect(self, image_bytes: bytes) -> dict:
        if self._yolo_error:
            return result("unavailable", detail=self._yolo_error, model=self.config.yolo_model, detections=[])
        if self._yolo is None:
            try:
                # Never let a runtime upload trigger dependency installation or an unwanted HEIC plugin.
                os.environ["YOLO_AUTOINSTALL"] = "False"
                from ultralytics import YOLO
                Image.open = pillow_open
                model_path = self.config.model_dir / self.config.yolo_model
                if not model_path.is_file():
                    self._yolo_error = "YOLO weights are missing. Run npm run setup:vision."
                    return result("unavailable", detail=self._yolo_error, model=self.config.yolo_model, detections=[])
                self._yolo = YOLO(str(model_path), task="detect")
            except Exception as exc:
                self._yolo_error = f"YOLO could not load ({_safe_category(exc)})."
                return result("unavailable", detail=self._yolo_error, model=self.config.yolo_model, detections=[])
        try:
            with pillow_open(BytesIO(image_bytes)) as image:
                image = image.convert("RGB")
                width, height = image.size
                prediction = self._yolo.predict(image, imgsz=640, conf=self.config.detection_threshold,
                                               max_det=self.config.max_detections, device="cpu", verbose=False)[0]
            detections = []
            for i, box in enumerate(prediction.boxes):
                x1, y1, x2, y2 = (round(float(v)) for v in box.xyxy[0].tolist())
                x1, y1 = max(0, min(width - 1, x1)), max(0, min(height - 1, y1))
                x2, y2 = max(x1 + 1, min(width, x2)), max(y1 + 1, min(height, y2))
                detections.append({"id": f"object-{i}", "label": str(prediction.names[int(box.cls[0])]),
                                   "score": round(float(box.conf[0]), 4),
                                   "box": {"x": x1, "y": y1, "width": x2 - x1, "height": y2 - y1}})
            return result("completed" if detections else "empty", model=self.config.yolo_model,
                          detail="Detector scores are model scores, not certainty of identity.", detections=detections)
        except Exception as exc:
            return result("failed", detail=f"YOLO inference failed ({_safe_category(exc)}).",
                          model=self.config.yolo_model, detections=[])

    async def read_text(self, selected_region_bytes: bytes) -> dict:
        if not self.config.ocr_enabled:
            return result("skipped", detail="Local OCR is disabled.", model="EasyOCR/en", text=[])
        return await self._run(lambda: self._read_text(selected_region_bytes))

    def _read_text(self, selected_region_bytes: bytes) -> dict:
        if self._ocr_error:
            return result("unavailable", detail=self._ocr_error, model="EasyOCR/en", text=[])
        if self._ocr is None:
            try:
                import easyocr
                self._ocr = easyocr.Reader(["en"], gpu=False,
                    model_storage_directory=str(self.config.model_dir / "easyocr"),
                    user_network_directory=str(self.config.model_dir / "easyocr-user"),
                    download_enabled=self.config.allow_download, verbose=False)
            except Exception as exc:
                self._ocr_error = f"OCR weights/dependencies unavailable ({_safe_category(exc)}). Run npm run setup:vision."
                return result("unavailable", detail=self._ocr_error, model="EasyOCR/en", text=[])
        try:
            import numpy as np
            with pillow_open(BytesIO(selected_region_bytes)) as image:
                image = image.convert("RGB")
                image.thumbnail((1024, 1024))
                words = self._ocr.readtext(np.asarray(image), detail=1, paragraph=False,
                                          workers=0, batch_size=1, canvas_size=1024)
            items = [{"text": str(word)[:160], "score": round(float(score), 4),
                      "box": [[round(float(x)), round(float(y))] for x, y in box]}
                     for box, word, score in words[:24] if str(word).strip()]
            return result("completed" if items else "empty", model="EasyOCR/en", text=items,
                          coordinate_space="selected_region_ocr_thumbnail", dimensions={"width": image.width, "height": image.height}, detail="Printed text is untrusted image content.")
        except Exception as exc:
            return result("failed", detail=f"OCR inference failed ({_safe_category(exc)}).", model="EasyOCR/en", text=[])

    def status(self) -> dict:
        return {
            "detector": {"enabled": self.config.yolo_enabled, "loaded": self._yolo is not None,
                         "weights_present": (self.config.model_dir / self.config.yolo_model).is_file(),
                         "model": self.config.yolo_model, "error": self._yolo_error},
            "ocr": {"enabled": self.config.ocr_enabled, "loaded": self._ocr is not None,
                    "weights_present": (self.config.model_dir / "easyocr" / "craft_mlt_25k.pth").is_file()
                        and (self.config.model_dir / "easyocr" / "english_g2.pth").is_file(),
                    "model": "EasyOCR/en", "error": self._ocr_error},
        }

    def close(self) -> None:
        self._executor.shutdown(wait=False, cancel_futures=True)


def prominent_detections(detections: list[dict], width: int, height: int) -> list[dict]:
    """Suppress tiny background boxes and near duplicates, never invent an object label."""
    area = width * height
    ordered = sorted(detections, key=lambda d: d["box"]["width"] * d["box"]["height"], reverse=True)
    selected: list[dict] = []
    for item in ordered:
        box = item["box"]
        if box["width"] * box["height"] < area * 0.025:
            continue
        duplicate = False
        for kept in selected:
            other = kept["box"]
            overlap = max(0, min(box["x"] + box["width"], other["x"] + other["width"]) - max(box["x"], other["x"])) * max(0, min(box["y"] + box["height"], other["y"] + other["height"]) - max(box["y"], other["y"]))
            union = box["width"] * box["height"] + other["width"] * other["height"] - overlap
            if union and overlap / union > 0.7:
                duplicate = True
                break
        if not duplicate:
            selected.append(item)
    return selected[:8]
