"""Render already-computed evidence as bilingual facts, independently of AI prose."""
from app.telemetry_evidence import timestamp


def build_report_facts(source: str, replay_at: str | None, evidence: dict, language: str = 'zh') -> list[dict]:
    facts = []
    def add(key, zh, en, refs):
        facts.append({'fact_id': key, 'text': en if language == 'en' else zh,
                      'evidence_ids': refs, 'method': 'evidence_render_v1'})
    snapshot = next(((ref, item) for ref, item in evidence.items() if ref.endswith(':snapshot')), None)
    refs = [snapshot[0]] if snapshot else []
    if source in {'mock', 'imported_synthetic'}:
        add('source', '本报告使用模拟数据；结论仅适用于该片段，不代表实机状态。',
            'This report uses simulated data; conclusions apply only to this segment, not a physical machine.', refs)
    else:
        add('source', f'数据来源：{source}。仅说明已载入记录，不保证数据完整或代表设备当前状态。',
            f'Data source: {source}. Loaded records do not establish completeness or current machine state.', refs)
    if snapshot:
        item = snapshot[1]
        times = [timestamp(row.get('recorded_at')) for row in item.get('telemetry', [])]
        valid = [value for value in times if value is not None]
        latest = max(valid).isoformat() if valid else None
        cutoff = timestamp(replay_at)
        if cutoff:
            add('replay-time', f'分析截止时刻：{cutoff.isoformat()}。这不是采样时刻。',
                f'Analysis cutoff: {cutoff.isoformat()}. This is not a sample timestamp.', refs)
        if latest:
            add('sample-time', f'快照展示记录中最新有效采样时刻：{latest}。',
                f'Latest valid timestamp among displayed snapshot records: {latest}.', refs)
    for ref, item in evidence.items():
        if ref == 'operator:manual-fault':
            row = item['definition']
            add('manual-fault',
                f'人工填报故障码 {item["code"]}（未经 Trackunit 事件验证）。TV12U / {item["version"]} 原表定义：{row["description"]}。提醒方式：{row["reminder_description"]}，不是风险等级。来源：{item["source"]["file_name"]}，{row["source_sheet"]} 第 {row["source_row"]} 行。代码定义不等于确认零件损坏。',
                f'Operator-reported code {item["code"]} (not verified through Trackunit events). TV12U / {item["version"]} original definition: {row["description"]}. Original reminder: {row["reminder_description"]}; this is not a severity rating. Source: {item["source"]["file_name"]}, {row["source_sheet"]}, row {row["source_row"]}. A definition does not confirm component damage.',
                [ref])
        if item.get('method') == 'cooling_warning_v1':
            prediction=item['prediction']; score=prediction.get('score')
            temperatures=item.get('latest_observations',[])
            temperature=temperatures[-1].get('coolant_c') if temperatures else None
            status={'warning':'提前预警','watch':'尚未连续触发','below_threshold':'未触发预警',
                    'unknown':'数据不足或不合要求','stopped':'停机不预测','current_high':'当前观测已达到实验温度阈值'}.get(prediction['status'],prediction['status'])
            score_text=format(score,'.3f') if score is not None else '—'
            add('cooling-warning',
                f'模拟冷却预警：{status}；当前冷却液温度 {temperature if temperature is not None else "未知"}°C；模型得分 {score_text}，阈值 {item["alarm_threshold"]}。预测窗口 {item["horizon_minutes"]} 分钟。得分不是故障概率，实验事件不等于零件损坏；未经实机验证。',
                f'Synthetic cooling warning: {prediction["status"]}; observed coolant {temperature if temperature is not None else "unknown"}C; model score {score_text}, threshold {item["alarm_threshold"]}, horizon {item["horizon_minutes"]} minutes. Scores are not failure probabilities; the experimental thermal event does not establish component damage. No field validation.', [ref])
        if ref == 'operator:feedback':
            outcomes = {
                'observed': ('观察到该现象', 'Observed'),
                'not_observed': ('未观察到该现象', 'Not observed'),
                'inconclusive': ('无法判断', 'Inconclusive'),
            }
            for record in item.get('records', []):
                zh_result, en_result = outcomes.get(record.get('outcome'), ('未注明结果', 'Outcome unspecified'))
                observed_at = record.get('observed_at', '')
                notes = record.get('notes', '')
                add('operator-feedback:' + record['feedback_id'],
                    f'人工检查反馈（未经验证），观察时间：{observed_at}；填报结果：{zh_result}。原文：{notes}\n未观察到现象不能排除故障，观察到现象也不确认根因；检查范围以原文为准。',
                    f'Operator inspection feedback (unverified), observation time: {observed_at}; reported outcome: {en_result}. Original text (not translated): {notes}\nNot observing a symptom does not exclude a fault; observing one does not confirm a root cause. Inspection scope is as described in the original text.',
                    [ref])
        if item.get('method') == 'time_window_rules_v1':
            hours, idle = item.get('operating_hours_delta'), item.get('idle_share')
            samples = item.get('valid_counter_sample_counts', {})
            if hours is None or idle is None:
                add('trend-availability',
                    f'窗口工时增量：{hours if hours is not None else "不可计算"}；怠速占比：{format(idle * 100, ".2f") + "%" if idle is not None else "不可计算"}。有效工时/怠速时间戳数：{samples.get("operating", "未知")}/{samples.get("idle", "未知")}。缺失指标不按零处理，详细原因见趋势证据。',
                    f'Window operating increment: {hours if hours is not None else "unavailable"}; idle share: {format(idle * 100, ".2f") + "%" if idle is not None else "unavailable"}. Valid operating/idle timestamp counts: {samples.get("operating", "unknown")}/{samples.get("idle", "unknown")}. Missing metrics are not zero; see trend evidence for reasons.', [ref])
            else:
                add('trend-values', f'有效区间工时增量 {hours} 小时；对应怠速占比 {idle * 100:.2f}%。仅汇总通过核验的区间，不代表设备健康或完整窗口总量。',
                    f'Accepted-interval operating increment: {hours} h; corresponding idle share: {idle * 100:.2f}%. Accepted intervals alone do not establish health or complete-window totals.', [ref])
        if 'search_diagnostics' in item:
            reason = item['search_diagnostics'].get('reason_code')
            messages = {
                'catalog_empty': ('本地备件目录为空，没有可支持的候选。', 'The local parts catalog is empty; no supported candidates are available.'),
                'no_eligible_catalog': ('本地只有演示目录，已为当前真实数据排除。', 'Only demonstration catalog entries exist and were excluded for this real-data source.'),
                'model_not_in_catalog': ('目录中没有精确匹配此整机型号的可用条目。', 'No eligible catalog entry matches this exact equipment model.'),
                'serial_not_applicable': ('目录有此整机型号，但序列号不在适用清单内。', 'Entries match the equipment model, but the serial number is outside their applicability lists.'),
                'fault_or_component_not_matched': ('条目通过机型及序列号限制筛选，但未匹配故障码或部件查询。', 'Entries passed model and serial-scope filters but did not match the fault codes or component query.'),
                'matched': ('找到待检查候选；机型指整机适用型号，不是零件型号。序列号范围及整机配置仍需核实。', 'Inspection candidates were found. Model lists describe applicable equipment, not part model numbers. Serial applicability and machine configuration still require verification.'),
            }
            if reason in messages:
                zh, en = messages[reason]
                add('parts-result', zh + ' 检索仅覆盖本地目录，不构成更换或采购结论。',
                    en + ' Search covers this local catalog only; it is not a replacement or purchasing decision.', [ref])
    return facts
