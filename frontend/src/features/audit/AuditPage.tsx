import { useState } from "react";
import { Search, Check, ArrowUpRight } from "lucide-react";
import { Link } from "react-router-dom";
import { PageHeader, Card, Badge, Modal, Note } from "../../components/ui";
import { auditEvents } from "../../lib/demo";
export default function AuditPage() {
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState<(typeof auditEvents)[number] | null>(
    null,
  );
  const filtered = auditEvents.filter((e) =>
    `${e.title} ${e.entity} ${e.type}`
      .toLowerCase()
      .includes(query.toLowerCase()),
  );
  return (
    <>
      <PageHeader
        eyebrow="THE STORY BEHIND EVERY DECISION"
        title="An open trail."
        description="Follow a trade from its first proposal to its final settlement."
        action={
          <Link to="/settings" className="button secondary">
            Look up API records <ArrowUpRight size={16} />
          </Link>
        }
      />
      <Card
        title="Trade event timeline"
        subtitle="Illustrative history · TR-2046"
        action={
          <label className="search-field">
            <Search size={16} />
            <input
              aria-label="Search audit events"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search events…"
            />
          </label>
        }
      >
        <div className="timeline">
          {filtered.map((e) => (
            <button
              className="timeline-event"
              key={e.type}
              onClick={() => setSelected(e)}
            >
              <span className="timeline-marker">
                <Check size={15} />
              </span>
              <div>
                <small>{e.time}</small>
                <h3>{e.title}</h3>
                <p>{e.detail}</p>
                <Badge tone="neutral">{e.entity}</Badge>
              </div>
              <ArrowUpRight size={17} />
            </button>
          ))}
        </div>
        {!filtered.length && <p className="empty">No matching audit events.</p>}
      </Card>
      <Note>
        The backend stores a hash-linked audit trail. This preview does not
        verify integrity or claim a blockchain anchor. Real audit access
        requires an authorized identity.
      </Note>
      {selected && (
        <Modal title={selected.title} onClose={() => setSelected(null)}>
          <Badge tone="neutral">ILLUSTRATIVE EVENT</Badge>
          <p className="body-copy">{selected.detail}</p>
          <div className="simple-list">
            <div>
              <span>Event type</span>
              <code>{selected.type}</code>
            </div>
            <div>
              <span>Entity</span>
              <strong>{selected.entity}</strong>
            </div>
            <div>
              <span>Occurred</span>
              <strong>{selected.time}</strong>
            </div>
          </div>
        </Modal>
      )}
    </>
  );
}
