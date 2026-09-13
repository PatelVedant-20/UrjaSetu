import { useEffect, useMemo, useState } from "react";
import {
  ReactFlow,
  Background,
  Controls,
  Handle,
  Position,
  useNodesState,
  type Node,
  type NodeProps,
} from "@xyflow/react";
import { Search, Sun, House, Zap, Users, ArrowUpRight } from "lucide-react";
import "@xyflow/react/dist/style.css";
import { LiveChart, HistoryChart } from "./charts";
import {
  Avatar,
  Card,
  Empty,
  Heading,
  Modal,
  PeriodTabs,
  Tag,
  fmt,
  num,
  str,
} from "./ui";
import type { Experience, Member, Period } from "./types";

export function MemberDetails({
  member,
  close,
}: {
  member: Member;
  close: () => void;
}) {
  const [period, setPeriod] = useState<Period>("day");
  const stats = member.periods?.[period];
  return (
    <Modal title="Meet your neighbour" close={close}>
      {member.photo && (
        <img
          className="ux-house-cover"
          src={member.photo}
          alt={`${member.name}'s home`}
        />
      )}
      <div className="ux-member-intro">
        <Avatar name={member.name} src={member.avatar} size="large" />
        <div>
          <h2>{member.name}</h2>
          <p>
            {member.city} · {member.home_type.replaceAll("_", " ")}
          </p>
          <Tag value={member.role} />
        </div>
      </div>
      <div className="ux-member-setup">
        <span>
          <Sun size={17} /> {fmt(member.capacity_kw)} kW rooftop
        </span>
        {member.live && (
          <span>
            <Zap size={17} /> {fmt(member.live.load_kw, 3)} kW demand now
          </span>
        )}
      </div>
      <PeriodTabs value={period} onChange={setPeriod} />
      {stats ? (
        <>
          <div className="ux-detail-stats">
            <div>
              <small>Consumption</small>
              <strong>
                {fmt(stats.load_kwh)} <span>kWh</span>
              </strong>
            </div>
            <div>
              <small>Production</small>
              <strong>
                {fmt(stats.generation_kwh)} <span>kWh</span>
              </strong>
            </div>
            <div>
              <small>Energy to grid</small>
              <strong>
                {fmt(stats.grid_export_kwh)} <span>kWh</span>
              </strong>
            </div>
            <div>
              <small>Grid imports</small>
              <strong>
                {fmt(stats.grid_import_kwh)} <span>kWh</span>
              </strong>
            </div>
          </div>
          <HistoryChart
            data={member.daily.slice(
              -(period === "day" ? 1 : period === "week" ? 7 : 30),
            )}
          />
        </>
      ) : (
        <Empty>
          {member.role === "operator"
            ? "This account manages the community and has no household readings."
            : "This neighbour keeps their energy statistics private."}
        </Empty>
      )}
    </Modal>
  );
}

