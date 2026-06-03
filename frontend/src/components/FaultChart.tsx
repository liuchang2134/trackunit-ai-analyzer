import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { Machine } from "../types";

type Props = {
  machines: Machine[];
  language: "zh" | "en";
};

export default function FaultChart({ machines, language }: Props) {
  const data = machines.map((machine) => ({
    machine: machine.machine_id,
    model: machine.model,
    fault_count: machine.fault_count ?? 0
  }));

  return (
    <section className="panel">
      <div className="panel-header">
        <h2>{language === "zh" ? "故障图表" : "Fault Chart"}</h2>
        <span>{language === "zh" ? "故障数量" : "Fault count"}</span>
      </div>
      <div className="chart">
        <ResponsiveContainer width="100%" height={260}>
          <BarChart data={data}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="machine" />
            <YAxis allowDecimals={false} />
            <Tooltip />
            <Bar dataKey="fault_count" fill="#b42318" radius={[4, 4, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </section>
  );
}
