import { useState } from "react";
import { Search } from "lucide-react";
import { PageHeader, Card, Status, Modal, Note } from "../../components/ui";
import { members } from "../../lib/demo";
export default function CommunityPage() {
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState<(typeof members)[number] | null>(
    null,
  );
  const filtered = members.filter((m) =>
    `${m.name} ${m.role}`.toLowerCase().includes(query.toLowerCase()),
  );
  return (
    <>
      <PageHeader
        eyebrow="POWERED BY PEOPLE"
        title="Your energy neighborhood."
        description="Meet the homes and shared spaces making local renewable energy possible."
      />
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