export function CommunityPage({ data }: { data: Experience }) {
  const [search, setSearch] = useState("");
  const [selected, setSelected] = useState<string | null>(null);
  const member = data.members.find((m) => m.id === selected);
  const households = data.members.filter((m) => m.node_id);
  const visible = data.members.filter((m) =>
    `${m.name} ${m.role} ${m.city}`
      .toLowerCase()
      .includes(search.toLowerCase()),
  );
  return (
    <>
      <Heading
        title="Good neighbours. Better energy."
        subtitle="Meet the people giving your community a little more sunshine."
      />
      <div className="ux-community-banner">
        <div>
          <Users />
          <strong>{households.length}</strong>
          <span>connected households</span>
        </div>
        <div>
          <Sun />
          <strong>
            {fmt(households.reduce((s, m) => s + m.capacity_kw, 0))} kW
          </strong>
          <span>community rooftop capacity</span>
        </div>
        <div>
          <ArrowUpRight />
          <strong>
            {households.filter((m) => m.role === "prosumer").length}
          </strong>
          <span>solar-sharing neighbours</span>
        </div>
      </div>
      <LiveChart scope="community" userId={data.user.id} />
      <div className="ux-section-line">
        <h2>People in your community</h2>
        <label className="ux-search">
          <Search size={17} />
          <input
            aria-label="Search community"
            placeholder="Find a neighbour…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </label>
      </div>
      <div className="ux-member-grid">
        {visible.map((m) => (
          <button
            className="ux-member-card"
            key={m.id}
            onClick={() => setSelected(m.id)}
            aria-label={`View ${m.name}`}
          >
            <div className="ux-member-cover">
              {m.photo ? (
                <img src={m.photo} alt="Household rooftop" />
              ) : (
                <>
                  <Sun size={34} />
                  <House size={70} />
                </>
              )}
            </div>
            <Avatar name={m.name} src={m.avatar} size="large" />
            <div className="ux-member-copy">
              <h3>
                {m.name}
                {m.id === data.user.id && <small>YOU</small>}
              </h3>
              <p>
                {m.city} · {m.role}
              </p>
              <div>
                <span>
                  <strong>{fmt(m.periods?.day?.generation_kwh)}</strong>kWh
                  produced
                </span>
                <span>
                  <strong>{fmt(m.periods?.day?.load_kwh)}</strong>kWh consumed
                </span>
              </div>
              <small>
                {m.periods
                  ? "Last 24 hours · View household →"
                  : "View household →"}
              </small>
            </div>
          </button>
        ))}
      </div>
      {!visible.length && <Empty>No neighbours match that search.</Empty>}
      {member && (
        <MemberDetails member={member} close={() => setSelected(null)} />
      )}
    </>
  );
}

type FlowData = {
  name: string;
  member?: Member;
  kind: string;
  open: () => void;
};
type HouseholdNode = Node<FlowData>;
function EnergyNode({ data }: NodeProps<HouseholdNode>) {
  return (
    <>
      <Handle type="target" position={Position.Top} />
      <button
        className={`ux-flow-node ${data.member?.role === "prosumer" ? "solar" : ""}`}
        onClick={data.open}
        aria-label={`Inspect ${data.name}`}
      >
        {data.member ? (
          <Avatar name={data.name} src={data.member.avatar} />
        ) : (
          <span className="ux-flow-icon">
            <Zap size={23} />
          </span>
        )}
        <strong>{data.name}</strong>
        <small>
          {data.member
            ? data.member.live
              ? `${fmt(data.member.live.generation_kw, 2)} kW solar · ${fmt(data.member.live.load_kw, 2)} kW load`
              : "Household connection"
            : data.kind === "transformer"
              ? "400 V · Community transformer"
              : "11 kV · Distribution grid"}
        </small>
        <span className="ux-flow-pulse" />
      </button>
      <Handle type="source" position={Position.Bottom} />
    </>
  );
}
const nodeTypes = { household: EnergyNode };

