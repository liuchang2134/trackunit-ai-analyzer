"""Read-only Trackunit history sync command."""
import argparse
from datetime import datetime
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from app.history_sync import fetch_history, persist_sync_result
from app.trackunit_client import TrackunitClient, TrackunitError

if __name__ == "__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot-file", type=Path, required=True)
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    args=parser.parse_args()
    try:
        result=fetch_history(json.loads(args.snapshot_file.read_text(encoding="utf-8")),
            datetime.fromisoformat(args.start.replace("Z","+00:00")), datetime.fromisoformat(args.end.replace("Z","+00:00")),
            TrackunitClient(retries=0), ROOT/"data/local/sync-state")
        output=persist_sync_result(result)
        print(json.dumps(output,ensure_ascii=False))
    except (ValueError, OSError, TrackunitError):
        raise SystemExit("Sync failed: verify snapshot/schema/date window and the local cooldown; no raw provider error was printed") from None
