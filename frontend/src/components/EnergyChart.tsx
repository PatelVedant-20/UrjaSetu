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
          <Tooltip
            contentStyle={{
              borderRadius: 12,
              border: "1px solid #e1e5dc",
              fontSize: 12,
            }}
          />
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
