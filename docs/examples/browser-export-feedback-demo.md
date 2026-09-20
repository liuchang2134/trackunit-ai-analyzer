# 机联智检 / Local investigation

设备: SIM-PARTS-REPLAY-001
来源: imported_synthetic
时间: 2026-09-14T06:54:46.791074+00:00
模型: qwen3:8b

## 数据事实 / Data facts
- 本报告使用模拟数据；结论仅适用于该片段，不代表实机状态。 [tool:3:snapshot]
- 分析截止时刻：2026-06-29T08:55:00+00:00。这不是采样时刻。 [tool:3:snapshot]
- 快照展示记录中最新有效采样时刻：2026-06-29T08:45:00+00:00。 [tool:3:snapshot]
- 人工检查反馈（未经验证），观察时间：2026-06-29T08:50:00Z；填报结果：未观察到该现象。原文：模拟检查记录：目视未发现接头松脱；尚未测量压力信号，无法确认传感器是否损坏。仅用于功能演示，不是真实现场检查。
未观察到现象不能排除故障，观察到现象也不确认根因；检查范围以原文为准。 [operator:feedback]
- 有效区间工时增量 1.7333 小时；对应怠速占比 30.45%。仅汇总通过核验的区间，不代表设备健康或完整窗口总量。 [tool:1:trends]
- 找到待检查候选；机型指整机适用型号，不是零件型号。序列号范围及整机配置仍需核实。 检索仅覆盖本地目录，不构成更换或采购结论。 [tool:4:parts]

## AI解释（待核实） / AI interpretation (requires review)
当前支持的判断：增压压力信号异常（ENG-BOOST-102-3）重复记录，需核实故障是否仍活跃。缺少的证据：未测量压力信号，无法确认传感器是否损坏；未检查线束和接头。建议：根据维修手册检查相关部件，并测量传感器信号以确认故障根源。

## Next checks
- 先核实故障是否仍活跃，再根据对应维修手册检查线束、接头与传感器测量结果。

