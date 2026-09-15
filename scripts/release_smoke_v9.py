"""Run the v9 installed-app self-check in a fresh, uncredentialed extracted copy."""
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.release_smoke import run
from scripts.verify_release_v9 import verify_folder

if __name__ == '__main__':
    print(json.dumps(run(verifier=verify_folder), ensure_ascii=False, indent=2))
