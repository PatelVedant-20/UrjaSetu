import { memo } from "react";
import { Status } from "../../components/ui";
import {
  Activity,
  Zap,
  ShieldCheck,
  ShieldAlert,
  Gauge,
  Layers,
  HelpCircle,
} from "lucide-react";
import type { GridScenario, GridNodeConfig } from "./gridData";

interface NodeInspectorHUDProps {
  selectedLabel: string;
  nodeConfig?: GridNodeConfig;
  scenario: GridScenario;
}

function NodeInspectorHUDComponent({
  selectedLabel,
  nodeConfig,
  scenario,
}: NodeInspectorHUDProps) {
  const stressed = scenario === "Congestion";
  const unknown = scenario === "Missing data";
  const status = unknown ? "unknown" : stressed ? "unsafe" : "safe";

  const telemetry = nodeConfig ? nodeConfig.telemetry[scenario] : null;

  // Strict rule: missing measurements must strictly render as '—' (em dash), never '0'.
  const displayVoltage =
    telemetry?.voltagePu != null
      ? `${telemetry.voltagePu} pu (${telemetry.voltageV})`
      : "—";

  const displayPower =
    telemetry?.activePowerKw != null ? `${telemetry.activePowerKw} kW` : "—";

  const displayLoading = telemetry?.loadingPct ?? "—";
  const displayMargin = telemetry?.safetyMargin ?? "—";
  const displayPhase = nodeConfig?.phase ?? "—";
  const displayCapacity = nodeConfig?.ratedCapacity ?? "—";
  const displayGridHealth =
    telemetry?.powerFactor != null && telemetry?.frequencyHz != null
      ? `${telemetry.powerFactor} · ${telemetry.frequencyHz}`
      : "—";

  return (
    <div className="flow-inspector-wrapper">
      {/* Primary Inspector Banner - strictly preserves workspace.spec.ts classes and text */}
      <div className="flow-inspector">
        <div className="inspector-primary-info">
          <small>SELECTED NODE</small>
          <strong>{selectedLabel}</strong>
        </div>
        <Status value={status} />
        <span className="inspector-decision-text">
          {unknown
            ? "Missing measurements prevent a safety decision."
            : stressed
              ? "Capacity exceeded. Do not commit a proposed trade."
              : "Example network state is within limits."}
        </span>
      </div>

      {/* High-density interactive Telemetry HUD */}
      <div className="hud-telemetry-panel">
        <div className="hud-metric-card">
          <div className="hud-metric-label">
            <Activity size={12} className="hud-icon" />
            <span>Bus Voltage</span>
          </div>
          <div className="hud-metric-value">{displayVoltage}</div>
          <div className="hud-metric-sub">
            {unknown
              ? "Telemetry disconnected"
              : "Nominal: " + (nodeConfig?.nominalVoltage ?? "230V")}
          </div>
        </div>

        <div className="hud-metric-card">
          <div className="hud-metric-label">
            <Zap size={12} className="hud-icon" />
            <span>Active Power</span>
          </div>
          <div className="hud-metric-value">{displayPower}</div>
          <div className="hud-metric-sub">
            {unknown ? "Telemetry disconnected" : "Rated: " + displayCapacity}
          </div>
        </div>

        <div className="hud-metric-card">
          <div className="hud-metric-label">
            <Gauge size={12} className="hud-icon" />
            <span>Line / Thermal Loading</span>
          </div>
          <div
            className={`hud-metric-value ${stressed && !unknown ? "hud-text-warn" : ""}`}
          >
            {displayLoading}
          </div>
          <div className="hud-metric-sub">
            {unknown ? "Telemetry disconnected" : "Rated limit threshold"}
          </div>
        </div>

        <div className="hud-metric-card">
          <div className="hud-metric-label">
            {stressed ? (
              <ShieldAlert size={12} className="hud-icon hud-icon-warn" />
            ) : unknown ? (
              <HelpCircle size={12} className="hud-icon" />
            ) : (
              <ShieldCheck size={12} className="hud-icon hud-icon-safe" />
            )}
            <span>Safety Margin</span>
          </div>
          <div
            className={`hud-metric-value ${stressed && !unknown ? "hud-text-warn" : ""}`}
          >
            {displayMargin}
          </div>
          <div className="hud-metric-sub">
            {unknown ? "Safety decision unavailable" : "DISCOM network rule"}
          </div>
        </div>

        <div className="hud-metric-card">
          <div className="hud-metric-label">
            <Layers size={12} className="hud-icon" />
            <span>Phase & Config</span>
          </div>
          <div className="hud-metric-value hud-text-small">{displayPhase}</div>
          <div className="hud-metric-sub">Physical connection</div>
        </div>

        <div className="hud-metric-card">
          <div className="hud-metric-label">
            <Activity size={12} className="hud-icon" />
            <span>Power Quality</span>
          </div>
          <div className="hud-metric-value hud-text-small">
            {displayGridHealth}
          </div>
          <div className="hud-metric-sub">
            {unknown ? "Telemetry disconnected" : "PF & 50Hz Standard"}
          </div>
        </div>
      </div>
    </div>
  );
}

export const NodeInspectorHUD = memo(NodeInspectorHUDComponent);
