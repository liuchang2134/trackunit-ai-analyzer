import { useMemo, useState } from "react";
import type { Machine } from "../types";
import StatusBadge from "./StatusBadge";
import { isLowFuel, isLowUtilization, isOffline, recommendedAction, riskLevel, riskReasons, riskScore, riskTone } from "../utils/display";

type Props = {
  machines: Machine[];
  language: "zh" | "en";
  selectedMachineId?: string | null;
  onSelectMachine?: (machine: Machine) => void;
};

type SortKey = "last_seen_at" | "operating_hours" | "fuel_remaining_percent" | "fault_count";
type FleetFilter = "all" | "offline" | "highRisk" | "lowFuel" | "lowUtilization" | "faults";

export default function MachineTable({ machines, language, selectedMachineId, onSelectMachine }: Props) {
  const [search, setSearch] = useState("");
  const [fleetFilter, setFleetFilter] = useState<FleetFilter>("all");
  const [modelFilter, setModelFilter] = useState("all");
  const [sortKey, setSortKey] = useState<SortKey>("last_seen_at");

  const models = useMemo(() => {
    return Array.from(new Set(machines.map((machine) => safe(machine.model, "Not available")).filter(Boolean))).slice(0, 80);
  }, [machines]);

  const filtered = useMemo(() => {
    const searchText = search.trim().toLowerCase();
    return machines
      .filter((machine) => {
        const values = [
          machine.machine_id,
          machine.serial_number,
          machine.model,
          machine.machine_type,
          machine.customer,
          machine.location
        ].join(" ").toLowerCase();
        if (searchText && !values.includes(searchText)) return false;
        if (fleetFilter === "offline" && !isOffline(machine)) return false;
        if (fleetFilter === "highRisk" && riskScore(machine) < 70) return false;
        if (fleetFilter === "lowFuel" && !isLowFuel(machine)) return false;
        if (fleetFilter === "lowUtilization" && !isLowUtilization(machine)) return false;
        if (fleetFilter === "faults" && (machine.fault_count ?? 0) <= 0) return false;
        if (modelFilter !== "all" && machine.model !== modelFilter) return false;
        return true;
      })
      .sort((a, b) => compareBySortKey(a, b, sortKey));
  }, [fleetFilter, machines, modelFilter, search, sortKey]);

  const t = language === "zh"
    ? {
        title: "设备列表",
        count: "台",
        search: "搜索设备、序列号、型号、客户、位置",
        all: "全部",
        offline: "离线",
        highRisk: "高风险",
        model: "型号",
        faults: "有故障",
        lowFuel: "低油量",
        lowUtilization: "低利用率",
        sort: "点击列标题排序",
        machine: "设备",
        serial: "序列号",
        type: "类型",
        customer: "客户",
        location: "位置",
        status: "状态",
        fuel: "油量",
        hours: "运行小时",
        lastSeen: "最近通信",
        fault: "故障",
        risk: "风险等级",
        reason: "风险原因",
        action: "建议动作",
        online: "在线",
        dataSource: "数据源",
        missing: "数据缺失"
      }
    : {
        title: "Fleet List",
        count: "machines",
        search: "Search asset, serial, model, customer, location",
        all: "All",
        offline: "Offline",
        highRisk: "High risk",
        model: "Model",
        faults: "Faults",
        lowFuel: "Low fuel",
        lowUtilization: "Low utilization",
        sort: "Click column headers to sort",
        machine: "Machine",
        serial: "Serial",
        type: "Type",
        customer: "Customer",
        location: "Location",
        status: "Status",
        fuel: "Fuel",
        hours: "Hours",
        lastSeen: "Last update",
        fault: "Faults",
        risk: "Risk",
        reason: "Reason",
        action: "Action",
        online: "Online",
        dataSource: "Source",
        missing: "Missing"
      };

  const filterItems: Array<{ key: FleetFilter; label: string }> = [
    { key: "all", label: t.all },
    { key: "offline", label: t.offline },
    { key: "highRisk", label: t.highRisk },
    { key: "lowFuel", label: t.lowFuel },
    { key: "lowUtilization", label: t.lowUtilization },
    { key: "faults", label: t.faults },
  ];

  return (
    <section className="panel">
      <div className="panel-header">
        <div>
          <h2>{t.title}</h2>
          <span>{filtered.length} / {machines.length} {t.count}</span>
        </div>
      </div>
      <div className="filter-bar">
        <input value={search} onChange={(event) => setSearch(event.target.value)} placeholder={t.search} />
        <div className="filter-segment">
          {filterItems.map((item) => (
            <button
              key={item.key}
              className={fleetFilter === item.key ? "toggle-active" : "secondary-button"}
              onClick={() => setFleetFilter(item.key)}
            >
              {item.label}
            </button>
          ))}
        </div>
        <select value={modelFilter} onChange={(event) => setModelFilter(event.target.value)}>
          <option value="all">{t.model}: {t.all}</option>
          {models.map((model) => <option key={model} value={model}>{model}</option>)}
        </select>
        <span className="table-hint">{t.sort}</span>
      </div>
      <div className="table-wrap">
        <table className="data-table">
          <thead>
            <tr>
              <th>{t.machine}</th>
              <th>{t.model}</th>
              <th>{t.serial}</th>
              <th>{t.type}</th>
              <th>{t.customer}</th>
              <th>{t.location}</th>
              <th>{t.status}</th>
              <th><SortableButton label={t.fuel} active={sortKey === "fuel_remaining_percent"} onClick={() => setSortKey("fuel_remaining_percent")} /></th>
              <th><SortableButton label={t.hours} active={sortKey === "operating_hours"} onClick={() => setSortKey("operating_hours")} /></th>
              <th><SortableButton label={t.fault} active={sortKey === "fault_count"} onClick={() => setSortKey("fault_count")} /></th>
              <th><SortableButton label={t.lastSeen} active={sortKey === "last_seen_at"} onClick={() => setSortKey("last_seen_at")} /></th>
              <th>{t.risk}</th>
              <th>{t.reason}</th>
              <th>{t.action}</th>
              <th>{t.dataSource}</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((machine) => (
              <tr
                key={machine.machine_id}
                className={machine.machine_id === selectedMachineId ? "selected" : ""}
                onClick={() => onSelectMachine?.(machine)}
              >
                <td>{safe(machine.machine_id, t.missing)}</td>
                <td>{safe(machine.model, t.missing)}</td>
                <td>{safe(machine.serial_number, t.missing)}</td>
                <td>{safe(machine.machine_type, t.missing)}</td>
                <td>{safe(machine.customer, t.missing)}</td>
                <td>{safe(machine.location, t.missing)}</td>
                <td><StatusBadge label={isOffline(machine) ? t.offline : t.online} tone={isOffline(machine) ? "danger" : "good"} /></td>
                <td>{formatPercent(machine.fuel_remaining_percent, t.missing)}</td>
                <td>{formatNumber(machine.operating_hours, t.missing)}</td>
                <td>{machine.fault_count ?? 0}</td>
                <td>{safe(machine.last_seen_at, t.missing)}</td>
                <td><StatusBadge label={`${riskLevel(machine, language)} ${riskScore(machine)}`} tone={riskTone(machine)} /></td>
                <td>{riskReasons(machine, language).join("; ")}</td>
                <td>{recommendedAction(machine, language)}</td>
                <td>trackunit_cache</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function SortableButton({ label, active, onClick }: { label: string; active: boolean; onClick: () => void }) {
  return <button className={`table-sort ${active ? "active" : ""}`} onClick={onClick}>{label}</button>;
}

function safe(value: string | null | undefined, fallback: string): string {
  return value && value !== "Data not available" ? value : fallback;
}

function formatNumber(value: number | null | undefined, fallback: string): string {
  return value === null || value === undefined ? fallback : value.toLocaleString();
}

function formatPercent(value: number | null | undefined, fallback: string): string {
  return value === null || value === undefined ? fallback : `${value}%`;
}

function compareBySortKey(a: Machine, b: Machine, sortKey: SortKey): number {
  if (sortKey === "last_seen_at") return Date.parse(b.last_seen_at) - Date.parse(a.last_seen_at);
  if (sortKey === "fault_count") return (b.fault_count ?? 0) - (a.fault_count ?? 0);
  const left = a[sortKey] ?? Number.NEGATIVE_INFINITY;
  const right = b[sortKey] ?? Number.NEGATIVE_INFINITY;
  return Number(right) - Number(left);
}
