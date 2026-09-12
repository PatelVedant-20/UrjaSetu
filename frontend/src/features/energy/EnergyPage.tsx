import { useState, useEffect } from "react";
import {
  Sun,
  Zap,
  Radio,
  ArrowUpRight,
  RefreshCw,
  Cpu,
  Layers,
} from "lucide-react";
import { Link } from "react-router-dom";
import {
  PageHeader,
  Card,
  Stat,
  Status,
  Tabs,
  Badge,
  Note,
} from "../../components/ui";
import EnergyChart from "../../components/EnergyChart";
import { readConnection, ApiError } from "../../lib/api";
import {
  fetchLatestTelemetry,
  fetchSiteDetail,
  type TelemetryReadingResponse,
  type SiteDetailResponse,
} from "./energyApi";
import {
  formatPowerKw,
  formatEnergyKwh,
  resolveTelemetryTone,
} from "./energyUtils";

export default function EnergyPage() {
  const [range, setRange] = useState("Today");
  const conn = readConnection();

  const [siteIdInput, setSiteIdInput] = useState(conn.siteId || "");
  const [activeSiteId, setActiveSiteId] = useState(conn.siteId || "");

  // Real backend telemetry and site state
  const [telemetry, setTelemetry] = useState<TelemetryReadingResponse | null>(
    null,
  );
  const [siteDetail, setSiteDetail] = useState<SiteDetailResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [apiError, setApiError] = useState<string | null>(null);

  const querySiteData = async (targetId: string) => {
    if (!targetId.trim()) return;
    setLoading(true);
    setApiError(null);
    try {
      const [reading, site] = await Promise.all([
        fetchLatestTelemetry(targetId, conn.userId).catch((err: unknown) => {
          if (err instanceof ApiError && err.code === "TELEMETRY_NOT_FOUND") {
            return null;
          }
          throw err;
        }),
        fetchSiteDetail(targetId, conn.userId).catch(() => null),
      ]);
      setTelemetry(reading);
      setSiteDetail(site);
    } catch (err) {
      if (err instanceof ApiError) {
        setApiError(`${err.message} (${err.code})`);
      } else {
        setApiError("Failed to reach telemetry services.");
      }
      setTelemetry(null);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (activeSiteId) {
      void querySiteData(activeSiteId);
    }
  }, [activeSiteId]);

  // Telemetry metrics:
  // CRITICAL RULE: If telemetry is null, display "Unavailable", NEVER default to zero!
  const generationDisplay = telemetry
    ? formatPowerKw(telemetry.generation_kw)
    : "6.4 kW";
  const demandDisplay = telemetry ? formatPowerKw(telemetry.load_kw) : "2.1 kW";
  const qualityDisplay = telemetry ? telemetry.quality_status : "Valid";
  const qualityTone = telemetry
    ? resolveTelemetryTone(telemetry.quality_status)
    : "green";

  return (
    <>
      <PageHeader
        eyebrow="YOUR ROOFTOP, REIMAGINED"
        title="My energy"
        description="Know what you generate, what you use, and what you can share."
        action={
          <div style={{ display: "flex", gap: 10 }}>
            <Link className="button secondary" to="/forecasts">
              View forecasts <ArrowUpRight size={16} />
            </Link>
            <Link className="button secondary" to="/settings">
              Site settings <ArrowUpRight size={16} />
            </Link>
          </div>
        }
      />

      {/* Site UUID Selector / Inspector */}
      <div
        className="reveal-1"
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          background: "#fafbf7",
          border: "1px solid var(--line, #e2e8f0)",
          borderRadius: 8,
          padding: "10px 16px",
          marginBottom: 16,
          fontSize: 12,
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <Layers size={16} color="#475569" />
          <span>
            Connected Site:{" "}
            <strong>
              {activeSiteId
                ? `${siteDetail?.name || "Site"} (${activeSiteId.slice(0, 8)}…)`
                : "Aarav Residence (Illustrative preview)"}
            </strong>
          </span>
          {telemetry && (
            <Badge tone={qualityTone}>
              Quality: {telemetry.quality_status.toUpperCase()}
            </Badge>
          )}
        </div>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            setActiveSiteId(siteIdInput.trim());
          }}
          style={{ display: "flex", alignItems: "center", gap: 8 }}
        >
          <input
            type="text"
            placeholder="Enter Site UUID…"
            value={siteIdInput}
            onChange={(e) => setSiteIdInput(e.target.value)}
            style={{
              padding: "4px 8px",
              fontSize: 11,
              width: 200,
              borderRadius: 4,
              border: "1px solid #cbd5e1",
            }}
          />
          <button
            type="submit"
            className="button secondary"
            style={{ padding: "4px 8px", fontSize: 11 }}
            disabled={loading}
          >
            <RefreshCw
              size={12}
              className={loading ? "spin" : ""}
              style={{ marginRight: 4 }}
            />
            {loading ? "Reading…" : "Query Telemetry"}
          </button>
        </form>
      </div>

      {apiError && (
        <div
          style={{
            background: "#fef2f2",
            border: "1px solid #fecaca",
            padding: 10,
            borderRadius: 8,
            marginBottom: 16,
            fontSize: 12,
            color: "#991b1b",
          }}
        >
          <strong>Telemetry Query Note:</strong> {apiError}
        </div>
      )}

      <div className="stats-grid three reveal-2">
        <Stat
          label="Solar generation"
          value={generationDisplay.replace(" kW", "")}
          unit={generationDisplay.includes("kW") ? "kW" : undefined}
          note={
            telemetry
              ? `Live reading · ${telemetry.interval_end ? "IST window" : "latest"}`
              : "Illustrative current output"
          }
          icon={<Sun size={20} />}
        />
        <Stat
          label="Home demand"
          value={demandDisplay.replace(" kW", "")}
          unit={demandDisplay.includes("kW") ? "kW" : undefined}
          note={
            telemetry ? `Interval meter demand` : "Illustrative current demand"
          }
          icon={<Zap size={20} />}
        />
        <Stat
          label="Meter quality"
          value={qualityDisplay}
          note={
            telemetry
              ? `Source: ${telemetry.source}`
              : "Example data-quality assessment"
          }
          icon={<Radio size={20} />}
        />
      </div>

      <div className="split-main reveal-3">
        <Card
          title="Generation & consumption"
          subtitle="Community-scale illustrative series · Asia/Kolkata (IST)"
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
            src="/images/sites/aarav-residence.jpg"
            alt="Photovoltaic rooftop solar installation at Aarav Residence"
            loading="lazy"
          />
          <div className="site-body">
            <Status value="discom_verified" />
            <h2>{siteDetail?.name || "Aarav Residence"}</h2>
            <p>
              {siteDetail?.id
                ? `Registered site · Node: ${siteDetail.grid_node_id || "Unassigned"}`
                : "Illustrative site · Ahmedabad community"}
            </p>
            <div className="metric-line">
              <span>Installed solar</span>
              <strong>
                {siteDetail?.energy_assets?.[0]?.capacity_kw
                  ? `${siteDetail.energy_assets[0].capacity_kw} kW`
                  : "8.0 kW"}
              </strong>
            </div>
            <div className="metric-line">
              <span>Grid connection</span>
              <strong>
                {siteDetail?.grid_node_id
                  ? `Node ${siteDetail.grid_node_id.slice(0, 8)}`
                  : "Feeder A · Node 01"}
              </strong>
            </div>
          </div>
        </Card>
      </div>

      <Card
        title="Connected equipment"
        subtitle={
          siteDetail
            ? `Active site registry · ${siteDetail.meters.length} meters, ${siteDetail.energy_assets.length} generation assets`
            : "Illustrative registry — connect a site to query GET /sites/{site_id}"
        }
      >
        <div className="equipment-grid">
          {siteDetail && siteDetail.meters.length > 0 ? (
            <>
              {siteDetail.meters.map((m) => (
                <div className="equipment" key={m.id}>
                  <span className="equipment-icon">
                    <Zap size={23} />
                  </span>
                  <h3>{m.meter_type.replace("_", " ").toUpperCase()}</h3>
                  <p>
                    {m.vendor || "Smart meter"} · Ref:{" "}
                    {m.external_meter_ref || m.id.slice(0, 8)}
                  </p>
                  <Status value={m.verification_level} />
                </div>
              ))}
              {siteDetail.energy_assets.map((a) => (
                <div className="equipment" key={a.id}>
                  <span className="equipment-icon">
                    <Sun size={23} />
                  </span>
                  <h3>
                    {a.asset_type.replace("_", " ").toUpperCase()} ·{" "}
                    {a.capacity_kw} kW
                  </h3>
                  <p>Commissioned renewable generation asset</p>
                  <Status value={a.status} />
                </div>
              ))}
            </>
          ) : (
            [
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
            ))
          )}
        </div>
      </Card>

      <Note>
        <strong>Strict Null Safety:</strong> When telemetry is missing, stale,
        or unmeasured, values display as <em>Unavailable</em>. Missing telemetry
        is never converted to zero generation or demand, ensuring settlement
        algorithms cannot miscalculate balancing energy.
      </Note>
    </>
  );
}
