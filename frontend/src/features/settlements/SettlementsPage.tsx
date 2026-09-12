import { useState } from "react";
import { Download, Wallet, CheckCheck } from "lucide-react";
import {
  PageHeader,
  Card,
  Stat,
  Modal,
  Badge,
  Note,
} from "../../components/ui";
import { money, exportCsv } from "../../lib/format";
const rows = [
  {
    id: "ST-1046",
    trade: "TR-2046",
    date: "11 Sep 2026",
    energy: 8.2,
    gross: 36.49,
    fee: 0.73,
    balancing: 0,
    credit: 35.76,
    debit: 36.49,
  },
  {
    id: "ST-1044",
    trade: "TR-2044",
    date: "10 Sep 2026",
    energy: 10,
    gross: 47,
    fee: 0.94,
    balancing: 0,
    credit: 46.06,
    debit: 47,
  },
];
export default function SettlementsPage() {
  const [selected, setSelected] = useState<(typeof rows)[number] | null>(null);
  return (
    <>
      <PageHeader
        eyebrow="CLEAR ACCOUNTS. COMPLETE CONFIDENCE."
        title="Settlements"
        description="See how measured delivery becomes an auditable financial record."
        action={
          <button
            className="button secondary"
            onClick={() =>
              exportCsv(rows, "urjasetu-illustrative-settlements.csv")
            }
          >
            <Download size={16} /> Export demo CSV
          </button>
        }
      />
      <div className="stats-grid three">
        <Stat
          label="Illustrative seller credits"
          value="₹81.82"
          note="Sample settled records"
          icon={<Wallet size={20} />}
        />
        <Stat
          label="Settled energy"
          value="18.2"
          unit="kWh"
          note="Measured delivery in demo records"
          icon={<CheckCheck size={20} />}
        />
        <Stat
          label="Balancing charges"
          value="₹0.00"
          note="No shortfall in these examples"
          icon={<Wallet size={20} />}
        />
      </div>
      <Card
        title="Settlement history"
        subtitle="Illustrative accounting · not a wallet or payment service"
      >
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>Settlement</th>
                <th>Delivered energy</th>
                <th>Seller credit</th>
                <th>Status</th>
                <th>Details</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.id}>
                  <td>
                    <strong>{r.id}</strong>
                    <small>
                      {r.trade} · {r.date}
                    </small>
                  </td>
                  <td>{r.energy} kWh</td>
                  <td>{money(r.credit)}</td>
                  <td>
                    <Badge>Settled</Badge>
                  </td>
                  <td>
                    <button
                      className="text-button"
                      onClick={() => setSelected(r)}
                    >
                      Breakdown →
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
      <Note>
        Final amounts, fees and reconciliation are backend-owned. No money is
        transferred by this prototype interface.
      </Note>
      {selected && (
        <Modal
          title={`${selected.id} · Breakdown`}
          onClose={() => setSelected(null)}
        >
          <Badge tone="neutral">ILLUSTRATIVE RECORD</Badge>
          <div className="simple-list">
            {[
              ["Gross amount", selected.gross],
              ["Platform fee", selected.fee],
              ["Balancing charge", selected.balancing],
              ["Seller credit", selected.credit],
              ["Buyer debit", selected.debit],
            ].map(([k, v]) => (
              <div key={k}>
                <span>{k}</span>
                <strong>{money(v)}</strong>
              </div>
            ))}
          </div>
          <Note>
            Amounts shown are stored sample values. Connected records must come
            directly from the settlement API.
          </Note>
        </Modal>
      )}
    </>
  );
}
