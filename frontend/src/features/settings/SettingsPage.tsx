import { useEffect, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Plug, RefreshCw, Save } from "lucide-react";
import { PageHeader, Card, Note, Badge } from "../../components/ui";
import { readConnection, request, subscribe, ApiError } from "../../lib/api";
const uuid =
  "[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}";
export default function SettingsPage() {
  const [config, setConfig] = useState(readConnection);
  const [saved, setSaved] = useState(false);
  const [kind, setKind] = useState("Site");
  const [id, setId] = useState("");
  const [lookup, setLookup] = useState("");
  const [channel, setChannel] = useState<"market" | "grid" | "telemetry">(
    "market",
  );
  const [listening, setListening] = useState(false);
  const [stream, setStream] = useState("Disconnected");
  const qc = useQueryClient();
  const health = useQuery({
    queryKey: ["health"],
    queryFn: ({ signal }) => request("/health", "", signal),
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
      <div className="two-col">
        <Card
          title="Backend connection"
          subtitle="Read-only connectivity check"
        >
          <div className="connection-icon">
            <Plug size={28} />
            <div>
              <strong>UrjaSetu API</strong>
              <p>Same-origin proxy · /api/v1</p>
            </div>
          </div>
          <button
            className="button secondary"
            disabled={health.isFetching}
            onClick={() => void health.refetch()}
          >
            <RefreshCw size={15} />
            {health.isFetching ? "Checking…" : "Check API health"}
          </button>
          <div role="status">
            {health.isSuccess && (
              <Note>
                API process responded. This does not verify database readiness
                or feature availability.
              </Note>
            )}
            {health.isError && (
              <p className="error-text">
                Connection failed: {health.error.message}
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
            {(["userId", "siteId", "sessionId"] as const).map((key) => (
              <label key={key}>
                {key === "userId"
                  ? "User UUID"
                  : key === "siteId"
                    ? "Site UUID"
                    : "Market session UUID"}
                <input
                  pattern={uuid}
                  placeholder="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
                  value={config[key]}
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
              "Order book": `/market/order-book?session_id=${value}`,
              "Trade audit": `/audit/entities/trade/${value}`,
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
                "Order book",
                "Trade audit",
              ].map((k) => (
                <option key={k}>{k}</option>
              ))}
            </select>
          </label>
          <label>
            Resource UUID
            <input
              required
              pattern={uuid}
              value={id}
              onChange={(e) => setId(e.target.value)}
              placeholder="Enter an existing UUID"
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
        title="Realtime notifications"
        subtitle="Optional connection · notifications trigger a REST refetch"
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
            {stream}
          </Badge>
        </div>
        <Note>
          An active backend user UUID is required. Prototype identity headers
          are not a production sign-in system.
        </Note>
      </Card>
    </>
  );
}
