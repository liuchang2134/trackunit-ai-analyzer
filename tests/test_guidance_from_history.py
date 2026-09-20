"""A report opened from the history must feed the sidebar's guidance.

The sidebar asks the workbench for the AI's search terms whenever the engineer wants
to mark the official catalog. That request was answered only from the live run, so a
report opened from 诊断记录 produced no terms at all — the panel then told the
engineer to run the analysis first, while the finished report was on screen. Marking
the catalog is this project's central action, so that gap removed the AI's value from
the most ordinary way of reaching a report.

These tests pin the contract across the two files, because the bug lived in the seam
between them: the history opener never published the report it was displaying.
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / 'app/assistant_ui/app.js').read_text(encoding='utf-8')


def test_the_guidance_source_falls_back_to_an_opened_report():
    body = APP[APP.index('function currentAISearchGuidance'):]
    body = body[:body.index('\n}')]
    assert 'const source=report||openedReport;' in body, \
        'guidance must read the opened report when there is no live one'
    assert 'source?.component_hypotheses' in body, 'hypotheses must come from that source'


def test_opening_a_saved_report_publishes_it_for_guidance():
    # The history path renders through its own code; it has to publish the report it
    # shows, otherwise the guidance source stays empty.
    assert re.search(r'const saved=full\.report;\s*openedReport=saved;', APP), \
        'the history opener must publish the report it displays'


def test_clearing_the_workspace_also_clears_the_opened_report():
    # Otherwise a stale report would keep answering the sidebar after the workspace
    # was reset, and the terms would describe a machine no longer on screen.
    assert re.search(r'function clearReport\(\)\s*\{\s*report=null;\s*openedReport=null;', APP), \
        'clearReport must clear the opened report too'


def test_the_reported_flags_describe_the_report_the_terms_came_from():
    body = APP[APP.index('function currentAISearchGuidance'):]
    body = body[:body.index('\n}')]
    assert 'has_report:Boolean(source)' in body, \
        'has_report must be true when the terms came from an opened report'
    assert 'has_search_terms:terms.length>0' in body, \
        'the panel needs to tell "no report" apart from "report without search terms"'
    assert 'has_report:Boolean(report)' not in body, \
        'has_report must not keep looking only at the live run'


def test_the_opened_report_is_kept_apart_from_the_live_run():
    # Overwriting `report` would silently move the flow track, the export and the
    # feedback panel onto a historical snapshot.
    assert re.search(r'let report = null, openedReport = null,', APP), \
        'the opened report needs its own holder'


def test_the_panel_still_asks_before_marking():
    panel = (ROOT / 'extension/panel.js').read_text(encoding='utf-8')
    # The fix is only useful if the panel requests guidance when it has none.
    assert "if (!aiGuidance.terms.length) await requestAIGuidance();" in panel
    assert "jilian:ai-guidance-request" in panel
    assert 'has_report' in panel, 'the panel decides what to say from this flag'
