import { memo } from "react";
import { BaseEdge, getBezierPath, EdgeLabelRenderer } from "@xyflow/react";
import type { EdgeProps } from "@xyflow/react";
import type { GridScenario } from "./gridData";

export interface CustomEdgeData {
  scenario: GridScenario;
  phaseCode?: string;
  label?: string;
  [key: string]: unknown;
}

function GridPowerEdgeComponent({
  id,
  sourceX,
  sourceY,
  targetX,
  targetY,
  sourcePosition,
  targetPosition,
  style = {},
  markerEnd,
  data,
}: EdgeProps) {
  const [edgePath, labelX, labelY] = getBezierPath({
    sourceX,
    sourceY,
    sourcePosition,
    targetX,
    targetY,
    targetPosition,
  });

  const edgeData = data as unknown as CustomEdgeData | undefined;
  const scenario = edgeData?.scenario || "Normal";
  const phaseCode = edgeData?.phaseCode;
  const edgeLabel = edgeData?.label;

  const isUnknown = scenario === "Missing data";
  const isCongested = scenario === "Congestion";

  const strokeColor = isUnknown
    ? "#9a9d96"
    : isCongested
      ? "#cf8751"
      : "#5b9374";

  const particleColor = isCongested ? "#ff9e58" : "#89cca6";
  const particleDur = isCongested ? "0.9s" : "2.2s";

  return (
    <>
      {/* Background conduit path (subtle electrical bus track) */}
      <BaseEdge
        id={`base-${id}`}
        path={edgePath}
        style={{
          stroke: isUnknown ? "#d0d4cd" : isCongested ? "#fae2d0" : "#dbe8dd",
          strokeWidth: isCongested ? 4 : 3,
          strokeLinecap: "round",
          ...style,
        }}
      />

      {/* Main energized line with directional pulse/dash animation */}
      <path
        id={id}
        d={edgePath}
        fill="none"
        stroke={strokeColor}
        strokeWidth={isCongested ? 2.5 : 2}
        strokeDasharray={isUnknown ? "5 6" : isCongested ? "10 8" : "8 10"}
        className={
          isUnknown
            ? "edge-line-static"
            : isCongested
              ? "edge-line-congested"
              : "edge-line-normal"
        }
        markerEnd={markerEnd}
      />

      {/* Traveling energy packet particle (SVG animateMotion) */}
      {!isUnknown && (
        <circle
          r={isCongested ? 4 : 3.5}
          fill={particleColor}
          className="power-particle"
        >
          <animateMotion
            dur={particleDur}
            repeatCount="indefinite"
            path={edgePath}
            rotate="auto"
          />
        </circle>
      )}

      {/* Optional edge metadata pill */}
      {(edgeLabel || phaseCode) && (
        <EdgeLabelRenderer>
          <div
            style={{
              position: "absolute",
              transform: `translate(-50%, -50%) translate(${labelX}px,${labelY}px)`,
              pointerEvents: "all",
            }}
            className={`edge-meta-badge ${
              isUnknown
                ? "edge-badge-gray"
                : isCongested
                  ? "edge-badge-amber"
                  : "edge-badge-green"
            }`}
          >
            {phaseCode && <span className="edge-phase">{phaseCode}</span>}
            {edgeLabel && <span className="edge-desc">{edgeLabel}</span>}
          </div>
        </EdgeLabelRenderer>
      )}
    </>
  );
}

export const GridPowerEdge = memo(GridPowerEdgeComponent);
