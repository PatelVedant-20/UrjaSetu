import { useState } from "react";
import { Sun, Zap, Radio, ArrowUpRight } from "lucide-react";
import { Link } from "react-router-dom";
import {
  PageHeader,
  Card,
  Stat,
  Status,
  Tabs,
  Note,
} from "../../components/ui";
import EnergyChart from "../../components/EnergyChart";
export default function EnergyPage() {
  const [range, setRange] = useState("Today");
  return (
    <>
      <PageHeader
        eyebrow="YOUR ROOFTOP, REIMAGINED"
        title="My energy"
        description="Know what you generate, what you use, and what you can share."
        action={
          <Link className="button secondary" to="/settings">
            Connect a site <ArrowUpRight size={16} />
          </Link>
        }
      />
      <div className="stats-grid three">
        <Stat
          label="Generation"
          value="6.4"
          unit="kW"
          note="Illustrative current output"
          icon={<Sun size={20} />}
        />
        <Stat
          label="Home demand"
          value="2.1"
          unit="kW"
          note="Illustrative current demand"
          icon={<Zap size={20} />}
        />
        <Stat
          label="Meter quality"
          value="Valid"
          note="Example data-quality assessment"
          icon={<Radio size={20} />}
        />
      </div>
      <div className="split-main">
        <Card
          title="Generation & consumption"
          subtitle="Community-scale illustrative series · IST"
          action={
            <Tabs
              items={["Today", "Morning", "Afternoon"]}
              value={range}
              onChange={setRange}
            />
          }
        >
          <EnergyChart range={range} />
        </Card>
        <Card className="site-card">
          <img
            src="/images/placeholders/solar-roof.svg"
            alt="Illustration of a home with rooftop solar panels"
          />
          <div className="site-body">
            <Status value="discom_verified" />
            <h2>Aarav Residence</h2>
            <p>Illustrative site · Ahmedabad community</p>
            <div className="metric-line">
              <span>Installed solar</span>
              <strong>8.0 kW</strong>
            </div>
            <div className="metric-line">
              <span>Grid connection</span>
              <strong>Feeder A · Node 01</strong>
            </div>
          </div>
        </Card>
      </div>
      <Card
        title="Connected equipment"
        subtitle="Illustrative registry — replace with GET /sites/{site_id}"
      >
        <div className="equipment-grid">
          {[
            ["Net meter", "Bidirectional energy readings", "discom_verified"],
            ["Rooftop PV · 8 kW", "Renewable generation asset", "active"],
            ["Solar inverter", "SunSpec-compatible metadata", "active"],
          ].map(([name, desc, status]) => (
            <div className="equipment" key={name}>
              <span className="equipment-icon">
                <Zap size={23} />
              </span>
              <h3>{name}</h3>
              <p>{desc}</p>
              <Status value={status} />
            </div>
          ))}
        </div>
      </Card>
      <Note>
        When telemetry is stale or unavailable, its quality stays visible.
        Missing measurements must never be displayed as zero generation.
      </Note>
    </>
  );
}
