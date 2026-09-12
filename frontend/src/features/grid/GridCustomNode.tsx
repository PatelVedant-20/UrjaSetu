import { memo } from "react";
import { Handle, Position } from "@xyflow/react";
import type { NodeProps } from "@xyflow/react";
import { Building2, Zap, Sun, Home, AlertCircle } from "lucide-react";
import type { GridNodeConfig, GridScenario } from "./gridData";

export interface CustomNodeData {
  label: string;
  config: GridNodeConfig;
  scenario: GridScenario;
  [key: string]: unknown;
}

const ICONS = {
  Building2,
  Zap,
  Sun,
  Home,
};

function GridCustomNodeComponent({ data, selected }: NodeProps) {
  const nodeData = data as unknown as CustomNodeData;
  const config = nodeData.config;
  const scenario = nodeData.scenario || "Normal";
  const telemetry = config.telemetry[scenario];

  const IconComponent = ICONS[config.iconName] || Zap;

  const isUnknown = scenario === "Missing data";
  const isCongested = scenario === "Congestion";

  const glowClass = isUnknown
    ? "glow-ring-gray"
    : isCongested
      ? "glow-ring-amber"
      : "glow-ring-green";

  const statusBadgeText = isUnknown
    ? "Observability Blackout"
    : isCongested
      ? "Congestion Warning"
      : "Normal Operation";

  const statusDotClass = isUnknown
    ? "dot-gray"
    : isCongested
      ? "dot-amber"
      : "dot-green";

  return (
    <div
      className={`grid-node-card ${glowClass} ${selected ? "node-selected" : ""} node-type-${config.type}`}
      tabIndex={0}
      role="button"
      aria-label={`${config.name}: ${statusBadgeText}`}
    >
      {/* Top connector handle for power flow input */}
      <Handle
        type="target"
        position={Position.Top}
        className="flow-handle flow-handle-top"
      />

      <div className="grid-node-header">
        <div className={`grid-node-icon-wrapper icon-bg-${config.type}`}>
          <IconComponent size={16} strokeWidth={2.2} />
        </div>
        <div className="grid-node-titles">
          <div className="grid-node-name">{config.name}</div>
          <div className="grid-node-subtitle">{config.subtitle}</div>
        </div>
        <div
          className={`grid-node-status-dot ${statusDotClass}`}
          title={statusBadgeText}
        />
      </div>

      <div className="grid-node-body">
        <div className="grid-node-chip">
          {isUnknown ? (
            <span className="chip-muted">
              <AlertCircle
                size={10}
                style={{ display: "inline", marginRight: "3px" }}
              />
              Telemetry: —
            </span>
          ) : (
            <span className={isCongested ? "chip-warn" : "chip-live"}>
              {telemetry.chipLabel}
            </span>
          )}
        </div>

        <div className="grid-node-submeta">
          <span>{config.nominalVoltage}</span>
          <span className="meta-sep">·</span>
          <span>{config.ratedCapacity}</span>
        </div>
      </div>

      {/* Bottom connector handle for power flow output */}
      <Handle
        type="source"
        position={Position.Bottom}
        className="flow-handle flow-handle-bottom"
      />
    </div>
  );
}

export const GridCustomNode = memo(GridCustomNodeComponent);
