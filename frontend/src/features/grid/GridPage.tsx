import { useState, useCallback, useMemo } from "react";
import {
  ReactFlow,
  Background,
  Controls,
  applyNodeChanges,
  ReactFlowProvider,
} from "@xyflow/react";
import type { Node, Edge, NodeChange } from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import {
  ShieldCheck,
  ShieldAlert,
  Activity,
  Zap,
  HelpCircle,
  Maximize2,
  Minimize2,
} from "lucide-react";
import { motion, AnimatePresence } from "motion/react";

import { PageHeader, Card, Note } from "../../components/ui";
import {
  GRID_NODES_CONFIG,
  GRID_EDGES_CONFIG,
  type GridScenario,
} from "./gridData";
import { GridCustomNode } from "./GridCustomNode";
import { GridPowerEdge } from "./GridPowerEdge";
import { NodeInspectorHUD } from "./NodeInspectorHUD";
import { GridLifecycleStepper } from "./GridLifecycleStepper";
import { GridCanvasControls } from "./GridCanvasControls";

const nodeTypes = {
  gridNode: GridCustomNode,
};

const edgeTypes = {
  gridEdge: GridPowerEdge,
};

export default function GridPage() {
  const [scenario, setScenario] = useState<GridScenario>("Normal");
  const [selected, setSelected] = useState<string>("Community transformer");
  const [isFocused, setIsFocused] = useState<boolean>(false);

  const stressed = scenario === "Congestion";
  const unknown = scenario === "Missing data";

  // Selected node configuration for HUD
  const selectedConfig = useMemo(() => {
    return Object.values(GRID_NODES_CONFIG).find(
      (cfg) =>
        cfg.name.toLowerCase() === selected.toLowerCase() ||
        selected.toLowerCase().includes(cfg.name.toLowerCase()) ||
        cfg.id.toLowerCase() === selected.toLowerCase(),
    );
  }, [selected]);

  // Dynamic nodes array synced with scenario & selection
  const [nodes, setNodes] = useState<Node[]>(() =>
    Object.values(GRID_NODES_CONFIG).map((cfg) => ({
      id: cfg.id,
      type: "gridNode",
      position: cfg.initialPosition,
      data: {
        label: cfg.name,
        config: cfg,
        scenario: "Normal",
      },
      className: cfg.id === "utility" ? "flow-utility" : undefined,
    })),
  );

  // Keep node scenario and selection synchronized
  const activeNodes = useMemo(() => {
    return nodes.map((node) => ({
      ...node,
      data: {
        ...node.data,
        scenario,
      },
      selected:
        node.id === selectedConfig?.id ||
        String(node.data?.label).toLowerCase() === selected.toLowerCase(),
    }));
  }, [nodes, scenario, selected, selectedConfig]);

  const onNodesChange = useCallback(
    (changes: NodeChange<Node>[]) =>
      setNodes((nds) => applyNodeChanges(changes, nds)),
    [],
  );

  // Dynamic edges array reflecting power flow particles
  const edges: Edge[] = useMemo(() => {
    return GRID_EDGES_CONFIG.map((edgeCfg) => ({
      id: edgeCfg.id,
      source: edgeCfg.source,
      target: edgeCfg.target,
      type: "gridEdge",
      animated: !unknown,
      data: {
        scenario,
        phaseCode: edgeCfg.phaseCode,
        label: edgeCfg.label,
      },
    }));
  }, [scenario, unknown]);

  const handleNodeClick = useCallback((_: React.MouseEvent, node: Node) => {
    setSelected(String(node.data.label));
  }, []);

  return (
    <ReactFlowProvider>
      <div className="grid-page-container">
        <PageHeader
          eyebrow="THE NETWORK BEHIND THE NEIGHBORHOOD"
          title="Grid monitor"
          description="Understand the shared distribution network and the limits that keep it reliable."
        />

        <Note>
          Interactive illustrative twin. Scenario switching changes sample
          values, not a power-flow simulation. Grid REST endpoints are not yet
          exposed.
        </Note>

        {/* Dynamic Top Stat Counters with micro-transitions */}
        <div className="stats-grid three">
          <div className="stat card">
            <div className="stat-top">
              <span>Validation outcome</span>
              <span className="stat-icon">
                {unknown ? (
                  <HelpCircle size={20} className="icon-unknown" />
                ) : stressed ? (
                  <ShieldAlert size={20} className="icon-unsafe" />
                ) : (
                  <ShieldCheck size={20} className="icon-safe" />
                )}
              </span>
            </div>
            <AnimatePresence mode="wait">
              <motion.div
                key={scenario + "-outcome"}
                initial={{ opacity: 0, y: -6 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: 6 }}
                transition={{ duration: 0.2 }}
                className={`stat-value ${
                  unknown
                    ? "text-unknown"
                    : stressed
                      ? "text-unsafe"
                      : "text-safe"
                }`}
              >
                {unknown ? "Unknown" : stressed ? "Unsafe" : "Safe"}
              </motion.div>
            </AnimatePresence>
            <div className="stat-note">
              <span>Illustrative scenario result</span>
            </div>
          </div>

          <div className="stat card">
            <div className="stat-top">
              <span>Transformer loading</span>
              <span className="stat-icon">
                <Zap size={20} />
              </span>
            </div>
            <AnimatePresence mode="wait">
              <motion.div
                key={scenario + "-loading"}
                initial={{ opacity: 0, y: -6 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: 6 }}
                transition={{ duration: 0.2 }}
                className={`stat-value ${stressed && !unknown ? "text-unsafe" : ""}`}
              >
                {unknown ? "—" : stressed ? "108" : "64"}
                <small>{unknown ? "" : "%"}</small>
              </motion.div>
            </AnimatePresence>
            <div className="stat-note">
              <span>
                {unknown
                  ? "No measurement available"
                  : "Illustrative capacity utilization"}
              </span>
            </div>
          </div>

          <div className="stat card">
            <div className="stat-top">
              <span>Minimum voltage</span>
              <span className="stat-icon">
                <Activity size={20} />
              </span>
            </div>
            <AnimatePresence mode="wait">
              <motion.div
                key={scenario + "-voltage"}
                initial={{ opacity: 0, y: -6 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: 6 }}
                transition={{ duration: 0.2 }}
                className={`stat-value ${stressed && !unknown ? "text-unsafe" : ""}`}
              >
                {unknown ? "—" : stressed ? "0.91" : "0.98"}
                <small>{unknown ? "" : "pu"}</small>
              </motion.div>
            </AnimatePresence>
            <div className="stat-note">
              <span>Illustrative network metric</span>
            </div>
          </div>
        </div>

        {/* Main Digital Twin Canvas Card */}
        <Card
          title="Community digital twin"
          subtitle="Drag nodes, pan or zoom. Select a node to inspect it."
          action={
            <div className="grid-card-actions">
              <div
                className="tabs scenario-tabs"
                role="group"
                aria-label="Scenario selection"
              >
                {(
                  ["Normal", "Congestion", "Missing data"] as GridScenario[]
                ).map((item) => {
                  const isSelected = item === scenario;
                  return (
                    <button
                      key={item}
                      type="button"
                      aria-pressed={isSelected}
                      className={`scenario-tab-btn ${isSelected ? "selected" : ""}`}
                      onClick={() => setScenario(item)}
                    >
                      {isSelected && (
                        <motion.span
                          layoutId="activeScenarioTabPill"
                          className="active-pill-bg"
                          transition={{
                            type: "spring",
                            stiffness: 450,
                            damping: 35,
                          }}
                        />
                      )}
                      <span className="tab-text">{item}</span>
                    </button>
                  );
                })}
              </div>

              <button
                type="button"
                className={`button secondary focus-toggle-header-btn ${
                  isFocused ? "focused-active" : ""
                }`}
                onClick={() => setIsFocused((prev) => !prev)}
                title={isFocused ? "Exit Focus Mode" : "Expand Focus Mode"}
              >
                {isFocused ? <Minimize2 size={13} /> : <Maximize2 size={13} />}
                <span>{isFocused ? "Exit Focus" : "Focus Mode"}</span>
              </button>
            </div>
          }
        >
          {/* Ambient radial vignette canvas */}
          <div className={`flow-canvas ${isFocused ? "is-focused" : ""}`}>
            <div className="flow-canvas-vignette" />
            <ReactFlow
              nodes={activeNodes}
              edges={edges}
              nodeTypes={nodeTypes}
              edgeTypes={edgeTypes}
              onNodesChange={onNodesChange}
              onNodeClick={handleNodeClick}
              fitView
              nodesConnectable={false}
              minZoom={0.4}
              maxZoom={1.8}
            >
              <Background color="#d8ded2" gap={22} size={1.2} />
              <Controls showInteractive={false} position="bottom-right" />
              <GridCanvasControls
                isFocused={isFocused}
                onToggleFocus={() => setIsFocused((prev) => !prev)}
              />
            </ReactFlow>
          </div>

          {/* Interactive Node Inspector HUD */}
          <NodeInspectorHUD
            selectedLabel={selected}
            nodeConfig={selectedConfig}
            scenario={scenario}
          />
        </Card>

        {/* Animated Transaction & Grid Validation Lifecycle Stepper */}
        <GridLifecycleStepper scenario={scenario} />

        {/* Two-Col Physical & Conceptual Clarity Cards */}
        <div className="two-col">
          <Card title="Why grid validation matters">
            <p className="body-copy">
              An order match is only the beginning. Every proposed trade must be
              checked against line loading, transformer capacity and voltage
              limits before commitment.
            </p>
          </Card>
          <Card title="One grid. A shared digital layer.">
            <p className="body-copy">
              Connections show electrical infrastructure, not peer-to-peer
              electron routes. Physical supply continues through the existing
              DISCOM distribution network.
            </p>
          </Card>
        </div>
      </div>
    </ReactFlowProvider>
  );
}