export function GridPage({ data }: { data: Experience }) {
  const [selected, setSelected] = useState<string | null>(null);
  const [gridInfo, setGridInfo] = useState<string | null>(null);
  const [nodes, setNodes, onNodesChange] = useNodesState<HouseholdNode>([]);
  const member = data.members.find((m) => m.id === selected);
  useEffect(() => {
    let saved: Record<string, { x: number; y: number }> = {};
    try {
      saved = JSON.parse(
        localStorage.getItem(`urjasetu.grid.${data.user.id}`) || "{}",
      );
    } catch {
      /* Browser storage may be disabled. */
    }
    setNodes((previous) =>
      data.nodes.map((node, index) => {
        const household = data.members.find((m) => m.node_id === node.id);
        const old = previous.find((n) => n.id === node.id);
        const kind = str(node.node_type);
        const households = data.nodes.filter(
          (n) => n.node_type === "connection_point",
        );
        const i = households.findIndex((n) => n.id === node.id);
        const x =
          kind === "substation" || kind === "transformer"
            ? 210
            : (i % 4) * 215 - Math.min(households.length - 1, 3) * 65;
        const y =
          kind === "substation"
            ? 0
            : kind === "transformer"
              ? 160
              : 345 + Math.floor(i / 4) * 155;
        return {
          id: node.id,
          type: "household",
          position: old?.position || saved[node.id] || { x, y },
          data: {
            name:
              household?.name ||
              (kind === "transformer"
                ? "Community feeder"
                : `Distribution grid${index > 1 ? " " + index : ""}`),
            member: household,
            kind,
            open: () =>
              household ? setSelected(household.id) : setGridInfo(node.id),
          },
        };
      }),
    );
  }, [data.nodes, data.members, data.user.id, setNodes]);
  const edges = useMemo(
    () =>
      data.nodes
        .filter((n) => n.parent_node_id)
        .map((n) => ({
          id: `edge-${n.id}`,
          source: str(n.parent_node_id),
          target: n.id,
          animated: true,
          type: "smoothstep",
          style: {
            stroke:
              data.members.find((m) => m.node_id === n.id)?.role === "prosumer"
                ? "#c79a3e"
                : "#6c9b85",
            strokeWidth: 2,
          },
        })),
    [data.nodes, data.members],
  );
  return (
    <>
      <Heading
        title="Your neighbourhood, connected."
        subtitle="Drag households to explore the feeder. Tap a home to meet the person behind the power."
      />
      <Card
        title="Community feeder"
        note={`${data.members.filter((m) => m.node_id).length} households · New neighbours join automatically`}
        action={<span className="ux-live-dot">Connected community</span>}
      >
        <div
          className="ux-network"
          role="region"
          aria-label="Interactive community feeder"
        >
          <ReactFlow
            nodes={nodes}
            edges={edges}
            nodeTypes={nodeTypes}
            onNodesChange={onNodesChange}
            fitView
            fitViewOptions={{ padding: 0.22 }}
            minZoom={0.25}
            maxZoom={1.7}
            onNodeDragStop={(_, node) => {
              try {
                const key = `urjasetu.grid.${data.user.id}`;
                const stored = JSON.parse(localStorage.getItem(key) || "{}");
                stored[node.id] = node.position;
                localStorage.setItem(key, JSON.stringify(stored));
              } catch {
                /* Layout persistence is optional. */
              }
            }}
          >
            <Background gap={22} color="#d7e3d4" />
            <Controls showInteractive={false} />
          </ReactFlow>
        </div>
        <div className="ux-chart-foot">
          <span>● Solar households &nbsp; ● Consumer households</span>
          <span>Animated connections show the feeder topology</span>
        </div>
      </Card>
      <LiveChart scope="community" userId={data.user.id} />
      <Card
        title="Latest grid checks"
        note="Each accepted trade passes voltage and feeder capacity validation."
      >
        {data.grid.length ? (
          <div className="ux-grid-checks">
            {data.grid.slice(0, 6).map((g) => (
              <article key={g.id}>
                <Tag value={g.status} />
                <h3>{fmt(g.max_transformer_loading_pct)}% transformer load</h3>
                <p>
                  {fmt(g.min_voltage_pu, 3)}–{fmt(g.max_voltage_pu, 3)} pu
                  voltage
                </p>
                <small>{str(g.reason)}</small>
              </article>
            ))}
          </div>
        ) : (
          <Empty>A grid check appears when neighbours match a trade.</Empty>
        )}
      </Card>
      {member && (
        <MemberDetails member={member} close={() => setSelected(null)} />
      )}{" "}
      {gridInfo && (
        <Modal
          title="Community grid connection"
          close={() => setGridInfo(null)}
        >
          <p>
            This shared distribution connection links every participating
            household. Each trade is checked against feeder capacity and voltage
            limits.
          </p>
          <p>
            Registered households:{" "}
            {data.members.filter((m) => m.node_id).length}
          </p>
          <p>
            Latest transformer loading:{" "}
            {fmt(data.grid[0]?.max_transformer_loading_pct)}%
          </p>
          <p>
            Connection voltage:{" "}
            {num(data.nodes.find((n) => n.id === gridInfo)?.nominal_voltage_kv)}{" "}
            kV
          </p>
        </Modal>
      )}
    </>
  );
}
