import { useId } from "react";
import { useReducedMotion } from "motion/react";
import {
  ResponsiveContainer,
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
} from "recharts";
import { energySeries } from "../lib/demo";

export interface ChartDataPoint {
  time: string;
  solar?: number | null;
  load?: number | null;
  price?: number | null;
}

interface TooltipPayloadEntry {
  name?: string;
  value?: number | null;
  color?: string;
  dataKey?: string;
}

function GlassTooltip({
  active,
  payload,
  label,
}: {
  active?: boolean;
  payload?: TooltipPayloadEntry[];
  label?: string;
}) {
  if (!active || !payload || !payload.length) return null;

  return (
    <div
      style={{
        background: "rgba(255, 255, 255, 0.9)",
        backdropFilter: "blur(12px)",
        WebkitBackdropFilter: "blur(12px)",
        border: "1px solid rgba(220, 228, 215, 0.95)",
        borderRadius: 10,
        padding: "10px 14px",
        boxShadow:
          "0 10px 25px -5px rgba(35, 63, 45, 0.12), 0 4px 6px -2px rgba(35, 63, 45, 0.04)",
        minWidth: 160,
        fontSize: 12,
      }}
    >
      <div
        style={{
          fontSize: 11,
          fontWeight: 600,
          color: "#4a6350",
          marginBottom: 6,
          borderBottom: "1px solid #eef2eb",
          paddingBottom: 4,
          letterSpacing: "0.2px",
        }}
      >
        {label ? `${label} IST` : "Interval Window"}
      </div>
      <div style={{ display: "flex", flexDirection: "column", gap: 5 }}>
        {payload.map((entry, idx) => (
          <div
            key={idx}
            style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              gap: 12,
            }}
          >
            <span
              style={{
                display: "inline-flex",
                alignItems: "center",
                gap: 6,
                color: "#556b5b",
                fontSize: 11.5,
              }}
            >
              <span
                style={{
                  width: 7,
                  height: 7,
                  borderRadius: "50%",
                  backgroundColor: entry.color || "#3c8865",
                  display: "inline-block",
                }}
              />
              {entry.name?.split(" · ")[0] || entry.name}
            </span>
            <strong style={{ color: "#1a3322", fontWeight: 650 }}>
              {entry.value !== null && entry.value !== undefined
                ? entry.dataKey === "price"
                  ? `₹ ${Number(entry.value).toFixed(2)}`
                  : `${Number(entry.value).toFixed(1)} kW`
                : "—"}
            </strong>
          </div>
        ))}
      </div>
    </div>
  );
}

export default function EnergyChart({
  range = "Today",
  kind = "energy",
  data: customData,
}: {
  range?: string;
  kind?: "energy" | "price";
  data?: ChartDataPoint[];
}) {
  const reducedMotion = useReducedMotion();
  const gradientId = useId().replaceAll(":", "");

  const defaultData =
    range === "Morning"
      ? energySeries.slice(0, 13)
      : range === "Afternoon"
        ? energySeries.slice(12)
        : energySeries;

  const chartData =
    customData && customData.length > 0 ? customData : defaultData;

  return (
    <div
      className="chart"
      role="img"
      aria-label={
        kind === "price"
          ? "Illustrative energy price in INR per kWh over 24 hours"
          : "Illustrative solar generation and community demand in kW over 24 hours"
      }
    >
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart
          data={chartData}
          margin={{ top: 15, right: 15, left: -20, bottom: 0 }}
        >
          <defs>
            <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#3c8865" stopOpacity={0.2} />
              <stop offset="100%" stopColor="#3c8865" stopOpacity={0.01} />
            </linearGradient>
          </defs>
          <CartesianGrid
            vertical={false}
            stroke="#e9ece6"
            strokeDasharray="3 4"
          />
          <XAxis
            dataKey="time"
            tick={{ fontSize: 11, fill: "#858c83" }}
            axisLine={false}
            tickLine={false}
            minTickGap={45}
          />
          <YAxis
            tick={{ fontSize: 11, fill: "#858c83" }}
            axisLine={false}
            tickLine={false}
          />
          <Tooltip content={<GlassTooltip />} />
          <Legend
            iconType="circle"
            iconSize={7}
            wrapperStyle={{ fontSize: 12, paddingTop: 16 }}
          />
          {kind === "energy" ? (
            <>
              <Area
                isAnimationActive={!reducedMotion}
                animationDuration={650}
                name="Solar generation · kW"
                type="monotone"
                dataKey="solar"
                stroke="#3c8865"
                strokeWidth={2.5}
                fill={`url(#${gradientId})`}
              />
              <Area
                isAnimationActive={!reducedMotion}
                animationDuration={650}
                name="Community demand · kW"
                type="monotone"
                dataKey="load"
                stroke="#d4a158"
                strokeWidth={2}
                fill="transparent"
                strokeDasharray="5 5"
              />
            </>
          ) : (
            <Area
              isAnimationActive={!reducedMotion}
              animationDuration={650}
              name="Illustrative price · INR/kWh"
              type="monotone"
              dataKey="price"
              stroke="#3c8865"
              strokeWidth={2.5}
              fill={`url(#${gradientId})`}
            />
          )}
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}
