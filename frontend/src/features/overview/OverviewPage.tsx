import { useState } from "react";
import { Link } from "react-router-dom";
import {
  ArrowUpRight,
  Sun,
  Zap,
  Wallet,
  Users,
  ArrowRight,
  ShieldCheck,
  Activity,
  Leaf,
} from "lucide-react";
import { PageHeader, Card, Stat, Badge, Tabs } from "../../components/ui";
import EnergyChart from "../../components/EnergyChart";
import TradeTable from "../../components/TradeTable";
export default function OverviewPage() {
  const [range, setRange] = useState("Today");
  return (
    <>
      <PageHeader
        eyebrow="YOUR COMMUNITY, CONNECTED"
        title="Good energy. Shared locally."
        description="A clearer picture of your energy, your community, and what comes next."
        action={
          <Link to="/market" className="button primary">
            Explore marketplace <ArrowUpRight size={16} />
          </Link>
        }
      />
      <div className="hero-strip">
        <div>
          <Badge tone="light">THE COMMUNITY ENERGY LOOP</Badge>
          <h2>
            A little sunshine.
            <br />A whole lot of possibility.
          </h2>
          <p>
            Turn local renewable generation into
            <br />a more connected energy community.
          </p>
          <Link to="/energy">
            Meet your energy <ArrowRight size={15} />
          </Link>
        </div>
        <div className="solar-art" aria-hidden="true">
          <div className="orbit orbit-one" />
          <div className="orbit orbit-two" />
          <div className="sun-disc">
            <Sun size={38} />
          </div>
          <div className="art-house house-one">
            <Sun />
            <span>GENERATE</span>
          </div>
          <div className="art-house house-two">
            <Zap />
            <span>SHARE</span>
          </div>
          <div className="art-house house-three">
            <Leaf />
            <span>GROW</span>
          </div>
          <div className="art-tag">
            <span className="status-dot" /> Energy that brings us together
          </div>
        </div>
      </div>
      <div className="stats-grid">
        <Stat
          label="Solar generation"
          value="24.8"
          unit="kW"
          note="Illustrative midday snapshot"
          icon={<Sun size={19} />}
        />
        <Stat
          label="Energy offered"
          value="142.5"
          unit="kWh"
          note="Next day · community supply"
          icon={<Zap size={19} />}
        />
        <Stat
          label="Indicative price"
          value="₹4.65"
          unit="/ kWh"
          note="Sample day-ahead market"
          icon={<Wallet size={19} />}
        />
        <Stat
          label="Community members"
          value="06"
          note="4 prosumers · 2 consumers"
          icon={<Users size={19} />}
        />
      </div>
      <div className="split-main">
        <Card
          title="The community energy picture"
          subtitle="Generation meets demand · illustrative day · IST"
          action={
            <Tabs
              items={["Today", "Morning", "Afternoon"]}
              value={range}
              onChange={setRange}
            />
          }
        >
          <EnergyChart range={range} />
          <div className="chart-insight">
            <Sun size={16} />
            <span>
              Solar generation peaks around noon — a useful window for
              tomorrow’s offers.
            </span>
          </div>
        </Card>
        <Card
          title="Grid at a glance"
          subtitle="Community feeder · illustrative state"
        >
          <div className="grid-gauge">
            <div>
              <ShieldCheck size={26} />
              <strong>Within limits</strong>
              <span>Example validation result</span>
            </div>
          </div>
          <div className="metric-line">
            <span>Transformer loading</span>
            <strong>64%</strong>
          </div>
          <div className="progress">
            <span style={{ width: "64%" }} />
          </div>
          <div className="metric-line">
            <span>Voltage range</span>
            <strong>0.98–1.02 pu</strong>
          </div>
          <Link className="card-link" to="/grid">
            Explore the digital twin <ArrowUpRight size={16} />
          </Link>
        </Card>
      </div>
      <Card
        title="From sunshine to settlement"
        subtitle="Every step has a purpose. Every decision leaves a trail."
        action={<Badge tone="neutral">HOW IT WORKS</Badge>}
      >
        <div className="lifecycle">
          {[
            ["01", "Measure", "/energy"],
            ["02", "Forecast", "/forecasts"],
            ["03", "Match", "/market"],
            ["04", "Validate", "/grid"],
            ["05", "Settle", "/settlements"],
            ["06", "Trace", "/audit"],
          ].map(([n, t, path]) => (
            <Link key={n} to={path}>
              <span>{n}</span>
              <strong>{t}</strong>
              <ArrowRight size={15} />
            </Link>
          ))}
        </div>
      </Card>
      <Card
        title="Recent community trades"
        subtitle="Illustrative activity · proposals remain subject to grid validation"
        action={
          <Link className="text-button" to="/trades">
            All trades <ArrowUpRight size={15} />
          </Link>
        }
      >
        <TradeTable />
      </Card>
      <div className="bottom-note">
        <Activity size={14} /> Built around the existing distribution grid.
        Connected by UrjaSetu.
      </div>
    </>
  );
}
