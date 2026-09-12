import { useCallback, useMemo, useState } from "react";
import {
  ReactFlow,
  Background,
  Controls,
  applyNodeChanges,
} from "@xyflow/react";
import type { NodeChange, Edge } from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import "./grid.css";
import { ShieldCheck, Activity, Zap, Gauge, Info, Layers } from "lucide-react";
import {
  PageHeader,
  Card,
  Stat,
  Tabs,
  Note,
  Status,
  Badge,
} from "../../components/ui";
import { GridCustomNode, type CustomGridNodeType } from "./GridCustomNode";
import {
  BASE_TOPOLOGY_NODES,
  SCENARIO_METRICS,
  SCENARIO_NODE_STATES,
  TOPOLOGY_EDGES,
} from "./gridData";
import type { GridScenario, GridNodeData } from "./types";

const nodeTypes = {
  gridNode: GridCustomNode,
};

function buildInitialNodes(scenario: GridScenario): CustomGridNodeType[] {
  const scenarioStates = SCENARIO_NODE_STATES[scenario];
  return BASE_TOPOLOGY_NODES.map((node) => {
    const state = scenarioStates[node.id];
    const nodeData: GridNodeData = {
      ...node.baseData,
      currentVoltagePu: state.currentVoltagePu,
      currentPowerKw: state.currentPowerKw,
      status: state.status,
      statusLabel: state.statusLabel,
      connectionStatus: String(
        state.connectionStatus ?? node.baseData.connectionStatus,
      ),
      violations: state.violations,
    };

    return {
      id: node.id,
      type: "gridNode",
      position: node.position,
      data: nodeData,
    };
  });
}

function buildEdges(scenario: GridScenario): Edge[] {
  const isUnknown = scenario === "Missing data";
  const isCongested = scenario === "Congestion";
  const isReverse = scenario === "Reverse power flow";

  return TOPOLOGY_EDGES.map((edge) => {
    let strokeColor = "#3d875a"; // Normal green
    let strokeWidth = 2.5;
    let animated = true;
    let strokeDasharray: string | undefined = undefined;

    if (isUnknown) {
      strokeColor = "#9aa396";
      strokeWidth = 2;
      animated = false;
      strokeDasharray = "5 5";
    } else if (isCongested) {
      if (edge.id === "e-util-tx" || edge.id === "e-tx-home1") {
        strokeColor = "#c93b2b"; // Thermal overload
        strokeWidth = 4;
      } else {
        strokeColor = "#d97724"; // High loading
        strokeWidth = 3;
      }
    } else if (isReverse) {
      strokeColor = "#26829c"; // Reverse flow active
      strokeWidth = 3;
    }

    return {
      id: edge.id,
      source: edge.source,
      target: edge.target,
      label: edge.label,
      animated,
      style: {
        stroke: strokeColor,
        strokeWidth,
        strokeDasharray,
      },
      labelStyle: {
        fill: "#4b5f43",
        fontWeight: 600,
        fontSize: 10,
      },
      labelBgStyle: {
        fill: "#f8fbf5",
        fillOpacity: 0.9,
      },
      labelBgPadding: [4, 2] as [number, number],
      labelBgBorderRadius: 4,
    };
  });
}

