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
import {
  PageHeader,
  Card,
  Stat,
  Badge,
  Tabs,
  AnimatedCounter,
} from "../../components/ui";
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
          <div style={{ display: "flex", gap: 10 }}>
            <Link to="/market" className="button primary">
              Explore marketplace <ArrowUpRight size={16} />
            </Link>
            <Link to="/energy" className="button secondary">
              My energy <Zap size={15} />
            </Link>
          </div>
        }
      />

      <div className="hero-strip">
        <div className="hero-content">
          <Badge tone="light">THE COMMUNITY ENERGY LOOP</Badge>
          <h2>
            A little sunshine.
            <br />A whole lot of possibility.
          </h2>
          <p>
            Turn local renewable generation into
            <br />a more connected energy community.
          </p>

          <div className="hero-tickers" aria-label="Community energy summary">
            <div className="hero-ticker-item">
              <small>GENERATION</small>
              <div className="hero-ticker-num">
                <AnimatedCounter target={96.4} prefix="⚡ " suffix=" kWh" />
              </div>
            </div>
            <div className="hero-ticker-divider" />
            <div className="hero-ticker-item">
              <small>INDICATIVE PRICE</small>
              <div className="hero-ticker-num">
                <AnimatedCounter
                  target={4.65}
                  decimals={2}
                  prefix="₹ "
                  suffix="/kWh"
                />
              </div>
            </div>
            <div className="hero-ticker-divider" />
            <div className="hero-ticker-item">
              <small>AVOIDED CO₂</small>
              <div className="hero-ticker-num">
                <AnimatedCounter target={12.4} prefix="🌱 " suffix=" kg" />
              </div>
            </div>
          </div>

          <div style={{ display: "flex", gap: 14, marginTop: 16 }}>
            <Link
              to="/energy"
              style={{ display: "inline-flex", alignItems: "center", gap: 4 }}
            >
              Meet your energy <ArrowRight size={15} />
            </Link>
            <Link
              to="/community"
              style={{ display: "inline-flex", alignItems: "center", gap: 4 }}
            >
              Meet members <Users size={15} />
            </Link>
          </div>
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

      {/* Live Visual Energy Flow Loop */}
      <div className="card energy-flow-card">
        <div className="energy-flow-header">
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <span className="pulse-indicator" />
            <strong style={{ fontSize: 13, color: "#1c3524" }}>
              Live Community Energy Loop
            </strong>
          </div>
          <span style={{ fontSize: 11, color: "#6a7e6b" }}>
            Real-time peer-to-peer renewable flow across Ahmedabad Feeder A
          </span>
        </div>

        <div
          className="energy-flow-track"
          role="region"
          aria-label="Energy flow from solar generation to DISCOM grid"
        >
          <div className="flow-node">
            <div className="flow-node-icon solar">
              <Sun size={20} />
            </div>
            <div className="flow-node-text">
              <strong>Solar Generation</strong>
              <span>☀️ 96.4 kWh generated</span>
            </div>
          </div>

          <div className="flow-connector" aria-hidden="true">
            <div className="flow-line">
              <span className="flow-particle" />
            </div>
            <ArrowRight size={14} className="flow-arrow" />
          </div>

          <div className="flow-node">
            <div className="flow-node-icon storage">
              <Zap size={20} />
            </div>
            <div className="flow-node-text">
              <strong>Prosumer Storage</strong>
              <span>🔋 48.0 kWh buffered</span>
            </div>
          </div>

          <div className="flow-connector" aria-hidden="true">
            <div className="flow-line">
              <span className="flow-particle delay-1" />
            </div>
            <ArrowRight size={14} className="flow-arrow" />
          </div>

          <div className="flow-node">
            <div className="flow-node-icon demand">
              <Users size={20} />
            </div>
            <div className="flow-node-text">
              <strong>Neighborhood Demand</strong>
              <span>🏘️ 58.2 kWh absorbed</span>
            </div>
          </div>

          <div className="flow-connector" aria-hidden="true">
            <div className="flow-line">
              <span className="flow-particle delay-2" />
            </div>
            <ArrowRight size={14} className="flow-arrow" />
          </div>

          <div className="flow-node">
            <div className="flow-node-icon grid">
              <ShieldCheck size={20} />
            </div>
            <div className="flow-node-text">
              <strong>DISCOM Grid</strong>
              <span>⚡ Feeder balanced (0.99 pu)</span>
            </div>
          </div>
        </div>
      </div>

      <div className="stats-grid">
        <Stat
          label="Solar generation"
          value="24.8"
          unit="kW"
          note="Midday generation snapshot"
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
          note="Day-ahead clearing estimate"
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
          subtitle="Generation meets demand · illustrative day · Asia/Kolkata (IST)"
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
              Solar generation peaks between 11:00 and 13:00 IST — the primary
              window for day-ahead surplus dispatch.
            </span>
          </div>
        </Card>

        <Card
          title="Grid at a glance"
          subtitle="Community feeder · live digital twin state"
        >
          <div className="grid-gauge">
            <div>
              <ShieldCheck size={26} />
              <strong>Within limits</strong>
              <span>Power-flow safe</span>
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
            <span>Voltage operating range</span>
            <strong>0.98–1.02 pu</strong>
          </div>
          <Link className="card-link" to="/grid">
            Explore the digital twin <ArrowUpRight size={16} />
          </Link>
        </Card>
      </div>

      {/* Community Energy Lifecycle Loop */}
      <Card
        title="The community energy lifecycle"
        subtitle="How local renewable electricity moves from sunlight to verified settlement"
        action={<Badge tone="neutral">LIFECYCLE ARCHITECTURE</Badge>}
      >
        <div className="lifecycle">
          {[
            ["01", "Identity & Assets", "/community"],
            ["02", "Telemetry & Meters", "/energy"],
            ["03", "Forecasts & Surplus", "/forecasts"],
            ["04", "Day-Ahead Orders", "/market"],
            ["05", "Matching & Proposals", "/trades"],
            ["06", "Grid Validation", "/grid"],
            ["07", "Settlement & Audit", "/settlements"],
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
        <Activity size={14} /> Power flows physically across the DISCOM
        distribution grid. Connected and coordinated by UrjaSetu.
      </div>
    </>
  );
}
