import { useState, useEffect } from "react";
import {
  Sun,
  TrendingUp,
  Activity,
  RefreshCw,
  Layers,
  ArrowUpRight,
} from "lucide-react";
import { Link } from "react-router-dom";
import { PageHeader, Card, Stat, Tabs, Badge, Note } from "../../components/ui";
import EnergyChart from "../../components/EnergyChart";
import { readConnection, ApiError } from "../../lib/api";
import { localTime } from "../../lib/format";
import { fetchSiteSurplus, type SurplusResponse } from "../energy/energyApi";

export default function ForecastsPage() {
  const [range, setRange] = useState("Today");
  const conn = readConnection();

  const [siteIdInput, setSiteIdInput] = useState(conn.siteId || "");
  const [activeSiteId, setActiveSiteId] = useState(conn.siteId || "");

  const [surplus, setSurplus] = useState<SurplusResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const querySurplus = async (targetId: string) => {
    if (!targetId.trim()) return;
    setLoading(true);
    setError(null);
    try {
      const data = await fetchSiteSurplus(targetId, conn.userId);
      setSurplus(data);
    } catch (err) {
      if (err instanceof ApiError) {
        setError(`${err.message} (${err.code})`);
      } else {
        setError("Unable to load forecast surplus data.");
      }
      setSurplus(null);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (activeSiteId) {
      void querySurplus(activeSiteId);
    }
  }, [activeSiteId]);

  return (
    <>
      <PageHeader
        eyebrow="AHEAD OF THE ENERGY CURVE"
        title="A brighter outlook."
        description="Plan tomorrow’s delivery with generation, demand and exportable surplus."
        action={
          <div style={{ display: "flex", gap: 10 }}>
            <Link className="button primary" to="/market">
              Place day-ahead order <ArrowUpRight size={16} />
            </Link>
          </div>
        }
      />

      {/* Site UUID Selector for Forecast Surplus */}
      <div
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
            Forecast Target:{" "}
            <strong>
              {activeSiteId
                ? `Site (${activeSiteId.slice(0, 8)}…)`
                : "Aarav Residence (Illustrative preview)"}
            </strong>
          </span>
          {surplus && (
            <Badge tone={surplus.has_exportable_energy ? "green" : "amber"}>
              {surplus.has_exportable_energy
                ? "Exportable Surplus"
                : "Deficit Expected"}
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
            {loading ? "Calculating…" : "Query Surplus"}
          </button>
        </form>
      </div>

      {error && (
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
          <strong>Forecast Service:</strong> {error}
        </div>
      )}

      <div className="stats-grid three">
        <Stat
          label="Forecast generation"
          value={surplus ? "Calculated" : "96.4"}
          unit={surplus ? undefined : "kWh"}
          note={
            surplus
              ? `Calculated from ${surplus.points.length} intervals`
              : "Illustrative next-day total"
          }
          icon={<Sun size={20} />}
        />
        <Stat
          label="Exportable surplus"
          value={surplus ? String(surplus.total_exportable_kwh) : "38.2"}
          unit="kWh"
          note={
            surplus
              ? "Available for day-ahead offers"
              : "Illustrative available energy"
          }
          icon={<TrendingUp size={20} />}
        />
        <Stat
          label="Forecast provider"
          value="Baseline"
          note="Statistical provider · replaceable model"
          icon={<Activity size={20} />}
        />
      </div>

      <Card
        title="Tomorrow’s energy profile"
        subtitle="Solar generation vs. community demand · 13 Sep 2026 · Asia/Kolkata (IST)"
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

      <Card
        title="Delivery-window outlook"
        subtitle={
          surplus
            ? `Live surplus calculation · ${surplus.points.length} delivery intervals`
            : "Illustrative forecast · provider: baseline · forecasts are estimates"
        }
      >
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>Delivery window · IST</th>
                <th>Generation</th>
                <th>Demand</th>
                <th>Exportable surplus</th>
                <th>Outlook</th>
              </tr>
            </thead>
            <tbody>
              {surplus && surplus.points.length > 0
                ? surplus.points.slice(0, 10).map((pt, idx) => {
                    const hasExport = Number(pt.exportable_kw) > 0;
                    return (
                      <tr key={idx}>
                        <td>
                          <strong>
                            {localTime(pt.interval_start).replace(" IST", "")} –{" "}
                            {localTime(pt.interval_end)}
                          </strong>
                        </td>
                        <td>{pt.generation_kw ?? "Unavailable"} kW</td>
                        <td>{pt.load_kw ?? "Unavailable"} kW</td>
                        <td>
                          <strong>{pt.exportable_kw} kW</strong>
                        </td>
                        <td>
                          <Badge tone={hasExport ? "green" : "amber"}>
                            {hasExport
                              ? "Surplus expected"
                              : "Deficit expected"}
                          </Badge>
                        </td>
                      </tr>
                    );
                  })
                : [
                    ["06:00–09:00", "8.4", "12.1", "0.0", "Deficit expected"],
                    ["09:00–12:00", "28.6", "13.4", "15.2", "Surplus expected"],
                    ["12:00–15:00", "36.2", "17.0", "19.2", "Surplus expected"],
                    ["15:00–18:00", "23.2", "19.4", "3.8", "Surplus expected"],
                  ].map((r) => (
                    <tr key={r[0]}>
                      <td>
                        <strong>13 Sep · {r[0]}</strong>
                      </td>
                      {r.slice(1, 4).map((v, i) => (
                        <td key={i}>{v} kWh</td>
                      ))}
                      <td>
                        <Badge
                          tone={r[4].startsWith("Deficit") ? "amber" : "green"}
                        >
                          {r[4]}
                        </Badge>
                      </td>
                    </tr>
                  ))}
            </tbody>
          </table>
        </div>
      </Card>

      <Note>
        <strong>Estimates Only:</strong> Forecasts are produced by the baseline
        forecasting service using historical AMI telemetry and weather data.
        Forecasted surplus informs day-ahead order validation, but actual
        delivery is verified by meter readings during reconciliation.
      </Note>
    </>
  );
}
