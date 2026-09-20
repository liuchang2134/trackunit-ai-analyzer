"""Reproduce the AI reference-grounding figures from this machine's records.

The numbers quoted about the AI (how many references it made, whether they all
resolve, how many decisions it took) used to be produced by hand, which means
nobody else could check them. This script recomputes them from the saved
investigations and writes both a JSON and a Markdown report, so a reviewer can run
it and compare.

Read-only: it scans `data/local/investigations` and calls no model.

    .\\.tmp\\venv\\Scripts\\python.exe scripts/evaluate_ai_grounding.py
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.ai_grounding_report import build_report, render_markdown  # noqa: E402

DEFAULT_RECORDS = ROOT / 'data/local/investigations'
DEFAULT_TARGET = ROOT / 'docs/evaluation'

# Which code produced these figures, so a later reader can tell whether the
# measurement still applies to the version they are looking at.
HASHED_FILES = (
    'app/ai_contribution.py',
    'app/citation_audit.py',
    'app/ai_grounding_report.py',
    'app/local_assistant.py',
    'app/investigation_history.py',
)


def code_hashes() -> dict:
    hashes = {}
    for name in HASHED_FILES:
        path = ROOT / name
        try:
            hashes[name] = hashlib.sha256(path.read_bytes()).hexdigest()
        except OSError:
            hashes[name] = None
    return hashes


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--records', type=Path, default=DEFAULT_RECORDS,
                        help='directory holding saved investigations')
    parser.add_argument('--target', type=Path, default=DEFAULT_TARGET,
                        help='directory for the report files')
    parser.add_argument('--no-write', action='store_true', help='print only, write nothing')
    args = parser.parse_args(argv)

    if not args.records.is_dir():
        print(f'No such records directory: {args.records}', file=sys.stderr)
        return 1
    data = build_report(args.records)
    data['generated_at'] = datetime.now(timezone.utc).isoformat()
    data['records_directory'] = str(args.records)
    data['code_hashes'] = code_hashes()

    totals = data['totals']
    print(f"records scanned      : {totals['records_total']} "
          f"(with model: {totals['records_with_model']}, without: {totals['records_without_model']})")
    print(f"references checked   : {totals['checked']}  resolved: {totals['resolved']}  "
          f"dangling: {totals['dangling']}")
    print(f"model decisions      : {totals['model_decisions']}  "
          f"hypotheses: {totals['hypotheses']}  checks: {totals['checks']}")
    print('NOTE: this measures whether citations resolve, not diagnostic accuracy.')

    if args.no_write:
        return 0
    args.target.mkdir(parents=True, exist_ok=True)
    run_id = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    json_path = args.target / f'ai-grounding-{run_id}.json'
    md_path = args.target / f'ai-grounding-{run_id}.md'
    json_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    md_path.write_text(render_markdown(data), encoding='utf-8')
    print('Saved ' + json_path.name)
    print('Saved ' + md_path.name)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
