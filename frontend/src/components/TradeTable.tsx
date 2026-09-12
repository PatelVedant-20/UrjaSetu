import { Status } from "./ui";
import { money } from "../lib/format";
import { trades } from "../lib/demo";

export interface TradeItem {
  id: string;
  name: string;
  side: string;
  energy: number | string;
  price: number | string;
  status: string;
  window: string;
  total?: number | string;
  buy_order_id?: string;
  sell_order_id?: string;
  grid_validation_id?: string | null;
}

export default function TradeTable({
  rows = trades,
  onSelect,
}: {
  rows?: TradeItem[] | typeof trades;
  onSelect?: (row: TradeItem) => void;
}) {
  return (
    <div className="table-scroll">
      <table>
        <thead>
          <tr>
            <th>Trade / participant</th>
            <th>Side</th>
            <th>Energy</th>
            <th>Price / kWh</th>
            <th>Total Value</th>
            <th>Status</th>
            {onSelect && (
              <th>
                <span className="sr-only">Details</span>
              </th>
            )}
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => {
            const energyNum = Number(r.energy) || 0;
            const priceNum = Number(r.price) || 0;
            const totalValue =
              "total" in r && r.total ? Number(r.total) : energyNum * priceNum;

            return (
              <tr key={r.id}>
                <td>
                  <strong>{r.name}</strong>
                  <small>
                    {r.id} · {r.window}
                  </small>
                </td>
                <td>
                  <span className={`side ${r.side.toLowerCase()}`}>
                    {r.side.toLowerCase() === "sell" ? "↗" : "↙"} {r.side}
                  </span>
                </td>
                <td>{r.energy} kWh</td>
                <td>{money(r.price)}</td>
                <td>
                  <strong>{money(totalValue)}</strong>
                </td>
                <td>
                  <Status value={r.status} />
                </td>
                {onSelect && (
                  <td>
                    <button
                      className="text-button"
                      onClick={() => onSelect(r as TradeItem)}
                      aria-label={`View trade ${r.id}`}
                    >
                      View →
                    </button>
                  </td>
                )}
              </tr>
            );
          })}
        </tbody>
      </table>
      {!rows.length && <p className="empty">No trades match this filter.</p>}
    </div>
  );
}
