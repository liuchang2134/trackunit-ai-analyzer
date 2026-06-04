import type { Machine } from "../types";

export type Language = "zh" | "en";

export function isMissing(value: unknown): boolean {
  return value === null || value === undefined || value === "" || value === "Data not available" || value === "Not available";
}

export function fieldLabel(field: string, language: Language): string {
  const labels: Record<string, { zh: string; en: string }> = {
    engine_status: { zh: "发动机状态", en: "Engine status" },
    fuel_remaining_percent: { zh: "油量数据", en: "Fuel remaining" },
    last_seen_at: { zh: "最后上线时间", en: "Last seen" },
    location: { zh: "位置信息", en: "Location" },
    operating_hours: { zh: "运行小时", en: "Operating hours" },
    idle_hours: { zh: "怠速小时", en: "Idle hours" },
  };
  return labels[field]?.[language] || field;
}

export function missingFieldReason(field: string, language: Language): string {
  const reasons: Record<string, { zh: string; en: string }> = {
    engine_status: {
      zh: "发动机状态缺失：会影响运行状态判断",
      en: "Engine status is missing: this affects running/stopped status analysis",
    },
    fuel_remaining_percent: {
      zh: "油量数据缺失：会影响低油量分析",
      en: "Fuel data is missing: this affects low-fuel analysis",
    },
    last_seen_at: {
      zh: "最后上线时间缺失：会影响离线判断",
      en: "Last seen time is missing: this affects offline analysis",
    },
    location: {
      zh: "位置信息缺失：会影响位置分析",
      en: "Location is missing: this affects location analysis",
    },
  };
  return reasons[field]?.[language] || `${fieldLabel(field, language)} ${language === "zh" ? "缺失" : "is missing"}`;
}

export function getMissingFields(machine: Machine): string[] {
  const fields: string[] = [];
  if (isMissing(machine.engine_status)) fields.push("engine_status");
  if (isMissing(machine.fuel_remaining_percent)) fields.push("fuel_remaining_percent");
  if (isMissing(machine.last_seen_at)) fields.push("last_seen_at");
  if (isMissing(machine.location)) fields.push("location");
  return fields;
}

export function riskScore(machine: Machine): number {
  let score = 0;
  if (isOffline(machine)) score += 40;
  if ((machine.fault_count ?? 0) >= 2) score += 35;
  else if ((machine.fault_count ?? 0) > 0) score += 18;
  if (isLowFuel(machine)) score += 20;
  if (isLowUtilization(machine)) score += 15;
  if (getMissingFields(machine).length > 0) score += 5;
  return Math.min(score, 100);
}

export function riskLevel(machine: Machine, language: Language): string {
  const score = riskScore(machine);
  if (score >= 70) return language === "zh" ? "高风险" : "Critical";
  if (score >= 35) return language === "zh" ? "中风险" : "Warning";
  if (score > 0) return language === "zh" ? "关注" : "Watch";
  return language === "zh" ? "正常" : "Normal";
}

export function riskTone(machine: Machine): "good" | "warning" | "danger" | "info" {
  const score = riskScore(machine);
  if (score >= 70) return "danger";
  if (score >= 35) return "warning";
  if (score > 0) return "info";
  return "good";
}

export function riskReasons(machine: Machine, language: Language): string[] {
  const reasons: string[] = [];
  if (isOffline(machine)) reasons.push(language === "zh" ? "超过 72 小时未通讯" : "No communication for over 72 hours");
  if ((machine.fault_count ?? 0) >= 2) reasons.push(language === "zh" ? "存在重复故障" : "Repeated faults");
  else if ((machine.fault_count ?? 0) > 0) reasons.push(language === "zh" ? "存在故障记录" : "Fault records exist");
  if (isLowFuel(machine)) reasons.push(language === "zh" ? "油量低于或等于 10%" : "Fuel is at or below 10%");
  if (isLowUtilization(machine)) reasons.push(language === "zh" ? "设备利用率偏低" : "Low utilization");
  if (getMissingFields(machine).length > 0) reasons.push(language === "zh" ? "关键数据不完整" : "Key data is incomplete");
  return reasons.length ? reasons : [language === "zh" ? "未触发主要风险规则" : "No major risk rules triggered"];
}

export function recommendedAction(machine: Machine, language: Language): string {
  if (isOffline(machine)) return language === "zh" ? "检查终端供电、网络连接和现场设备状态。" : "Check telematics power, connectivity, and site status.";
  if ((machine.fault_count ?? 0) >= 2) return language === "zh" ? "优先创建服务跟进，核查活动故障和维修记录。" : "Create service follow-up and review active faults and service history.";
  if (isLowFuel(machine)) return language === "zh" ? "联系客户或现场团队确认补油计划。" : "Confirm refueling plan with customer or site team.";
  if (isLowUtilization(machine)) return language === "zh" ? "核查租赁状态、客户使用率和调度计划。" : "Review rental status, customer usage, and dispatch plan.";
  return language === "zh" ? "保持监控，按计划维护。" : "Keep monitoring and follow scheduled maintenance.";
}

export function isLowFuel(machine: Machine): boolean {
  return machine.fuel_remaining_percent !== null && machine.fuel_remaining_percent !== undefined && machine.fuel_remaining_percent <= 10;
}

export function isLowUtilization(machine: Machine): boolean {
  return machine.risk_level === "Low Utilization" || (machine.operating_hours !== null && machine.operating_hours !== undefined && machine.operating_hours < 50);
}

export function isOffline(machine: Machine): boolean {
  const timestamp = Date.parse(machine.last_seen_at);
  if (Number.isNaN(timestamp)) return false;
  return Date.now() - timestamp > 72 * 60 * 60 * 1000;
}

export function formatMissing(value: unknown, language: Language): string {
  return isMissing(value) ? (language === "zh" ? "数据缺失" : "Missing") : String(value);
}
