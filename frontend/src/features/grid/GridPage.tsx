import { useCallback, useState } from "react";
import {
  ReactFlow,
  Background,
  Controls,
  applyNodeChanges,
} from "@xyflow/react";
import type { NodeChange } from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { ShieldCheck, Activity, Zap } from "lucide-react";
import {
  PageHeader,
  Card,
  Stat,
  Tabs,
  Note,
  Status,
} from "../../components/ui";
const initialNodes = [
  {
    id: "utility",
    position: { x: 280, y: 0 },
    data: { label: "⚡ DISCOM substation" },
    className: "flow-utility",
  },
  {
    id: "transformer",
    position: { x: 280, y: 140 },
    data: { label: "Community transformer" },
  },
  {
    id: "solar1",
    position: { x: 30, y: 300 },
    data: { label: "☀ Aarav · Rooftop PV" },
  },
  {
    id: "solar2",
    position: { x: 280, y: 300 },
    data: { label: "☀ Mehta · Rooftop PV" },
  },
  {
    id: "home",
    position: { x: 530, y: 300 },
    data: { label: "⌂ Greenview · Demand" },
  },
];
export default function GridPage() {
  const [scenario, setScenario] = useState("Normal");
  const [nodes, setNodes] = useState(initialNodes);
  const [selected, setSelected] = useState("Community transformer");
  const onNodesChange = useCallback(
    (changes: NodeChange<(typeof initialNodes)[number]>[]) =>
      setNodes((nds) => applyNodeChanges(changes, nds)),
    [],
  );
  const stressed = scenario === "Congestion",
    unknown = scenario === "Missing data";
  const status = unknown ? "unknown" : stressed ? "unsafe" : "safe";
  const edges = [
    ["utility", "transformer"],
    ["transformer", "solar1"],
    ["transformer", "solar2"],
    ["transformer", "home"],
  ].map(([source, target], i) => ({
    id: String(i),
    source,
    target,
    animated: !unknown,
    style: {
      stroke: unknown ? "#9a9d96" : stressed ? "#cf8751" : "#5b9374",
      strokeWidth: 2,
    },
    label: i === 0 ? "11 kV / 0.415 kV" : undefined,
  }));
  return (
    <>
      <PageHeader
        eyebrow="THE NETWORK BEHIND THE NEIGHBORHOOD"
        title="Grid monitor"
        description="Understand the shared distribution network and the limits that keep it reliable."
      />
      <Note>
        Interactive illustrative twin. Scenario switching changes sample values,
        not a power-flow simulation. Grid REST endpoints are not yet exposed.
      </Note>
      <div className="stats-grid three">
        <Stat
          label="Validation outcome"
          value={unknown ? "Unknown" : stressed ? "Unsafe" : "Safe"}
          note="Illustrative scenario result"
          icon={<ShieldCheck size={20} />}
        />
        <Stat
          label="Transformer loading"
          value={unknown ? "—" : stressed ? "108" : "64"}
          unit={unknown ? "" : "%"}
          note={
            unknown
              ? "No measurement available"
              : "Illustrative capacity utilization"
          }
          icon={<Zap size={20} />}
        />
        <Stat
          label="Minimum voltage"
          value={unknown ? "—" : stressed ? "0.91" : "0.98"}
          unit={unknown ? "" : "pu"}
          note="Illustrative network metric"
          icon={<Activity size={20} />}
        />
      </div>
      <Card
        title="Community digital twin"
        subtitle="Drag nodes, pan or zoom. Select a node to inspect it."
        action={
          <Tabs
            items={["Normal", "Congestion", "Missing data"]}
            value={scenario}
            onChange={setScenario}
          />
        }
      >
        <div className="flow-canvas">
          <ReactFlow
            nodes={nodes}
            edges={edges}
            onNodesChange={onNodesChange}
            onNodeClick={(_, node) => setSelected(String(node.data.label))}
            fitView
            nodesConnectable={false}
            minZoom={0.4}
            maxZoom={1.5}
          >
            <Background color="#d8ded2" gap={22} />
            <Controls showInteractive={false} />
          </ReactFlow>
        </div>
        <div className="flow-inspector">
          <div>
            <small>SELECTED NODE</small>
            <strong>{selected}</strong>
          </div>
          <Status value={status} />
          <span>
            {unknown
              ? "Missing measurements prevent a safety decision."
              : stressed
                ? "Capacity exceeded. Do not commit a proposed trade."
                : "Example network state is within limits."}
          </span>
        </div>
      </Card>
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
    </>
  );
}
