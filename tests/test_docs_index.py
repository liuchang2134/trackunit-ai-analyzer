"""The document index must stay true, and the archive must stay reversible.

The docs directory once held nine proposal versions and eleven release guides with
nothing saying which was current. `docs/INDEX.md` is that missing entry point, so
these tests keep it honest: every link resolves, nothing points into the archive,
and the archive script never claims a file the code reads by path.
"""
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / 'docs'
ARCHIVE = DOCS / 'archive'
INDEX = DOCS / 'INDEX.md'

LINK = re.compile(r'\]\(([^)]+)\)')


def index_links() -> list[str]:
    return [target for target in LINK.findall(INDEX.read_text(encoding='utf-8'))
            if not target.startswith(('http://', 'https://', '#'))]


def test_the_index_exists_and_names_the_authoritative_document():
    text = INDEX.read_text(encoding='utf-8')
    assert 'PROJECT_ACCEPTANCE_STATUS.md' in text, 'the index must point at the current status'
    assert '../README.md' in text, 'the index must point at how to run the project'


def test_every_index_link_resolves():
    missing = [target for target in index_links() if not (DOCS / target).exists()]
    assert missing == [], f'index links to files that do not exist: {missing}'


def test_the_index_does_not_link_into_the_archive():
    # Archived material describes superseded implementations; the current entry
    # point must not send a reader there.
    offenders = [target for target in index_links() if 'archive/' in target]
    assert offenders == [], f'index must not link archived documents: {offenders}'


def test_the_index_says_the_proposal_predates_the_current_provider():
    # The v9 proposal describes Gemini, which the project no longer uses. Saying so
    # is what stops a reviewer learning about an architecture that does not exist.
    text = INDEX.read_text(encoding='utf-8')
    assert 'Gemini' in text and 'DeepSeek' in text, \
        'the index must warn that the proposal names a provider the project no longer uses'
    assert '以 `PROJECT_ACCEPTANCE_STATUS.md` 为准' in text


def test_the_archive_script_never_moves_a_file_the_code_reads_by_path():
    # Moving these broke the release scripts and the v8/v9/v10 acceptance tests
    # once already; that must not be possible again.
    from scripts.archive_superseded_docs import KEPT_FOR_CODE, SUPERSEDED
    listed = {name for names in SUPERSEDED.values() for name in names}
    overlap = listed & set(KEPT_FOR_CODE)
    assert overlap == set(), f'these are read by path and must not be archived: {overlap}'


@pytest.mark.parametrize('name', [
    'RELEASE_GUIDE.md', 'RELEASE_V8_GUIDE.md', 'RELEASE_V8_NOTES.md',
    'RELEASE_V9_GUIDE.md', 'RELEASE_V9_NOTES.md',
    'RELEASE_V10_GUIDE.md', 'RELEASE_V10_NOTES.md',
])
def test_the_release_documents_the_scripts_read_are_still_in_place(name):
    assert (DOCS / name).is_file(), f'docs/{name} is read by the release scripts and must stay'


def test_the_archive_holds_only_superseded_material():
    if not ARCHIVE.is_dir():
        pytest.skip('nothing is archived')
    from scripts.archive_superseded_docs import SUPERSEDED
    listed = {name for names in SUPERSEDED.values() for name in names}
    stray = [path.name for path in ARCHIVE.iterdir() if path.is_file() and path.name not in listed]
    assert stray == [], f'archived files the script does not know about: {stray}'


def test_the_superseded_list_only_names_files_that_were_real():
    # A typo in the list would silently fail to archive anything.
    from scripts.archive_superseded_docs import SUPERSEDED
    for reason, names in SUPERSEDED.items():
        assert names, f'empty group: {reason}'
        for name in names:
            assert (DOCS / name).exists() or (ARCHIVE / name).exists(), \
                f'listed but present in neither place: {name}'
