import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  ResponsiveContainer,
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  BarChart,
  Bar,
} from "recharts";
import { Download } from "lucide-react";
import { workspaceRequest } from "../../lib/api";
import { exportCsv } from "../../lib/format";
import { Card, Empty, fmt, stamp, Tabs } from "./ui";
import type { Daily } from "./types";

type Point = {
  time: string;
  generation_kw: number;
  load_kw: number;
  grid_export_kw: number;
  grid_import_kw: number;
};
type Series = { as_of: string; points: Point[]; resolution: string };
const colors = {
  generation_kw: "#d9a026",
  load_kw: "#28644d",
  grid_export_kw: "#6799b0",
};

export function LiveChart({
  scope,
  userId,
}: {
  scope: "energy" | "community";
  userId: string;
}) {
  const [window, setWindow] = useState<"live" | "hour" | "day">("live");
  const [resolution, setResolution] = useState("5s");
  const query = useQuery({
    queryKey: ["workspace", "series", userId, scope, window, resolution],
    queryFn: () =>
      workspaceRequest<Series>(
        `/workspace/series?scope=${scope}&window=${window}&resolution=${resolution}`,
      ),
    refetchInterval: 5000,
    staleTime: 4000,
    retry: 1,
  });
  function change(value: typeof window) {
    setWindow(value);
    setResolution(value === "day" ? "15m" : value === "hour" ? "1m" : "5s");
  }
  return (
    <Card
      title={
        scope === "energy" ? "Your energy, in motion" : "Community energy flow"
      }
      note="Generation and demand · kW · Indian Standard Time"
      action={
        <Tabs
          label="Chart range"
          value={window}
          onChange={change}
          options={[
            ["live", "Live"],
            ["hour", "Last hour"],
            ["day", "Last 24 hours"],
          ]}
        />
      }
    >
      <div className="ux-chart-toolbar">
        <span className="ux-live-dot">Refreshes every 5 seconds</span>
        <label>
          Reading interval{" "}
          <select
            aria-label="Reading interval"
            value={resolution}
            onChange={(e) => setResolution(e.target.value)}
          >
            <option value="5s" disabled={window === "day"}>
              5 seconds
            </option>
            <option value="1m">1 minute</option>
            <option value="15m">15 minutes</option>
          </select>
        </label>
        <button
          aria-label="Export chart to CSV"
          onClick={() =>
            exportCsv(query.data?.points ?? [], `${scope}-${window}.csv`)
          }
          disabled={!query.data?.points.length}
        >
          <Download size={15} />
        </button>
      </div>
      {query.isError ? (
        <p className="uw-inline-error" role="alert">
          Readings could not refresh. {query.error.message}
          <button onClick={() => void query.refetch()}>Retry</button>
        </p>
      ) : query.isPending ? (
        <div className="ux-chart-loading">Gathering your energy readings…</div>
      ) : query.data.points.length ? (
        <div
          className="uw-chart"
          role="img"
          aria-label={`${scope} energy chart`}
          data-updated-at={query.data.as_of}
        >
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart
              data={query.data.points}
              margin={{ top: 12, right: 16, bottom: 0, left: 0 }}
            >
              <defs>
                <linearGradient id={`${scope}-sun`} x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#e9ae37" stopOpacity={0.32} />
                  <stop offset="100%" stopColor="#e9ae37" stopOpacity={0.02} />
                </linearGradient>
              </defs>
              <CartesianGrid
                strokeDasharray="3 5"
                vertical={false}
                stroke="#e6ebe3"
              />
              <XAxis
                dataKey="time"
                tickFormatter={(v) => stamp(v)}
                minTickGap={55}
                tick={{ fontSize: 11 }}
              />
              <YAxis width={42} tick={{ fontSize: 11 }} />
              <Tooltip
                labelFormatter={(v) => stamp(v, true)}
                formatter={(v, name) => [`${fmt(v, 3)} kW`, name]}
              />
              <Legend iconType="circle" />
              {Object.entries(colors)
                .filter(
                  ([key]) => scope === "energy" || key !== "grid_export_kw",
                )
                .map(([key, color]) => (
                  <Area
                    key={key}
                    type="monotone"
                    dataKey={key}
                    name={
                      key === "generation_kw"
                        ? "Solar generation"
                        : key === "load_kw"
                          ? "Demand"
                          : "To grid"
                    }
                    stroke={color}
                    strokeWidth={2}
                    fill={
                      key === "generation_kw"
                        ? `url(#${scope}-sun)`
                        : "transparent"
                    }
                    isAnimationActive={false}
                    dot={false}
                  />
                ))}
            </AreaChart>
          </ResponsiveContainer>
        </div>
      ) : (
        <Empty>
          No completed readings in this interval yet. Try the Live view.
        </Empty>
      )}
      <div className="ux-chart-foot">
        <span>
          {window === "live"
            ? "Rolling 15-minute window"
            : window === "hour"
              ? "Rolling 60-minute window"
              : "Rolling 24-hour window"}
        </span>
        <span>Updated {stamp(query.data?.as_of)} IST</span>
      </div>
    </Card>
  );
}

export function HistoryChart({
  data,
  money = false,
}: {
  data: Daily[];
  money?: boolean;
}) {
  return data.length ? (
    <div
      className="uw-chart"
      role="img"
      aria-label={
        money
          ? "Savings and earnings history"
          : "Daily consumption and production history"
      }
    >
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data} barGap={3}>
          <CartesianGrid strokeDasharray="3 5" vertical={false} />
          <XAxis
            dataKey="date"
            tickFormatter={(v) => String(v).slice(5)}
            minTickGap={25}
            tick={{ fontSize: 11 }}
          />
          <YAxis width={50} tick={{ fontSize: 11 }} />
          <Tooltip
            formatter={(v, name) => [
              `${money ? "₹" : ""}${fmt(v)}${money ? "" : " kWh"}`,
              name,
            ]}
          />
          <Legend iconType="circle" />
          <Bar
            dataKey={money ? "savings_inr" : "generation_kwh"}
            name={money ? "Savings comparison" : "Solar generation"}
            fill="#d8a340"
            radius={[4, 4, 0, 0]}
          />
          <Bar
            dataKey={money ? "earned_inr" : "load_kwh"}
            name={money ? "Sales earnings" : "Consumption"}
            fill="#39765d"
            radius={[4, 4, 0, 0]}
          />
          {money && (
            <Bar
              dataKey="spent_inr"
              name="Purchases"
              fill="#87a7b6"
              radius={[4, 4, 0, 0]}
            />
          )}
        </BarChart>
      </ResponsiveContainer>
    </div>
  ) : (
    <Empty>Your daily history will appear here.</Empty>
  );
}
