import { useState } from "react";
import { Search, RefreshCw, Layers, ShieldCheck, User } from "lucide-react";
import {
  PageHeader,
  Card,
  Status,
  Modal,
  Note,
  Badge,
} from "../../components/ui";
import { members as demoMembers } from "../../lib/demo";
import { readConnection, ApiError } from "../../lib/api";
import {
  fetchUserById,
  fetchUserEligibility,
  type UserResponse,
  type UserEligibilityResponse,
} from "../energy/energyApi";

export default function CommunityPage() {
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState<(typeof demoMembers)[number] | null>(
    null,
  );

  // Live user lookup
  const conn = readConnection();
  const [lookupUserId, setLookupUserId] = useState(conn.userId || "");
  const [liveUser, setLiveUser] = useState<UserResponse | null>(null);
  const [liveEligibility, setLiveEligibility] =
    useState<UserEligibilityResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleLookup = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!lookupUserId.trim()) return;
    setLoading(true);
    setError(null);
    try {
      const [u, el] = await Promise.all([
        fetchUserById(lookupUserId.trim()),
        fetchUserEligibility(lookupUserId.trim()).catch(() => null),
      ]);
      setLiveUser(u);
      setLiveEligibility(el);
    } catch (err) {
      if (err instanceof ApiError) {
        setError(`${err.message} (${err.code})`);
      } else {
        setError("Failed to load user record.");
      }
      setLiveUser(null);
      setLiveEligibility(null);
    } finally {
      setLoading(false);
    }
  };

  const filtered = demoMembers.filter((m) =>
    `${m.name} ${m.role}`.toLowerCase().includes(query.toLowerCase()),
  );

  const handleCardMouseMove = (e: React.MouseEvent<HTMLButtonElement>) => {
    const card = e.currentTarget;
    const rect = card.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const y = e.clientY - rect.top;
    const centerX = rect.width / 2;
    const centerY = rect.height / 2;
    const rotateX = ((y - centerY) / centerY) * -5;
    const rotateY = ((x - centerX) / centerX) * 5;

    card.style.transform = `perspective(800px) rotateX(${rotateX.toFixed(2)}deg) rotateY(${rotateY.toFixed(2)}deg) translateY(-2px)`;
    card.style.setProperty("--glow-x", `${x}px`);
    card.style.setProperty("--glow-y", `${y}px`);
  };

  const handleCardMouseLeave = (e: React.MouseEvent<HTMLButtonElement>) => {
    e.currentTarget.style.transform = "";
  };

  return (
    <>
      <PageHeader
        eyebrow="POWERED BY PEOPLE"
        title="Your energy neighborhood."
        description="Meet the homes and shared spaces making local renewable energy possible."
      />

      {/* Live User Lookup Bar */}
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
            Lookup Backend Identity: <strong>GET /api/v1/users/:id</strong>
          </span>
        </div>
        <form
          onSubmit={handleLookup}
          style={{ display: "flex", alignItems: "center", gap: 8 }}
        >
          <input
            type="text"
            placeholder="Enter User UUID…"
            value={lookupUserId}
            onChange={(e) => setLookupUserId(e.target.value)}
            style={{
              padding: "4px 8px",
              fontSize: 11,
              width: 210,
              borderRadius: 4,
              border: "1px solid #cbd5e1",
            }}
          />
          <button
            type="submit"
            className="button secondary"
            style={{ padding: "4px 8px", fontSize: 11 }}
            disabled={loading || !lookupUserId.trim()}
          >
            {loading ? (
              <RefreshCw
                size={12}
                className="spin"
                style={{ marginRight: 4 }}
              />
            ) : (
              <Search size={12} style={{ marginRight: 4 }} />
            )}
            {loading ? "Checking…" : "Lookup"}
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
          <strong>User Lookup Error:</strong> {error}
        </div>
      )}

      {liveUser && (
        <div
          style={{
            background: "#f0fdf4",
            border: "1px solid #bbf7d0",
            borderRadius: 8,
            padding: "14px 18px",
            marginBottom: 16,
          }}
        >
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: 8,
              marginBottom: 8,
            }}
          >
            <User size={18} color="#16a34a" />
            <strong style={{ fontSize: 14 }}>{liveUser.display_name}</strong>
            <Badge tone="green">{liveUser.role.toUpperCase()}</Badge>
            <Status value={liveUser.status} />
          </div>
          <div className="simple-list" style={{ padding: 0 }}>
            <div>
              <span>User UUID</span>
              <code style={{ fontSize: 11 }}>{liveUser.id}</code>
            </div>
            {liveUser.email && (
              <div>
                <span>Email</span>
                <strong>{liveUser.email}</strong>
              </div>
            )}
            {liveEligibility && (
              <div>
                <span>Trading Eligibility</span>
                <div>
                  <Badge tone={liveEligibility.can_buy ? "green" : "neutral"}>
                    {liveEligibility.can_buy ? "Can Buy" : "Buy Restricted"}
                  </Badge>
                  <span style={{ margin: "0 4px" }} />
                  <Badge tone={liveEligibility.can_sell ? "green" : "neutral"}>
                    {liveEligibility.can_sell ? "Can Sell" : "Sell Restricted"}
                  </Badge>
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      <Card
        title="Community directory"
        subtitle="Six illustrative members · Ahmedabad demo community"
        action={
          <label className="search-field">
            <Search size={16} />
            <input
              aria-label="Search community"
              placeholder="Search members…"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
            />
          </label>
        }
      >
        <div className="member-grid">
          {filtered.map((m) => (
            <button
              className="member-card"
              key={m.name}
              onClick={() => setSelected(m)}
              onMouseMove={handleCardMouseMove}
              onMouseLeave={handleCardMouseLeave}
            >
              <span className="avatar large">{m.initials}</span>
              <span className="member-role">{m.role}</span>
              <h3>{m.name}</h3>
              <p>
                {m.capacity === "—"
                  ? "Community energy consumer"
                  : `${m.capacity} rooftop solar`}
              </p>
              <Status value={m.status} />
              <span className="member-link">View profile ↗</span>
            </button>
          ))}
        </div>
        {!filtered.length && (
          <p className="empty">
            No members found. Try a different name or role.
          </p>
        )}
      </Card>

      {selected && (
        <Modal title={selected.name} onClose={() => setSelected(null)}>
          <Status value={selected.status} />
          <p className="body-copy">
            {selected.role} · {selected.capacity} installed capacity
          </p>
          <h3>Participation checklist</h3>
          <div className="simple-list">
            <div>
              <span>Identity & utility verification</span>
              <Status value={selected.status} />
            </div>
            <div>
              <span>Meter-data consent</span>
              <span>Requires backend check</span>
            </div>
            <div>
              <span>Trading eligibility</span>
              <span>Requires backend check</span>
            </div>
          </div>
          <Note>
            Verification labels here are illustrative. Only the backend
            eligibility endpoint can determine whether a user may buy or sell.
          </Note>
        </Modal>
      )}
    </>
  );
}
