# 机联智检 / Local investigation

设备: SIM-PARTS-REPLAY-001
来源: imported_synthetic
时间: 2026-09-14T05:59:27.466548+00:00
模型: qwen3:8b

故障代码 ENG-BOOST-102-3 与演示增压压力传感器 DEMO-BOOST-SENSOR 匹配，但需核实故障是否仍活跃，并检查线束、接头与传感器测量结果。当前数据为模拟回放，结论仅适用于该片段。

## Next checks
- 核对故障码、事件时间、状态及数据来源；不能把重复记录直接当作多次独立故障。
- 先核实故障是否仍活跃，再根据对应维修手册检查线束、接头与传感器测量结果。
- 核对模拟数据的回放时点与记录时间；结论仅适用于该演示片段。

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
  "summary": "故障代码 ENG-BOOST-102-3 与演示增压压力传感器 DEMO-BOOST-SENSOR 匹配，但需核实故障是否仍活跃，并检查线束、接头与传感器测量结果。当前数据为模拟回放，结论仅适用于该片段。",
  "next_checks": [
    "核对故障码、事件时间、状态及数据来源；不能把重复记录直接当作多次独立故障。",
    "先核实故障是否仍活跃，再根据对应维修手册检查线束、接头与传感器测量结果。",
    "核对模拟数据的回放时点与记录时间；结论仅适用于该演示片段。"
  ],
  "check_recommendations": [
    {
      "check_id": "check:faults",
      "text": "核对故障码、事件时间、状态及数据来源；不能把重复记录直接当作多次独立故障。",
      "evidence_ids": [
        "tool:1:faults"
      ],
      "provenance": "application_rule",
      "source_document": "机联智检数据核验规则 v1",
      "limitation": "资料与适用性需核实；不是制造商认证的维修结论。"
    },
    {
      "check_id": "check:catalog:bb9e40ad600c8a25",
      "text": "先核实故障是否仍活跃，再根据对应维修手册检查线束、接头与传感器测量结果。",
      "evidence_ids": [
        "catalog:DEMO-BOOST-SENSOR"
      ],
      "provenance": "demo",
      "source_document": "机联智检人工编写演示目录，不是制造商资料 / 演示条目1 / demo-v1",
      "limitation": "资料与适用性需核实；不是制造商认证的维修结论。"
    },
    {
      "check_id": "check:snapshot",
      "text": "核对模拟数据的回放时点与记录时间；结论仅适用于该演示片段。",
      "evidence_ids": [
        "tool:3:snapshot"
      ],
      "provenance": "application_rule",
      "source_document": "机联智检数据核验规则 v1",
      "limitation": "资料与适用性需核实；不是制造商认证的维修结论。"
    }
  ],
  "check_selection_method": "model_selected_source_text_v1",
  "citations": [
    "tool:1:faults",
    "tool:2:parts",
    "tool:3:snapshot"
  ],
  "evidence": {
    "tool:1:faults": {
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
    "tool:2:parts": {
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
      "action": "faults",
      "source_id": "tool:1:faults"
    },
    {
      "action": "parts",
      "source_id": "tool:2:parts"
    },
    {
      "action": "snapshot",
      "source_id": "tool:3:snapshot"
    }
  ],
  "generated_at": "2026-09-14T05:59:27.466548+00:00",
  "task": "parts",
  "required_queries": [
    "faults",
    "parts",
    "snapshot"
  ],
  "prior_record_id": null,
  "limitations": [
    "AI hypotheses require inspection; no remaining-life estimate.",
    "Catalog applicability is user supplied and is not manufacturer certification."
  ],
  "record_id": "08967f53d94ecd35cea46c2a97bfa831ffc26ff7a02b5cc197b8350409682e2e",
  "history_saved": true
}
```
