"""Run real local-model smoke cases; structural checks are not diagnostic accuracy."""
from datetime import datetime, timezone
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import time
import uuid
import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app import local_datasets, parts_catalog, local_assistant
from app.local_assistant import investigate, InvestigationRequest
from app.ollama_client import OllamaError, get_ollama_model
from scripts.prepare_parts_demo import build_demo


def run(selected_cases: list[str] | None = None, language: str = 'zh') -> dict:
    if language not in {'zh','en'}: raise ValueError('Unsupported evaluation language')
    # Isolated paths in this process; no changes to the running backend's catalog.
    workspace = ROOT / ".tmp" / ("evaluation-" + uuid.uuid4().hex)
    workspace.mkdir(parents=True)
    local_datasets.DATASETS = workspace / "datasets"
    parts_catalog.CATALOG_PATH = workspace / "parts.json"
    catalog = parts_catalog.CatalogImport.model_validate_json((ROOT / "docs/examples/demo-parts-catalog.json").read_text(encoding="utf-8"))
    output = {"generated_at": datetime.now(timezone.utc).isoformat(), "model": get_ollama_model(), "language": language,
        "scope": "Selected synthetic workflow smoke cases, one run each; not real-machine accuracy or a latency benchmark",
        "code_hashes": {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in (
            "app/local_assistant.py", "app/report_facts.py", "app/summary_time_validation.py", "app/feedback_validation.py", "app/parts_catalog.py", "app/telemetry_evidence.py", "app/check_options.py", "app/fault_evidence.py")}, "cases": []}
    # Read only artifact metadata, not environment/secrets or raw account data.
    try:
        tags=httpx.get('http://127.0.0.1:11434/api/tags',timeout=10).json().get('models',[])
        output['model_artifact']=next(({k:m.get(k) for k in ('name','digest','size','details')} for m in tags if m.get('name')==get_ollama_model()),None)
    except (httpx.HTTPError,ValueError):
        output['model_artifact']=None
    cases = [("matching_catalog", "parts"), ("wrong_model", "parts"), ("empty_catalog", "parts"), ("one_sample", "trends")]
    if selected_cases and 'comprehensive' in selected_cases:
        cases.append(('comprehensive','comprehensive'))
    for name, task in cases:
        if selected_cases and name not in selected_cases:
            continue
        dataset = build_demo()
        if name == "wrong_model": dataset.machine.model = "DEMO-OTHER-MODEL"
        if name == "one_sample":
            dataset.telemetry = [dataset.telemetry[-1]]
            dataset.faults = []
        active_catalog = parts_catalog.CatalogImport(parts=[]) if name == "empty_catalog" else catalog
        parts_catalog.CATALOG_PATH.write_text(active_catalog.model_dump_json(), encoding="utf-8")
        saved = local_datasets.save_dataset(dataset)
        request = InvestigationRequest(machine_id=dataset.machine.machine_id, dataset_id=saved["dataset_id"], task=task, language=language,
            question=("综合检查这个模拟片段，说明事件间隔、备件匹配依据和对应资料中的检查步骤。" if task=='comprehensive' else
                "读取故障并检索备件，说明匹配依据和需要核查的事项。" if task == "parts" else "分析工时增量和怠速占比；资料不足时明确说明。"))
        if language == 'en':
            request.question = ('Review this simulated episode, explaining event intervals, parts applicability and source-supported checks.' if task == 'comprehensive' else
                'Read fault records and find applicable parts. Explain matching evidence and remaining uncertainty.' if task == 'parts' else
                'Analyze operating-hour increments and idle share. Explain precisely when the evidence is insufficient.')
        case = {"name": name, "input": dataset.model_dump(mode="json"), "catalog": active_catalog.model_dump(),
                "request": request.model_dump(), "checks": {}, "structural_pass": False}
        start = time.perf_counter()
        case['model_decisions'] = []
        original_step = local_assistant.model_step
        def traced_step(messages, allowed):
            decision = original_step(messages, allowed)
            case['model_decisions'].append({'allowed_actions': allowed,
                'control': messages[-1]['content'],
                'previous_message': messages[-2]['content'],
                'decision': decision.model_dump()})
            return decision
        local_assistant.model_step = traced_step
        try:
            report = investigate(request)
            case["report"] = report
            actual = {t["action"] for t in report["tool_trace"]}
            case["checks"]["required_queries_executed"] = set(report["required_queries"]) <= actual
            case["checks"]["all_citations_exist"] = all(c in report["evidence"] for c in report["citations"])
            source_checks = report.get('check_recommendations', [])
            case['checks']['has_supported_checks'] = bool(source_checks)
            case['checks']['check_sources_exist'] = all(c['evidence_ids'] and set(c['evidence_ids']) <= set(report['evidence']) for c in source_checks)
            case['checks']['check_text_is_source_selected'] = report['next_checks'] == [c['text'] for c in source_checks]
            candidates = {p["part_number"] for p in report["parts_candidates"]}
            if task in {"parts", "comprehensive"}:
                case["checks"]["expected_catalog_candidates"] = candidates == ({"DEMO-BOOST-SENSOR"} if name in {"matching_catalog", "comprehensive"} else set())
                event_facts=next(v for v in report['evidence'].values() if v.get('method')=='fault_record_facts_v1')
                case['checks']['event_interval_25_minutes']=event_facts['groups'][0]['first_to_last_minutes']==25
                if name in {'matching_catalog','comprehensive'}:
                    case['checks']['selected_matched_catalog_procedure']=any(c['check_id'].startswith('check:catalog:') for c in source_checks)
            else:
                trend = next(v for v in report["evidence"].values() if v.get("method") == "time_window_rules_v1")
                case["checks"]["no_invented_counter_results"] = trend["operating_hours_delta"] is None and trend["idle_share"] is None
            case["structural_pass"] = all(case["checks"].values())
        except OllamaError as exc:
            case["error"] = str(exc)
        finally:
            local_assistant.model_step = original_step
        case["elapsed_seconds"] = round(time.perf_counter() - start, 2)
        output["cases"].append(case)
        print(name + ": " + ("structural checks passed" if case["structural_pass"] else "FAILED"), flush=True)
    return output


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--case', action='append', choices=['matching_catalog','wrong_model','empty_catalog','one_sample','comprehensive'])
    parser.add_argument('--model',help='Local Ollama model override for this evaluation process only')
    parser.add_argument('--language',choices=['zh','en'],default='zh')
    args=parser.parse_args()
    if args.model: os.environ['OLLAMA_MODEL']=args.model
    result = run(args.case,args.language)
    target = ROOT / "docs/evaluation"
    target.mkdir(exist_ok=True)
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = target / ("local-assistant-" + run_id + ".json")
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = ["# 本地 AI 工作流实测", "", "模型：" + result["model"], "", f"本次 {len(result['cases'])} 个人工模拟案例，每例运行一次。下列结果只验证工具执行、引用存在性和目录适用性，不是故障诊断准确率。", "",
             "|案例|结构检查|本次耗时 秒|", "|---|---|---|"]
    lines += [f"|{c['name']}|{'通过' if c['structural_pass'] else '失败'}|{c['elapsed_seconds']}|" for c in result["cases"]]
    lines += ["", "耗时包含本次模型加载或推理波动，不能作为性能基准。完整 JSON 保留输入、目录、代码哈希、请求和原始输出，便于复核。", "",
              "自然语言结论的正确性、资料缺失时的措辞和现场适用性需要逐例审查；结构检查通过不表示这些要求全部满足。"]
    path.with_suffix(".md").write_text("\n".join(lines)+"\n", encoding="utf-8")
    print("Saved " + path.name)
