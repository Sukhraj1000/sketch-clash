"""Explicit one-time download of public official detector/OCR weights."""
from pathlib import Path
import sys
import os
from urllib.request import urlopen
from shutil import copyfileobj

ROOT = Path(__file__).resolve().parents[1]
MODEL_DIR = ROOT / 'models'

def main():
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    target = MODEL_DIR / 'yolo11n.pt'
    if not target.is_file():
        temporary = target.with_suffix('.download')
        try:
            with urlopen('https://github.com/ultralytics/assets/releases/download/v8.3.0/yolo11n.pt', timeout=60) as response, temporary.open('wb') as output:
                copyfileobj(response, output)
            temporary.replace(target)
        finally:
            temporary.unlink(missing_ok=True)
    os.environ["YOLO_AUTOINSTALL"] = "False"
    from ultralytics import YOLO
    YOLO(str(target), task='detect')
    import easyocr
    easyocr.Reader(['en'], gpu=False, model_storage_directory=str(MODEL_DIR/'easyocr'),
                   user_network_directory=str(MODEL_DIR/'easyocr-user'), download_enabled=True, verbose=False)
    print('YOLO11n and EasyOCR English weights are ready locally. Restart the backend after setup.')

if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print(f'Vision setup failed ({type(exc).__name__}). Check network access to the official Ultralytics/EasyOCR releases.', file=sys.stderr)
        raise SystemExit(1)
