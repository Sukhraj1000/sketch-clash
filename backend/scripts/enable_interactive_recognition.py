"""Enable the built-in fast camera profile for new battles, preserving pinned rounds."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from backend.app.config import Settings
from backend.app.repository import create_repository


def main():
    repository = create_repository(Settings.load())
    try:
        result = repository.enable_fast_live_pipeline()
        print(f"New battles use {result['active_version_id']} (revision {result['revision']}).")
        print('Existing battles, evaluation pause and provider request limits are unchanged.')
    finally:
        repository.close()


if __name__ == '__main__':
    main()
