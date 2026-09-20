"""Archive superseded documents so the current ones can be found.

The `docs/` root had accumulated nine proposal versions, seven presentation
decks, six scripts and eleven release guides, none of which said which one was
current. Worse, the v7/v9 series describe Gemini as the model provider, which the
project no longer uses — a reviewer reading them learns about an architecture that
does not exist.

This script moves superseded files into `docs/archive/` instead of deleting them:
nothing is lost, the current set becomes findable, and the move is reversible with
`--undo`. It only ever moves the files named in its own list.

    .\\.tmp\\venv\\Scripts\\python.exe scripts/archive_superseded_docs.py --dry-run
    .\\.tmp\\venv\\Scripts\\python.exe scripts/archive_superseded_docs.py
    .\\.tmp\\venv\\Scripts\\python.exe scripts/archive_superseded_docs.py --undo
"""
from __future__ import annotations

import argparse
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / 'docs'
ARCHIVE = DOCS / 'archive'

# Exact file names, grouped by why they are superseded. Only these are touched.
SUPERSEDED: dict[str, list[str]] = {
    '更早版本的参赛材料（保留了更晚的版本）': [
        '机联智检_完整参赛Proposal.md',
        '机联智检_完整参赛Proposal.docx',
        '机联智检_完整参赛Proposal.pdf',
        '机联智检_完整参赛Proposal_v6更新稿.md',
        '机联智检_完整参赛Proposal_v6更新稿.docx',
        '机联智检_完整参赛Proposal_v6更新稿.pdf',
        '机联智检_参赛Proposal_v7_Gemini版.md',
        '机联智检_参赛Proposal_v7_Gemini版.docx',
        '机联智检_参赛Proposal_v7_Gemini版.pdf',
        '参赛Proposal_机联智检_审阅稿.md',
        '机联智检_早期主动排查方案_存档.md',
    ],
    '更早版本的答辩材料（讲稿与演示稿）': [
        '机联智检_答辩讲稿.md',
        '机联智检_答辩讲稿_v6更新稿.md',
        '机联智检_答辩演示稿_v1.pdf',
        '机联智检_答辩演示稿_v1.pptx',
        '机联智检_答辩演示稿_v3.pdf',
        '机联智检_答辩演示稿_v3.pptx',
        '机联智检_答辩演示稿_v4.pdf',
        '机联智检_答辩演示稿_v4.pptx',
        '机联智检_答辩演示稿_v6更新稿.pdf',
        '机联智检_答辩演示稿_v6更新稿.pptx',
    ],
    '历史构建的发布说明（保留当前构建与脚本依赖的部分）': [
        'RELEASE_V4_NOTES.md',
        'RELEASE_V5_NOTES.md',
        'RELEASE_V6_NOTES.md',
        'RELEASE_V6_ERRATA.md',
        'DELIVERY_AUDIT.md',
        'DEMO_VIDEO.md',
    ],
    '一次性构建脚本（产物已生成）': [
        'build_full_proposal.py',
    ],
}

# These describe historical builds, but the release build and verification scripts
# read them by exact path, so moving them would silently change what those scripts
# do. They stay in place and are described as historical in docs/INDEX.md instead.
KEPT_FOR_CODE = (
    'RELEASE_GUIDE.md',
    'RELEASE_V8_GUIDE.md',
    'RELEASE_V8_NOTES.md',
    'RELEASE_V9_GUIDE.md',
    'RELEASE_V9_NOTES.md',
    'RELEASE_V10_GUIDE.md',
    'RELEASE_V10_NOTES.md',
)


def _plan() -> list[tuple[Path, Path, str]]:
    moves = []
    for reason, names in SUPERSEDED.items():
        for name in names:
            source = DOCS / name
            moves.append((source, ARCHIVE / name, reason))
    return moves


def archive(dry_run: bool) -> int:
    moves = _plan()
    missing = [str(source) for source, _, _ in moves if not source.is_file()]
    if not dry_run:
        ARCHIVE.mkdir(parents=True, exist_ok=True)
    moved = 0
    for source, target, reason in moves:
        if not source.is_file():
            continue
        if dry_run:
            print(f'would move  {source.name}   ({reason})')
        else:
            shutil.move(str(source), str(target))
            print(f'moved       {source.name}')
        moved += 1
    print(f'\n{"would move" if dry_run else "moved"}: {moved} files')
    if missing:
        print(f'already absent: {len(missing)}')
    return 0


def undo() -> int:
    if not ARCHIVE.is_dir():
        print('nothing to undo: docs/archive does not exist', file=sys.stderr)
        return 1
    restored = 0
    for source, target, _ in _plan():
        archived = ARCHIVE / source.name
        if archived.is_file() and not source.exists():
            shutil.move(str(archived), str(source))
            print(f'restored    {source.name}')
            restored += 1
    # Remove the archive directory only when it is empty afterwards.
    try:
        ARCHIVE.rmdir()
        print('removed empty docs/archive')
    except OSError:
        pass
    print(f'\nrestored: {restored} files')
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dry-run', action='store_true', help='list the moves without doing them')
    parser.add_argument('--undo', action='store_true', help='move the archived files back')
    args = parser.parse_args(argv)
    if args.undo:
        return undo()
    return archive(args.dry_run)


if __name__ == '__main__':
    raise SystemExit(main())
