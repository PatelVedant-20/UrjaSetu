import { useState } from "react";
import {
  PageHeader,
  Card,
  Tabs,
  Modal,
  Status,
  Note,
} from "../../components/ui";
import TradeTable from "../../components/TradeTable";
import { trades } from "../../lib/demo";
import { money } from "../../lib/format";
export default function TradesPage() {
  const [filter, setFilter] = useState("All");
  const [selected, setSelected] = useState<(typeof trades)[number] | null>(
    null,
  );
  return (
    <>
      <PageHeader
        eyebrow="YOUR MARKET ACTIVITY"
        title="Every trade, in view."
        description="Follow proposals, delivery windows and final outcomes in one place."
      />
      <Card
        title="Trade history"
        subtitle="Illustrative community trades"
        action={
          <Tabs
            items={["All", "Proposed", "Settled", "Rejected"]}
            value={filter}
            onChange={setFilter}
          />
        }
      >
        <TradeTable
          rows={trades.filter(
            (t) => filter === "All" || t.status === filter.toLowerCase(),
          )}
          onSelect={setSelected}
        />
      </Card>
      <Note>
        Matching creates a proposal. Grid validation, pricing and commitment
        must complete before a trade can move toward delivery and settlement.
      </Note>
      {selected && (
        <Modal title={`Trade ${selected.id}`} onClose={() => setSelected(null)}>
          <Status value={selected.status} />
          <h3>{selected.name}</h3>
          <div className="simple-list">
            <div>
              <span>Delivery window</span>
              <strong>{selected.window}</strong>
            </div>
            <div>
              <span>Energy</span>
              <strong>{selected.energy} kWh</strong>
            </div>
            <div>
              <span>Price</span>
              <strong>{money(selected.price)}/kWh</strong>
            </div>
          </div>
          <Note>
            This is an illustrative record. Approval and grid-validation
            controls require backend routes that are not currently mounted.
          </Note>
        </Modal>
      )}
    </>
  );
}