export default function GridPage() {
  const [scenario, setScenario] = useState<GridScenario>("Normal");
  const [nodes, setNodes] = useState<CustomGridNodeType[]>(() =>
    buildInitialNodes("Normal"),
  );
  const [selectedNodeId, setSelectedNodeId] = useState<string>("transformer");

  // Keep node positions while updating scenario data
  const handleScenarioChange = useCallback((newScenarioName: string) => {
    const newScenario = newScenarioName as GridScenario;
    setScenario(newScenario);
    const scenarioStates = SCENARIO_NODE_STATES[newScenario];

    setNodes((prevNodes) =>
      prevNodes.map((node) => {
        const state = scenarioStates[node.id];
        const updatedData: GridNodeData = {
          ...node.data,
          currentVoltagePu: state.currentVoltagePu,
          currentPowerKw: state.currentPowerKw,
          status: state.status,
          statusLabel: state.statusLabel,
          connectionStatus: String(
            state.connectionStatus ?? node.data.connectionStatus ?? "Connected",
          ),
          violations: state.violations,
        };
        return {
          ...node,
          data: updatedData,
        };
      }),
    );
  }, []);

  const onNodesChange = useCallback(
    (changes: NodeChange<CustomGridNodeType>[]) => {
      setNodes((nds) => applyNodeChanges(changes, nds));
    },
    [],
  );

  const edges = useMemo(() => buildEdges(scenario), [scenario]);
  const metrics = SCENARIO_METRICS[scenario];

  const selectedNode = useMemo(() => {
    return (
      nodes.find((n) => n.id === selectedNodeId) ??
      nodes.find((n) => n.id === "transformer") ??
      nodes[0]
    );
  }, [nodes, selectedNodeId]);

  const stressed = scenario === "Congestion";
  const unknown = scenario === "Missing data";
  const statusValue = unknown ? "unknown" : stressed ? "unsafe" : "safe";

  return (
    <div className="grid-monitor-container">
      <PageHeader
        eyebrow="DISTRIBUTION NETWORK DIGITAL TWIN"
        title="Grid monitor"
        description="Real-time physical topology, bus telemetry, and automated thermal and voltage constraint validation."
        action={
          <Badge tone={metrics.validationOutcomeTone}>
            {scenario.toUpperCase()} SCENARIO ACTIVE
          </Badge>
        }
      />

      {/* Prominent API Gate Notice */}
      <Note>
        <div style={{ display: "flex", gap: "10px", alignItems: "flex-start" }}>
          <Info size={18} style={{ flexShrink: 0, marginTop: "2px" }} />
          <div>
            <strong>Operational Prototype Notice:</strong> Interactive
            illustrative twin. Scenario switching demonstrates network states
            (voltage bands, reverse flow, and telemetry loss) rather than
            executing an active Newton–Raphson solver run. Backend grid
            endpoints (<code>/grid/nodes</code>,{" "}
            <code>/grid/feeders/{`{id}`}/snapshot</code>,{" "}
            <code>/grid/simulations</code>,{" "}
            <code>/grid/validation/{`{id}`}</code>,{" "}
            <code>/trades/{`{id}`}/validate-grid</code>) are not mounted in the
            public FastAPI router. Authoritative validation judgements remain
            pending backend exposure.
          </div>
        </div>
      </Note>

      {/* Network KPIs */}
      <div className="stats-grid four">
        <Stat
          label="Validation outcome"
          value={metrics.validationOutcome}
          note="Feeder operating status"
          icon={<ShieldCheck size={20} />}
          tone={metrics.validationOutcomeTone}
        />
        <Stat
          label="Transformer loading"
          value={
            metrics.transformerLoadingPct !== null
              ? String(metrics.transformerLoadingPct)
              : "—"
          }
          unit={metrics.transformerLoadingPct !== null ? "%" : ""}
          note={
            metrics.transformerLoadingPct !== null
              ? `${metrics.transformerLoadingPct}% of 100 kVA rating`
              : "Telemetry unavailable"
          }
          icon={<Zap size={20} />}
        />
        <Stat
          label="Minimum voltage"
          value={
            metrics.minVoltagePu !== null
              ? metrics.minVoltagePu.toFixed(2)
              : "—"
          }
          unit={metrics.minVoltagePu !== null ? "pu" : ""}
          note={
            metrics.minVoltagePu !== null
              ? "Statutory limit: ≥ 0.94 pu"
              : "Telemetry unavailable"
          }
          icon={<Activity size={20} />}
        />
        <Stat
          label="Max line loading"
          value={
            metrics.maxLineLoadingPct !== null
              ? String(metrics.maxLineLoadingPct)
              : "—"
          }
          unit={metrics.maxLineLoadingPct !== null ? "%" : ""}
          note={
            metrics.maxLineLoadingPct !== null
              ? "Feeder lateral thermal rating"
              : "Telemetry unavailable"
          }
          icon={<Gauge size={20} />}
        />
      </div>

      {/* Interactive Topology Card */}
      <Card
        title="Community distribution topology"
        subtitle="Draggable nodes, pan and zoom. Select any node to inspect physical bus specifications and telemetry."
        action={
          <Tabs
            items={[
              "Normal",
              "Congestion",
              "Missing data",
              "Reverse power flow",
            ]}
            value={scenario}
            onChange={handleScenarioChange}
          />
        }
      >
        <div className="grid-flow-container">
          <ReactFlow
            nodes={nodes}
            edges={edges}
            nodeTypes={nodeTypes}
            onNodesChange={onNodesChange}
            onNodeClick={(_, node) => setSelectedNodeId(node.id)}
            fitView
            nodesConnectable={false}
            minZoom={0.4}
            maxZoom={1.6}
            proOptions={{ hideAttribution: true }}
          >
            <Background color="#d7ded2" gap={20} size={1} />
            <Controls showInteractive={false} />
          </ReactFlow>

          {/* Topology Canvas Legend */}
          <div className="grid-canvas-legend">
            <div className="legend-row">
              <span className="legend-swatch substation" />
              <span>DISCOM Substation (11 kV)</span>
            </div>
            <div className="legend-row">
              <span className="legend-swatch transformer" />
              <span>Distribution Transformer (0.415 kV)</span>
            </div>
            <div className="legend-row">
              <span className="legend-swatch prosumer" />
              <span>Prosumer (Solar PV / Inverter)</span>
            </div>
            <div className="legend-row">
              <span className="legend-swatch consumer" />
              <span>Consumer Demand Node</span>
            </div>
          </div>
        </div>

        {/* Selected Node Inspector */}
        <div className="grid-inspector-container">
          <div className="grid-inspector-top">
            <div className="grid-inspector-target">
              <small>SELECTED NODE INSPECTOR</small>
              <strong>{selectedNode.data.label}</strong>
              <span style={{ fontSize: "11px", color: "var(--muted)" }}>
                {selectedNode.data.sublabel} · {selectedNode.data.busId}
              </span>
            </div>
            <div className="grid-inspector-status-wrap">
              <Status value={statusValue} />
              <span className="grid-inspector-message">
                {metrics.inspectorMessage}
              </span>
            </div>
          </div>

          {/* Node Metadata Key-Value Grid */}
          <div className="grid-metadata-grid">
            <div className="metadata-item">
              <span className="meta-label">Bus Identifier</span>
              <span className="meta-value">{selectedNode.data.busId}</span>
            </div>
            <div className="metadata-item">
              <span className="meta-label">External Reference</span>
              <span className="meta-value">
                {selectedNode.data.externalRef}
              </span>
            </div>
            <div className="metadata-item">
              <span className="meta-label">Rated Capacity</span>
              <span className="meta-value">
                {selectedNode.data.ratedCapacityKw !== null
                  ? `${selectedNode.data.ratedCapacityKw} kW`
                  : "—"}
              </span>
            </div>
            <div className="metadata-item">
              <span className="meta-label">Nominal Voltage</span>
              <span className="meta-value">
                {selectedNode.data.nominalVoltageKv} kV (
                {selectedNode.data.nominalVoltageKv >= 1 ? "11 kV" : "415 V"})
              </span>
            </div>
            <div className="metadata-item">
              <span className="meta-label">Phase Configuration</span>
              <span className="meta-value">
                {selectedNode.data.phaseConfig}
              </span>
            </div>
            <div className="metadata-item">
              <span className="meta-label">Operating Mode</span>
              <span className="meta-value">
                {selectedNode.data.operatingMode}
              </span>
            </div>
            <div className="metadata-item">
              <span className="meta-label">Current Voltage</span>
              <span className="meta-value">
                {selectedNode.data.currentVoltagePu !== null
                  ? `${selectedNode.data.currentVoltagePu.toFixed(2)} pu`
                  : "—"}
              </span>
            </div>
            <div className="metadata-item">
              <span className="meta-label">Active Power Flow</span>
              <span className="meta-value">
                {selectedNode.data.currentPowerKw !== null
                  ? `${selectedNode.data.currentPowerKw > 0 ? "+" : ""}${selectedNode.data.currentPowerKw.toFixed(1)} kW`
                  : "—"}
              </span>
            </div>
            <div className="metadata-item">
              <span className="meta-label">Smart Inverter / Asset</span>
              <span className="meta-value">
                {selectedNode.data.inverterModel ||
                  "Passive Load / Utility Infrastructure"}
              </span>
            </div>
            <div className="metadata-item">
              <span className="meta-label">Telemetry Status</span>
              <span className="meta-value">
                {selectedNode.data.connectionStatus}
              </span>
            </div>
          </div>

          {/* Node Violations or Scenario Warnings */}
          {selectedNode.data.violations &&
            selectedNode.data.violations.length > 0 && (
              <div className="grid-violations-box">
                <div className="grid-violations-title">
                  <ShieldCheck size={14} /> Active Node Constraint Violations
                </div>
                <ul className="grid-violations-list">
                  {selectedNode.data.violations.map((violation, i) => (
                    <li key={i}>{violation}</li>
                  ))}
                </ul>
              </div>
            )}

          {/* Scenario Violations Summary if Node has none but Scenario does */}
          {(!selectedNode.data.violations ||
            selectedNode.data.violations.length === 0) &&
            metrics.violationsSummary && (
              <div className="grid-violations-box">
                <div className="grid-violations-title">
                  <ShieldCheck size={14} /> Feeder-Wide Constraint Findings
                </div>
                <ul className="grid-violations-list">
                  {metrics.violationsSummary.map((item, i) => (
                    <li key={i}>{item}</li>
                  ))}
                </ul>
              </div>
            )}
        </div>
      </Card>

      {/* Educational & Architectural Panels */}
      <div className="grid-edu-grid">
        <Card
          title="Physical grid, not P2P electron routing"
          subtitle="How power really flows through the community"
          className="grid-edu-card"
        >
          <p>
            All community members connect to the existing{" "}
            <strong>DISCOM distribution network</strong>. Electricity obeys the
            laws of physics (Kirchhoff’s laws) and travels along the path of
            least electrical resistance across public conductors and
            distribution transformers—not along private peer-to-peer tunnels.
          </p>
          <p>
            UrjaSetu provides a{" "}
            <strong>digital coordination and local settlement layer</strong>.
            Trading local solar energy offsets energy that would otherwise be
            drawn from the 11 kV grid, lowering system-wide transmission losses
            and avoiding distribution equipment stress.
          </p>
        </Card>

        <Card
          title="Why grid validation precedes trade commitment"
          subtitle="Provisional matching vs. physical safety"
          className="grid-edu-card"
        >
          <p>
            An order match produced by the double-auction matching engine is
            strictly <strong>provisional</strong>. Every proposed bilateral or
            pooled trade must pass automated power-flow simulation checks before
            final commitment.
          </p>
          <p>
            The grid engine validates three non-negotiable physical constraints:
          </p>
          <ul
            style={{
              fontSize: "12px",
              paddingLeft: "18px",
              color: "var(--muted)",
              margin: 0,
            }}
          >
            <li>
              <strong>Thermal Line Limits:</strong> Conductor current cannot
              exceed 100% continuous ampacity.
            </li>
            <li>
              <strong>Transformer Loading:</strong> Substation DTR cannot exceed
              nameplate kVA rating.
            </li>
            <li>
              <strong>Voltage Envelope:</strong> Bus voltages must strictly
              remain within 0.94 pu – 1.06 pu.
            </li>
          </ul>
        </Card>

        <Card
          title="Indian LV distribution standards"
          subtitle="Operating limits & regulatory envelopes"
          className="grid-edu-card"
        >
          <p>
            Indian low-voltage (415V three-phase / 230V single-phase)
            distribution networks are regulated to operate within a{" "}
            <strong>±6% voltage band (0.94 pu to 1.06 pu)</strong>.
          </p>
          <p>
            When midday rooftop PV generation exceeds neighborhood demand,
            reverse power flow causes localized voltage rise. Without smart
            inverter Volt-VAR autonomous control, overvoltage trips rooftop
            inverters. UrjaSetu incentivizes local daytime consumption to
            preserve voltage stability.
          </p>
        </Card>
      </div>
    </div>
  );
}
