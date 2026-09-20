"""Ignore this machine's evaluation products without ignoring anything the build reads.

`docs/evaluation/` accumulated far more local output than the repository needs to
carry: repeated runs of the same evaluation, dated acceptance notes, and package
checks for superseded versions. Committing them would add megabytes of duplicated
history, and leaving them untracked makes `git status` useless.

The risk in cleaning them up is that some of those files are *inputs*: build_release*,
verify_release*, historical_assets and the release tests read specific ones by exact
path. Those must stay visible to Git. So this script does not guess by pattern — it
reads the repository, finds which products are referenced by code, tests or documents,
and writes ignore rules for only the rest.

    .\\.tmp\\venv\\Scripts\\python.exe scripts/prune_evaluation_ignores.py --dry-run
    .\\.tmp\\venv\\Scripts\\python.exe scripts/prune_evaluation_ignores.py
"""
from __future__ import annotations

import argparse
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
EVALUATION = ROOT / 'docs/evaluation'
GITIGNORE = ROOT / '.gitignore'
MARKER = '# 本机评估产物（由 scripts/prune_evaluation_ignores.py 生成）'

# Where a reference to an evaluation file can appear. Anything found here keeps the file.
REFERENCE_SOURCES = (
    'tests/*.py', 'tests/*.cjs', 'scripts/*.py', 'scripts/*.mjs',
    'app/*.py', 'app/**/*.py', 'docs/*.md', 'README.md', 'extension/*.md',
)


def tracked_files() -> set[str]:
    result = subprocess.run(['git', 'ls-files', 'docs/evaluation'],
                            cwd=ROOT, capture_output=True, text=True)
    return {Path(line).name for line in result.stdout.splitlines() if line.strip()}


def untracked_products() -> list[Path]:
    tracked = tracked_files()
    return sorted((path for path in EVALUATION.glob('*')
                   if path.is_file() and path.name not in tracked), key=lambda p: p.name)


def referenced_names() -> set[str]:
    """Names of evaluation products that some code, test or document points at."""
    found: set[str] = set()
    for pattern in REFERENCE_SOURCES:
        for source in ROOT.glob(pattern):
            try:
                text = source.read_text(encoding='utf-8')
            except (OSError, UnicodeDecodeError):
                continue
            for product in untracked_products():
                if product.name in text:
                    found.add(product.name)
    return found


def ignore_lines(names: list[str]) -> list[str]:
    return [MARKER] + [f'docs/evaluation/{name}' for name in sorted(names)] + ['']


def apply(names: list[str], dry_run: bool) -> int:
    lines = ignore_lines(names)
    existing = GITIGNORE.read_text(encoding='utf-8')
    # Replace any previous block so re-running stays idempotent.
    if MARKER in existing:
        head = existing.split(MARKER)[0].rstrip('\n')
        existing = head + '\n'
    updated = existing.rstrip('\n') + '\n\n' + '\n'.join(lines)
    if dry_run:
        print(f'would add {len(names)} ignore rules:')
        for line in lines[1:1 + 12]:
            print('  ' + line)
        if len(names) > 12:
            print(f'  … 另有 {len(names) - 12} 条')
        return 0
    GITIGNORE.write_text(updated, encoding='utf-8')
    print(f'wrote {len(names)} ignore rules into .gitignore')
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args(argv)

    products = {path.name for path in untracked_products()}
    kept = referenced_names()
    prunable = sorted(products - kept)
    print(f'untracked products : {len(products)}')
    print(f'kept (referenced)  : {len(kept)}')
    print(f'ignored (unused)   : {len(prunable)}')
    if not prunable:
        print('nothing to ignore')
        return 0
    return apply(prunable, args.dry_run)


if __name__ == '__main__':
    raise SystemExit(main())
