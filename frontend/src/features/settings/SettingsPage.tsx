import { useEffect, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Plug, RefreshCw, Save, Activity, Radio, Database } from "lucide-react";
import { PageHeader, Card, Note, Badge } from "../../components/ui";
import { readConnection, request, subscribe, ApiError } from "../../lib/api";

const uuid =
  "[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}";

interface ExtendedConnection {
  userId: string;
  siteId: string;
  sessionId: string;
  meterId: string;
}

export default function SettingsPage() {
  const [config, setConfig] = useState<ExtendedConnection>(() => {
    const raw = readConnection();
    let meterId = "";
    try {
      const stored = JSON.parse(
        localStorage.getItem("urjasetu.connection") || "{}",
      );
      meterId = stored.meterId || "";
    } catch {
      // fallback
    }
    return {
      userId: raw.userId || "",
      siteId: raw.siteId || "",
      sessionId: raw.sessionId || "",
      meterId,
    };
  });

  const [saved, setSaved] = useState(false);
  const [kind, setKind] = useState("Site");
  const [id, setId] = useState("");
  const [lookup, setLookup] = useState("");
  const [channel, setChannel] = useState<"market" | "grid" | "telemetry">(
    "market",
  );
  const [listening, setListening] = useState(false);
  const [stream, setStream] = useState("Disconnected");

  // Latencies for endpoints
  const [healthLatency, setHealthLatency] = useState<number | null>(null);
  const [readyLatency, setReadyLatency] = useState<number | null>(null);

  const qc = useQueryClient();

  const health = useQuery({
    queryKey: ["health"],
    queryFn: async ({ signal }) => {
      const start = performance.now();
      try {
        const res = await request<{ status: string }>("/health", "", signal);
        setHealthLatency(Math.round(performance.now() - start));
        return res;
      } catch (e) {
        setHealthLatency(Math.round(performance.now() - start));
        throw e;
      }
    },
    enabled: false,
    retry: false,
  });

  const readiness = useQuery({
    queryKey: ["health-ready"],
    queryFn: async ({ signal }) => {
      const start = performance.now();
      try {
        const res = await request<{ status: string }>(
          "/health/ready",
          "",
          signal,
        );
        setReadyLatency(Math.round(performance.now() - start));
        return res;
      } catch (e) {
        setReadyLatency(Math.round(performance.now() - start));
        throw e;
      }
    },
    enabled: false,
    retry: false,
  });

  interface MetaInfo {
    app: string;
    version: string;
    api_version: string;
    environment: string;
    market_mode: string;
    enabled_integrations: string[];
  }

  const meta = useQuery({
    queryKey: ["meta"],
    queryFn: ({ signal }) => request<MetaInfo>("/api/v1/meta", "", signal),
    enabled: false,
    retry: false,
  });

  const record = useQuery({
    queryKey: ["record", lookup, config.userId],
    queryFn: ({ signal }) => request(lookup, config.userId, signal),
    enabled: !!lookup,
    retry: false,
  });

  useEffect(() => {
    if (!listening || !config.userId) return;
    return subscribe(
      channel,
      config.userId,
      () => {
        void qc.invalidateQueries({ queryKey: ["record"] });
      },
      setStream,
    );
  }, [listening, channel, config.userId, qc]);

  return (
    <>
      <PageHeader
        eyebrow="MAKE IT YOUR WORKSPACE"
        title="Connection & preferences"
        description="Connect to existing backend records without changing the backend."
      />
      <div className="two-col reveal-1">
        <Card
          title="Backend connection & health probes"
          subtitle="Read-only connectivity check · /health & /health/ready"
        >
          <div className="connection-icon">
            <Plug size={28} />
            <div>
              <strong>UrjaSetu API Gateway</strong>
              <p>Same-origin proxy · /api/v1</p>
            </div>
          </div>

          <div style={{ display: "flex", gap: 10, margin: "14px 0 10px" }}>
            <button
              className="button secondary"
              disabled={health.isFetching}
              onClick={() => {
                void health.refetch();
                void readiness.refetch();
                void meta.refetch();
              }}
            >
              <RefreshCw
                size={15}
                className={health.isFetching ? "spin" : ""}
              />
              {health.isFetching ? "Checking…" : "Check API health"}
            </button>
          </div>

          <div role="status">
            {meta.isSuccess && meta.data && (
              <div
                style={{
                  margin: "8px 0 12px",
                  padding: "8px 12px",
                  background: "#f0fdf4",
                  borderRadius: 6,
                  border: "1px solid #bbf7d0",
                  fontSize: 11,
                }}
              >
                <div
                  style={{
                    display: "flex",
                    justifyContent: "space-between",
                    alignItems: "center",
                    marginBottom: 4,
                  }}
                >
                  <span style={{ fontWeight: 600, color: "#166534" }}>
                    {meta.data.app} v{meta.data.version} (
                    {meta.data.api_version})
                  </span>
                  <Badge tone="green">
                    {meta.data.environment.toUpperCase()}
                  </Badge>
                </div>
                <div
                  style={{
                    display: "flex",
                    justifyContent: "space-between",
                    color: "#1e293b",
                    marginBottom: 4,
                  }}
                >
                  <span>Market Mode:</span>
                  <strong>{meta.data.market_mode}</strong>
                </div>
                <div
                  style={{
                    display: "flex",
                    justifyContent: "space-between",
                    color: "#64748b",
                  }}
                >
                  <span>Active Integrations:</span>
                  <span>
                    {meta.data.enabled_integrations &&
                    meta.data.enabled_integrations.length > 0
                      ? meta.data.enabled_integrations.join(", ")
                      : "Local Simulation / Baseline"}
                  </span>
                </div>
              </div>
            )}
            {health.isSuccess && (
              <div style={{ margin: "10px 0" }}>
                <div
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: 8,
                    marginBottom: 6,
                  }}
                >
                  <Activity size={16} color="#15803d" />
                  <span
                    style={{ fontSize: 12, fontWeight: 600, color: "#166534" }}
                  >
                    API Liveness: 200 OK
                  </span>
                  {healthLatency !== null && (
                    <Badge tone="green">{healthLatency} ms</Badge>
                  )}
                </div>
                <Note>
                  API process responded. This verifies HTTP routing and process
                  availability.
                </Note>
              </div>
            )}

            {readiness.isSuccess && (
              <div style={{ margin: "8px 0" }}>
                <div
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: 8,
                    marginBottom: 4,
                  }}
                >
                  <Database size={16} color="#15803d" />
                  <span
                    style={{ fontSize: 12, fontWeight: 600, color: "#166534" }}
                  >
                    Database Readiness: Healthy
                  </span>
                  {readyLatency !== null && (
                    <Badge tone="green">{readyLatency} ms</Badge>
                  )}
                </div>
              </div>
            )}

            {health.isError && (
              <p className="error-text">
                Connection failed: {health.error.message}
              </p>
            )}

            {readiness.isError && (
              <p className="error-text" style={{ fontSize: 11, marginTop: 4 }}>
                Readiness check note: {readiness.error.message}
              </p>
            )}
          </div>

          <Note>
            All design pages remain explicitly illustrative. This workspace
            displays real API responses separately.
          </Note>
        </Card>

        <Card
          title="Prototype identity"
          subtitle="Opaque IDs only · saved in this browser"
        >
          <form
            onSubmit={(e) => {
              e.preventDefault();
              localStorage.setItem(
                "urjasetu.connection",
                JSON.stringify(config),
              );
              setSaved(true);
            }}
          >
            {(
              [
                ["userId", "User UUID"],
                ["siteId", "Site UUID"],
                ["sessionId", "Market session UUID"],
                ["meterId", "Meter UUID"],
              ] as const
            ).map(([key, label]) => (
              <label key={key}>
                {label}
                <input
                  pattern={uuid}
                  placeholder="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
                  value={config[key] || ""}
                  onChange={(e) => {
                    setConfig({ ...config, [key]: e.target.value });
                    setSaved(false);
                  }}
                />
              </label>
            ))}
            <button className="button primary" type="submit">
              <Save size={15} /> Save connection IDs
            </button>
            {saved && (
              <p role="status" className="success-text">
                Connection IDs saved.
              </p>
            )}
          </form>
        </Card>
      </div>

      <Card
        className="reveal-2"
        title="Read an existing record"
        subtitle="Uses implemented GET endpoints only. Enter a real resource UUID."
      >
        <form
          className="lookup-form"
          onSubmit={(e) => {
            e.preventDefault();
            const value = encodeURIComponent(id);
            const paths: Record<string, string> = {
              Site: `/sites/${value}`,
              User: `/users/${value}`,
              Eligibility: `/users/${value}/eligibility`,
              Order: `/orders/${value}`,
              Trade: `/trades/${value}`,
              Settlement: `/settlements/${value}`,
              "User settlements": `/users/${value}/settlements`,
              "Latest telemetry": `/sites/${value}/telemetry/latest`,
              "Site forecasts": `/sites/${value}/forecasts`,
              "Site surplus": `/sites/${value}/surplus`,
              "Order book": `/market/order-book?session_id=${value}`,
              "Trade audit": `/audit/entities/trade/${value}`,
              "Asset verification": `/assets/${value}/verification`,
              "System metadata": `/meta`,
            };
            const path = "/api/v1" + paths[kind];
            if (path === lookup) void record.refetch();
            else setLookup(path);
          }}
        >
          <label>
            Resource
            <select value={kind} onChange={(e) => setKind(e.target.value)}>
              {[
                "Site",
                "User",
                "Eligibility",
                "Order",
                "Trade",
                "Settlement",
                "User settlements",
                "Latest telemetry",
                "Site forecasts",
                "Site surplus",
                "Order book",
                "Trade audit",
                "Asset verification",
                "System metadata",
              ].map((k) => (
                <option key={k}>{k}</option>
              ))}
            </select>
          </label>
          <label>
            Resource UUID
            <input
              required={kind !== "System metadata"}
              pattern={kind === "System metadata" ? undefined : uuid}
              value={id}
              onChange={(e) => setId(e.target.value)}
              placeholder={
                kind === "System metadata"
                  ? "Not required for /meta"
                  : "Enter an existing UUID"
              }
            />
          </label>
          <button
            className="button primary"
            type="submit"
            disabled={record.isFetching}
          >
            {record.isFetching ? "Loading…" : "Load record"}
          </button>
        </form>
        {record.isError && (
          <div role="alert" className="note error-text">
            {record.error.message}
            {record.error instanceof ApiError && (
              <small>
                {record.error.code}{" "}
                {record.error.requestId &&
                  `· Request ${record.error.requestId}`}
              </small>
            )}
          </div>
        )}
        {record.isSuccess && !record.isError && (
          <pre className="json-result">
            {JSON.stringify(record.data, null, 2)}
          </pre>
        )}
        {!lookup && (
          <p className="empty">
            Select a resource to inspect its authoritative API response.
          </p>
        )}
      </Card>

      <Card
        className="reveal-3"
        title="Realtime notifications & WebSocket gateway"
        subtitle="Optional connection · incoming broadcast messages trigger a local state refresh"
      >
        <div className="stream-controls">
          <label>
            Channel
            <select
              value={channel}
              onChange={(e) => setChannel(e.target.value as typeof channel)}
            >
              <option>market</option>
              <option>grid</option>
              <option>telemetry</option>
            </select>
          </label>
          <button
            className="button secondary"
            disabled={!new RegExp(`^${uuid}$`).test(config.userId)}
            onClick={() => {
              setListening(!listening);
              if (listening) setStream("Disconnected");
            }}
          >
            {listening ? "Disconnect" : "Connect stream"}
          </button>
          <Badge tone={stream === "Connected" ? "green" : "neutral"}>
            <Radio size={12} style={{ marginRight: 4 }} />
            {stream}
          </Badge>
        </div>
        <Note>
          An active backend user UUID is required to subscribe to peer channels.
          WebSocket reconnects automatically with exponential backoff on drop.
        </Note>
      </Card>
    </>
  );
}
