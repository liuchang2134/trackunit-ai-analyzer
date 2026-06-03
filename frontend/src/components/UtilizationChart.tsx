import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { Machine } from "../types";

type Props = {
  machines: Machine[];
  language: "zh" | "en";
};

export default function UtilizationChart({ machines, language }: Props) {
  const data = machines.map((machine) => ({
    machine: machine.machine_id,
    model: machine.model,
    operating_hours: machine.operating_hours ?? 0
  }));

  return (
    <section className="panel">
      <div className="panel-header">
        <h2>{language === "zh" ? "利用率图表" : "Utilization Chart"}</h2>
        <span>{language === "zh" ? "运行小时" : "Operating hours"}</span>
      </div>
      <div className="chart">
        <ResponsiveContainer width="100%" height={260}>
          <BarChart data={data}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="machine" />
            <YAxis />
            <Tooltip />
            <Bar dataKey="operating_hours" fill="#1457d9" radius={[4, 4, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </section>
  );
}
