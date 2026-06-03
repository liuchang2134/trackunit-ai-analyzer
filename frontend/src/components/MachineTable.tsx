import { useMemo, useState } from "react";
import type { Machine } from "../types";
import StatusBadge from "./StatusBadge";

type Props = {
  machines: Machine[];
  language: "zh" | "en";
  selectedMachineId?: string | null;
  onSelectMachine?: (machine: Machine) => void;
};

type SortKey = "last_seen_at" | "operating_hours" | "fuel_remaining_percent";

export default function MachineTable({ machines, language, selectedMachineId, onSelectMachine }: Props) {
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("all");
  const [modelFilter, setModelFilter] = useState("all");
  const [issueFilter, setIssueFilter] = useState("all");
  const [sortKey, setSortKey] = useState<SortKey>("last_seen_at");

  const models = useMemo(() => {
    return Array.from(new Set(machines.map((machine) => safe(machine.model)).filter(Boolean))).slice(0, 80);
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
        if (statusFilter === "offline" && !isOffline(machine)) return false;
        if (statusFilter === "online" && isOffline(machine)) return false;
        if (modelFilter !== "all" && machine.model !== modelFilter) return false;
        if (issueFilter === "faults" && (machine.fault_count ?? 0) <= 0) return false;
        if (issueFilter === "lowFuel" && !isLowFuel(machine)) return false;
        if (issueFilter === "lowUtilization" && !isLowUtilization(machine)) return false;
        return true;
      })
      .sort((a, b) => compareBySortKey(a, b, sortKey));
  }, [issueFilter, machines, modelFilter, search, sortKey, statusFilter]);

  const t = language === "zh"
    ? {
        title: "设备列表",
        count: "台",
        search: "搜索设备、序列号、型号、客户、位置",
        status: "状态",
        all: "全部",
        online: "在线",
        offline: "离线",
        model: "型号",
        issue: "问题",
        faults: "有故障",
        lowFuel: "低油量",
        lowUtilization: "低利用率",
        sort: "排序",
        machine: "设备",
        serial: "序列号",
        type: "类型",
        customer: "客户",
        location: "位置",
        fuel: "油量",
        hours: "运行小时",
        lastSeen: "最近通信",
        fault: "故障",
        source: "数据源"
      }
    : {
        title: "Fleet List",
        count: "machines",
        search: "Search asset, serial, model, customer, location",
        status: "Status",
        all: "All",
        online: "Online",
        offline: "Offline",
        model: "Model",
        issue: "Issue",
        faults: "Faults",
        lowFuel: "Low fuel",
        lowUtilization: "Low utilization",
        sort: "Sort",
        machine: "Machine",
        serial: "Serial",
        type: "Type",
        customer: "Customer",
        location: "Location",
        fuel: "Fuel",
        hours: "Hours",
        lastSeen: "Last update",
        fault: "Faults",
        source: "Source"
      };

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
        <select value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)}>
          <option value="all">{t.status}: {t.all}</option>
          <option value="online">{t.online}</option>
          <option value="offline">{t.offline}</option>
        </select>
        <select value={modelFilter} onChange={(event) => setModelFilter(event.target.value)}>
          <option value="all">{t.model}: {t.all}</option>
          {models.map((model) => <option key={model} value={model}>{model}</option>)}
        </select>
        <select value={issueFilter} onChange={(event) => setIssueFilter(event.target.value)}>
          <option value="all">{t.issue}: {t.all}</option>
          <option value="faults">{t.faults}</option>
          <option value="lowFuel">{t.lowFuel}</option>
          <option value="lowUtilization">{t.lowUtilization}</option>
        </select>
        <select value={sortKey} onChange={(event) => setSortKey(event.target.value as SortKey)}>
          <option value="last_seen_at">{t.sort}: {t.lastSeen}</option>
          <option value="operating_hours">{t.hours}</option>
          <option value="fuel_remaining_percent">{t.fuel}</option>
        </select>
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
              <th>{t.fuel}</th>
              <th>{t.hours}</th>
              <th>{t.fault}</th>
              <th>{t.lastSeen}</th>
              <th>{t.source}</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((machine) => (
              <tr
                key={machine.machine_id}
                className={machine.machine_id === selectedMachineId ? "selected" : ""}
                onClick={() => onSelectMachine?.(machine)}
              >
                <td>{safe(machine.machine_id)}</td>
                <td>{safe(machine.model)}</td>
                <td>{safe(machine.serial_number)}</td>
                <td>{safe(machine.machine_type)}</td>
                <td>{safe(machine.customer)}</td>
                <td>{safe(machine.location)}</td>
                <td><StatusBadge label={isOffline(machine) ? t.offline : t.online} tone={isOffline(machine) ? "danger" : "good"} /></td>
                <td>{formatPercent(machine.fuel_remaining_percent)}</td>
                <td>{formatNumber(machine.operating_hours)}</td>
                <td>{machine.fault_count ?? 0}</td>
                <td>{safe(machine.last_seen_at)}</td>
                <td>trackunit_cache</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function safe(value: string | null | undefined): string {
  return value && value !== "Data not available" ? value : "Not available";
}

function formatNumber(value: number | null | undefined): string {
  return value === null || value === undefined ? "Not available" : value.toLocaleString();
}

function formatPercent(value: number | null | undefined): string {
  return value === null || value === undefined ? "Missing field" : `${value}%`;
}

function isLowFuel(machine: Machine): boolean {
  return machine.fuel_remaining_percent !== null && machine.fuel_remaining_percent !== undefined && machine.fuel_remaining_percent <= 10;
}

function isLowUtilization(machine: Machine): boolean {
  return machine.risk_level === "Low Utilization" || (machine.operating_hours !== null && machine.operating_hours !== undefined && machine.operating_hours < 50);
}

function isOffline(machine: Machine): boolean {
  const timestamp = Date.parse(machine.last_seen_at);
  if (Number.isNaN(timestamp)) return false;
  return Date.now() - timestamp > 72 * 60 * 60 * 1000;
}

function compareBySortKey(a: Machine, b: Machine, sortKey: SortKey): number {
  if (sortKey === "last_seen_at") return Date.parse(b.last_seen_at) - Date.parse(a.last_seen_at);
  const left = a[sortKey] ?? Number.NEGATIVE_INFINITY;
  const right = b[sortKey] ?? Number.NEGATIVE_INFINITY;
  return Number(right) - Number(left);
}