## Evidence & parts
```json
{
  "status": "completed",
  "provider": "ollama_local",
  "model": "qwen3:8b",
  "machine_id": "SIM-PARTS-REPLAY-001",
  "source": "imported_synthetic",
  "dataset_id": "926fa6c37d60fd358f94bb9697a53f3ba5be20820b413cbab14af3656896a147",
  "source_document": "人工编写的告警流程演示；工时沿用模拟片段；不代表真实故障或制造商诊断规则",
  "replay_at": "2026-06-29T08:55:00+00:00",
  "summary": "当前支持的判断：增压压力信号异常（ENG-BOOST-102-3）重复记录，需核实故障是否仍活跃。缺少的证据：未测量压力信号，无法确认传感器是否损坏；未检查线束和接头。建议：根据维修手册检查相关部件，并测量传感器信号以确认故障根源。",
  "summary_status": "ai_interpretation_requires_review",
  "data_facts": [
    {
      "fact_id": "source",
      "text": "本报告使用模拟数据；结论仅适用于该片段，不代表实机状态。",
      "evidence_ids": [
        "tool:3:snapshot"
      ],
      "method": "evidence_render_v1"
    },
    {
      "fact_id": "replay-time",
      "text": "分析截止时刻：2026-06-29T08:55:00+00:00。这不是采样时刻。",
      "evidence_ids": [
        "tool:3:snapshot"
      ],
      "method": "evidence_render_v1"
    },
    {
      "fact_id": "sample-time",
      "text": "快照展示记录中最新有效采样时刻：2026-06-29T08:45:00+00:00。",
      "evidence_ids": [
        "tool:3:snapshot"
      ],
      "method": "evidence_render_v1"
    },
    {
      "fact_id": "operator-feedback:0dd48388bc52f8d201608d171eef58ab4db5d7ab3cdb54a9c04810a9b2d5e6dc",
      "text": "人工检查反馈（未经验证），观察时间：2026-06-29T08:50:00Z；填报结果：未观察到该现象。原文：模拟检查记录：目视未发现接头松脱；尚未测量压力信号，无法确认传感器是否损坏。仅用于功能演示，不是真实现场检查。\n未观察到现象不能排除故障，观察到现象也不确认根因；检查范围以原文为准。",
      "evidence_ids": [
        "operator:feedback"
      ],
      "method": "evidence_render_v1"
    },
    {
      "fact_id": "trend-values",
      "text": "有效区间工时增量 1.7333 小时；对应怠速占比 30.45%。仅汇总通过核验的区间，不代表设备健康或完整窗口总量。",
      "evidence_ids": [
        "tool:1:trends"
      ],
      "method": "evidence_render_v1"
    },
    {
      "fact_id": "parts-result",
      "text": "找到待检查候选；机型指整机适用型号，不是零件型号。序列号范围及整机配置仍需核实。 检索仅覆盖本地目录，不构成更换或采购结论。",
      "evidence_ids": [
        "tool:4:parts"
      ],
      "method": "evidence_render_v1"
    }
  ],
  "language": "zh",
  "next_checks": [
    "先核实故障是否仍活跃，再根据对应维修手册检查线束、接头与传感器测量结果。"
  ],
  "check_recommendations": [
    {
      "check_id": "check:catalog:bb9e40ad600c8a25",
      "text": "先核实故障是否仍活跃，再根据对应维修手册检查线束、接头与传感器测量结果。",
      "evidence_ids": [
        "catalog:DEMO-BOOST-SENSOR"
      ],
      "provenance": "demo",
      "source_document": "机联智检人工编写演示目录，不是制造商资料 / 演示条目1 / demo-v1",
      "limitation": "资料与适用性需核实；不是制造商认证的维修结论。"
    }
  ],
  "check_selection_method": "model_selected_source_text_v1",
  "citations": [
    "operator:feedback",
    "tool:1:trends",
    "tool:2:faults",
    "tool:3:snapshot",
    "catalog:DEMO-BOOST-SENSOR"
  ],
  "evidence": {
    "operator:feedback": {
      "parent_record_id": "34d055644d64526b9cae820a5066cfde1bc62eede734758b08803196bfec2ef2",
      "total_records": 1,
      "included_latest_limit": 5,
      "records": [
        {
          "feedback_id": "0dd48388bc52f8d201608d171eef58ab4db5d7ab3cdb54a9c04810a9b2d5e6dc",
          "check_id": "check:catalog:bb9e40ad600c8a25",
          "check_text": "先核实故障是否仍活跃，再根据对应维修手册检查线束、接头与传感器测量结果。",
          "created_at": "2026-09-14T06:42:41.681522+00:00",
          "machine_id": "SIM-PARTS-REPLAY-001",
          "notes": "模拟检查记录：目视未发现接头松脱；尚未测量压力信号，无法确认传感器是否损坏。仅用于功能演示，不是真实现场检查。",
          "observed_at": "2026-06-29T08:50:00Z",
          "outcome": "not_observed",
          "record_id": "34d055644d64526b9cae820a5066cfde1bc62eede734758b08803196bfec2ef2",
          "source": "unverified_operator_feedback"
        }
      ],
      "source": "unverified_operator_feedback"
    },
    "tool:1:trends": {
      "method": "time_window_rules_v1",
      "as_of": "2026-06-29T08:55:00+00:00",
      "sample_count": 105,
      "completeness": "not_verified",
      "fault_coverage": "unknown",
      "window_duration_hours": 1.7333,
      "excluded_samples": {
        "duplicate": 9
      },
      "window_start": "2026-06-29T07:01:00+00:00",
      "window_end": "2026-06-29T08:45:00+00:00",
      "valid_intervals": 104,
      "excluded_intervals": 0,
      "operating_hours_delta": 1.7333,
      "idle_hours_delta": 0.5278,
      "paired_idle_intervals": 104,
      "idle_counter_coverage": "all_valid_operating_intervals",
      "valid_counter_sample_counts": {
        "operating": 105,
        "idle": 105
      },
      "metric_unavailable_reasons": {
        "operating_hours_delta": [],
        "idle_hours_delta": [],
        "idle_share": []
      },
      "operating_counter_window_start": "2026-06-29T07:01:00+00:00",
      "operating_counter_window_end": "2026-06-29T08:45:00+00:00",
      "idle_share": 0.3045,
      "latest_age_hours": 0.17,
      "findings": [
        {
          "code": "repeated_unresolved_events",
          "kind": "inspection_priority",
          "evidence": {
            "fault_code": "ENG-BOOST-102-3",
            "unique_events_7d": 2
          },
          "meaning": "Repeated records warrant inspection; verify whether the source repeats one persistent fault."
        }
      ],
      "findings_total": 1,
      "limitations": [
        "No remaining-life or calibrated failure probability is estimated.",
        "Only supplied records are assessed; absent findings do not prove health.",
        "Counter deltas assume aligned sample timestamps and cumulative engine-running/idle counters.",
        "Idle share requires at least 0.5 valid operating hours and aligned idle counters across every accepted operating interval. Operating increments are sums of valid intervals, not proof of full-window coverage."
      ],
      "source": "imported_synthetic"
    },
    "tool:2:faults": {
      "method": "fault_record_facts_v1",
      "as_of": "2026-06-29T08:55:00+00:00",
      "total_loaded_events": 2,
      "valid_loaded_records": 2,
      "excluded_records": {},
      "displayed_events_limit": 20,
      "events": [
        {
          "machine_id": "SIM-PARTS-REPLAY-001",
          "trackunit_asset_id": null,
          "equipment_id": null,
          "spn": null,
          "fmi": null,
          "fault_code": "ENG-BOOST-102-3",
          "description": "人工演示告警：增压压力信号异常。可能涉及线路、接头或传感器；尚未确认根因。",
          "severity": "medium",
          "occurred_at": "2026-06-29T08:20:00+00:00",
          "status": "open"
        },
        {
          "machine_id": "SIM-PARTS-REPLAY-001",
          "trackunit_asset_id": null,
          "equipment_id": null,
          "spn": null,
          "fmi": null,
          "fault_code": "ENG-BOOST-102-3",
          "description": "人工演示告警：增压压力信号异常。可能涉及线路、接头或传感器；尚未确认根因。",
          "severity": "medium",
          "occurred_at": "2026-06-29T08:45:00+00:00",
          "status": "open"
        }
      ],
      "groups": [
        {
          "fault_code": "ENG-BOOST-102-3",
          "unique_code_timestamp_records": 2,
          "first_record_at": "2026-06-29T08:20:00+00:00",
          "last_record_at": "2026-06-29T08:45:00+00:00",
          "first_to_last_minutes": 25,
          "consecutive_gaps_minutes": [
            25
          ],
          "conflicting_status_timestamps": 0,
          "unresolved_code_timestamp_records": 2,
          "independent_failure_count": null
        }
      ],
      "total_fault_code_groups": 1,
      "limitation": "Only supplied records before cutoff. Code/time uniqueness does not prove separate failures; time span is not a recurrence period. Fault codes are not part numbers or component IDs. Empty events do not prove health.",
      "source": "imported_synthetic"
    },
    "tool:3:snapshot": {
      "machine": {
        "machine_id": "SIM-PARTS-REPLAY-001",
        "trackunit_asset_id": null,
        "equipment_id": null,
        "serial_number": "SIM-PARTS-REPLAY-001",
        "model": "XE135U",
        "machine_type": "excavator",
        "customer": "SYNTHETIC DEMO",
        "location": "Synthetic site",
        "latitude": null,
        "longitude": null,
        "last_seen_at": "2026-06-29T08:45:00+00:00"
      },
      "total_telemetry_records": 114,
      "displayed_latest_records_limit": 8,
      "telemetry": [
        {
          "machine_id": "SIM-PARTS-REPLAY-001",
          "trackunit_asset_id": null,
          "equipment_id": null,
          "operating_hours": 4858.2791,
          "idle_hours": 608.7748,
          "fuel_remaining_percent": 69.4,
          "engine_status": "running",
          "latitude": null,
          "longitude": null,
          "recorded_at": "2026-06-29T08:45:00+00:00"
        },
        {
          "machine_id": "SIM-PARTS-REPLAY-001",
          "trackunit_asset_id": null,
          "equipment_id": null,
          "operating_hours": 4858.2791,
          "idle_hours": 608.7748,
          "fuel_remaining_percent": 69.4,
          "engine_status": "running",
          "latitude": null,
          "longitude": null,
          "recorded_at": "2026-06-29T08:45:00+00:00"
        },
        {
          "machine_id": "SIM-PARTS-REPLAY-001",
          "trackunit_asset_id": null,
          "equipment_id": null,
          "operating_hours": 4858.2791,
          "idle_hours": 608.7748,
          "fuel_remaining_percent": 69.4,
          "engine_status": "running",
          "latitude": null,
          "longitude": null,
          "recorded_at": "2026-06-29T08:45:00+00:00"
        },
        {
          "machine_id": "SIM-PARTS-REPLAY-001",
          "trackunit_asset_id": null,
          "equipment_id": null,
          "operating_hours": 4858.2791,
          "idle_hours": 608.7748,
          "fuel_remaining_percent": 69.4,
          "engine_status": "running",
          "latitude": null,
          "longitude": null,
          "recorded_at": "2026-06-29T08:45:00+00:00"
        },
        {
          "machine_id": "SIM-PARTS-REPLAY-001",
          "trackunit_asset_id": null,
          "equipment_id": null,
          "operating_hours": 4858.2791,
          "idle_hours": 608.7748,
          "fuel_remaining_percent": 69.4,
          "engine_status": "running",
          "latitude": null,
          "longitude": null,
          "recorded_at": "2026-06-29T08:45:00+00:00"
        },
        {
          "machine_id": "SIM-PARTS-REPLAY-001",
          "trackunit_asset_id": null,
          "equipment_id": null,
          "operating_hours": 4858.2791,
          "idle_hours": 608.7748,
          "fuel_remaining_percent": 69.4,
          "engine_status": "running",
          "latitude": null,
          "longitude": null,
          "recorded_at": "2026-06-29T08:45:00+00:00"
        },
        {
          "machine_id": "SIM-PARTS-REPLAY-001",
          "trackunit_asset_id": null,
          "equipment_id": null,
          "operating_hours": 4858.2791,
          "idle_hours": 608.7748,
          "fuel_remaining_percent": 69.4,
          "engine_status": "running",
          "latitude": null,
          "longitude": null,
          "recorded_at": "2026-06-29T08:45:00+00:00"
        },
        {
          "machine_id": "SIM-PARTS-REPLAY-001",
          "trackunit_asset_id": null,
          "equipment_id": null,
          "operating_hours": 4858.2791,
          "idle_hours": 608.7748,
          "fuel_remaining_percent": 69.4,
          "engine_status": "running",
          "latitude": null,
          "longitude": null,
          "recorded_at": "2026-06-29T08:45:00+00:00"
        }
      ],
      "source": "imported_synthetic",
      "replay_at": "2026-06-29T08:55:00+00:00",
      "source_document": "人工编写的告警流程演示；工时沿用模拟片段；不代表真实故障或制造商诊断规则",
      "limitation": "May be stale or incomplete; inspect recorded_at and last_seen_at."
    },
    "catalog:DEMO-BOOST-SENSOR": {
      "part_number": "DEMO-BOOST-SENSOR",
      "name": "演示增压压力传感器（非采购零件号）",
      "component": "boost pressure sensor",
      "models": [
        "XE135U"
      ],
      "serial_numbers": [],
      "applicability": "model_only",
      "fault_codes": [
        "ENG-BOOST-102-3"
      ],
      "checks": [
        "先核实故障是否仍活跃，再根据对应维修手册检查线束、接头与传感器测量结果。"
      ],
      "source_document": "机联智检人工编写演示目录，不是制造商资料",
      "source_page": "演示条目1",
      "revision": "demo-v1",
      "provenance": "demo",
      "status": "candidate_requires_inspection",
      "match_reason": "fault_code",
      "serial_verified": false,
      "source_id": "catalog:DEMO-BOOST-SENSOR",
      "limitation": "Verify machine configuration and inspection results before ordering."
    },
    "tool:4:parts": {
      "candidates": [
        {
          "part_number": "DEMO-BOOST-SENSOR",
          "name": "演示增压压力传感器（非采购零件号）",
          "component": "boost pressure sensor",
          "models": [
            "XE135U"
          ],
          "serial_numbers": [],
          "applicability": "model_only",
          "fault_codes": [
            "ENG-BOOST-102-3"
          ],
          "checks": [
            "先核实故障是否仍活跃，再根据对应维修手册检查线束、接头与传感器测量结果。"
          ],
          "source_document": "机联智检人工编写演示目录，不是制造商资料",
          "source_page": "演示条目1",
          "revision": "demo-v1",
          "provenance": "demo",
          "status": "candidate_requires_inspection",
          "match_reason": "fault_code",
          "serial_verified": false,
          "source_id": "catalog:DEMO-BOOST-SENSOR",
          "limitation": "Verify machine configuration and inspection results before ordering."
        }
      ],
      "search_diagnostics": {
        "method": "catalog_filter_stages_v1",
        "counts": {
          "catalog_entries": 1,
          "eligible_provenance": 1,
          "matching_model": 1,
          "matching_serial_scope": 1,
          "matching_query": 1
        },
        "reason_code": "matched",
        "explanation": "Applicable candidates found; inspection and configuration verification remain required.",
        "returned_count": 1,
        "truncated": false,
        "limitation": "Stage counts are sequential filters of this local catalog only; no match does not prove parts do not exist elsewhere."
      },
      "limitation": "No match means no supported recommendation. Do not invent a part."
    }
  },
  "parts_candidates": [
    {
      "part_number": "DEMO-BOOST-SENSOR",
      "name": "演示增压压力传感器（非采购零件号）",
      "component": "boost pressure sensor",
      "models": [
        "XE135U"
      ],
      "serial_numbers": [],
      "applicability": "model_only",
      "fault_codes": [
        "ENG-BOOST-102-3"
      ],
      "checks": [
        "先核实故障是否仍活跃，再根据对应维修手册检查线束、接头与传感器测量结果。"
      ],
      "source_document": "机联智检人工编写演示目录，不是制造商资料",
      "source_page": "演示条目1",
      "revision": "demo-v1",
      "provenance": "demo",
      "status": "candidate_requires_inspection",
      "match_reason": "fault_code",
      "serial_verified": false,
      "source_id": "catalog:DEMO-BOOST-SENSOR",
      "limitation": "Verify machine configuration and inspection results before ordering."
    }
  ],
  "tool_trace": [
    {
      "action": "trends",
      "source_id": "tool:1:trends"
    },
    {
      "action": "faults",
      "source_id": "tool:2:faults"
    },
    {
      "action": "snapshot",
      "source_id": "tool:3:snapshot"
    },
    {
      "action": "parts",
      "source_id": "tool:4:parts"
    }
  ],
  "generated_at": "2026-09-14T06:54:46.791074+00:00",
  "task": "parts",
  "required_queries": [
    "faults",
    "parts",
    "snapshot"
  ],
  "prior_record_id": "34d055644d64526b9cae820a5066cfde1bc62eede734758b08803196bfec2ef2",
  "limitations": [
    "AI hypotheses require inspection; no remaining-life estimate.",
    "Catalog applicability is user supplied and is not manufacturer certification."
  ],
  "record_id": "48d291bfea0d21e8b4ebd9223f913c09aae5431a0d58722aacb00dac22c5c994",
  "history_saved": true
}
```
