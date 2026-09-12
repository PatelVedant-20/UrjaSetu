import { memo } from "react";
import { Handle, Position } from "@xyflow/react";
import type { NodeProps, Node } from "@xyflow/react";
import {
  Zap,
  SunMedium,
  Home,
  Cpu,
  CheckCircle2,
  AlertTriangle,
  AlertOctagon,
  HelpCircle,
} from "lucide-react";
import type { GridNodeData, NodeStatus } from "./types";

export type CustomGridNodeType = Node<GridNodeData, "gridNode">;

function getStatusIcon(status: NodeStatus) {
  switch (status) {
    case "safe":
      return (
        <CheckCircle2
          size={13}
          className="status-ico safe"
          aria-hidden="true"
        />
      );
    case "warning":
      return (
        <AlertTriangle
          size={13}
          className="status-ico warning"
          aria-hidden="true"
        />
      );
    case "unsafe":
      return (
        <AlertOctagon
          size={13}
          className="status-ico unsafe"
          aria-hidden="true"
        />
      );
    case "unknown":
    default:
      return (
        <HelpCircle
          size={13}
          className="status-ico unknown"
          aria-hidden="true"
        />
      );
  }
}

function getNodeTypeIcon(type: GridNodeData["nodeType"]) {
  switch (type) {
    case "feeder_substation":
      return <Zap size={16} aria-hidden="true" />;
    case "distribution_transformer":
      return <Cpu size={16} aria-hidden="true" />;
    case "prosumer":
      return <SunMedium size={16} aria-hidden="true" />;
    case "consumer":
      return <Home size={16} aria-hidden="true" />;
  }
}

function getNodeTypeBadge(type: GridNodeData["nodeType"]) {
  switch (type) {
    case "feeder_substation":
      return "11 kV Substation";
    case "distribution_transformer":
      return "11 / 0.415 kV DTR";
    case "prosumer":
      return "Prosumer PV";
    case "consumer":
      return "Consumer Load";
  }
}

function GridCustomNodeComponent({
  data,
  selected,
}: NodeProps<CustomGridNodeType>) {
  const isSubstation = data.nodeType === "feeder_substation";
  const isTransformer = data.nodeType === "distribution_transformer";

  return (
    <div
      className={`grid-custom-node node-type-${data.nodeType} status-${data.status} ${
        selected ? "is-selected" : ""
      }`}
      role="button"
      tabIndex={0}
      aria-label={`${data.label}: ${data.statusLabel}`}
    >
      {/* Top Handle: Utility has none, others connect to parent */}
      {!isSubstation && (
        <Handle
          type="target"
          position={Position.Top}
          className="custom-handle handle-top"
          isConnectable={false}
        />
      )}

      {/* Node Header */}
      <div className="custom-node-header">
        <div className="node-type-icon-wrapper">
          {getNodeTypeIcon(data.nodeType)}
        </div>
        <div className="custom-node-type-badge">
          {getNodeTypeBadge(data.nodeType)}
        </div>
      </div>

      {/* Title & Subtitle */}
      <div className="custom-node-body">
        <div className="custom-node-title">{data.label}</div>
        <div className="custom-node-sublabel">{data.sublabel}</div>
      </div>

      {/* Telemetry & Electrical Metrics */}
      <div className="custom-node-metrics">
        <div className="metric-chip">
          <span className="metric-name">V</span>
          <span className="metric-val">
            {data.currentVoltagePu !== null
              ? `${data.currentVoltagePu.toFixed(2)} pu`
              : "—"}
          </span>
        </div>
        <div className="metric-chip">
          <span className="metric-name">P</span>
          <span className="metric-val">
            {data.currentPowerKw !== null
              ? `${data.currentPowerKw > 0 ? "+" : ""}${data.currentPowerKw.toFixed(1)} kW`
              : "—"}
          </span>
        </div>
      </div>

      {/* Status Footer */}
      <div className="custom-node-footer">
        <div className="custom-status-pill">
          {getStatusIcon(data.status)}
          <span className="custom-status-text">{data.statusLabel}</span>
        </div>
        {data.violations && data.violations.length > 0 && (
          <span
            className="violation-count-badge"
            title={data.violations.join("\n")}
          >
            ! {data.violations.length}
          </span>
        )}
      </div>

      {/* Bottom Handle: Consumers have none, Substation & Transformer feed children */}
      {(isSubstation || isTransformer) && (
        <Handle
          type="source"
          position={Position.Bottom}
          className="custom-handle handle-bottom"
          isConnectable={false}
        />
      )}
    </div>
  );
}

export const GridCustomNode = memo(GridCustomNodeComponent);
