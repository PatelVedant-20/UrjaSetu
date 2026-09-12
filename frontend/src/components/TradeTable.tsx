import { Status } from "./ui";
import { money } from "../lib/format";
import { trades } from "../lib/demo";
export default function TradeTable({
  rows = trades,
  onSelect,
}: {
  rows?: typeof trades;
  onSelect?: (row: (typeof trades)[number]) => void;
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
            <th>Status</th>
            {onSelect && (
              <th>
                <span className="sr-only">Details</span>
              </th>
            )}
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.id}>
              <td>
                <strong>{r.name}</strong>
                <small>
                  {r.id} · {r.window}
                </small>
              </td>
              <td>
                <span className={`side ${r.side.toLowerCase()}`}>
                  {r.side === "Sell" ? "↗" : "↙"} {r.side}
                </span>
              </td>
              <td>{r.energy} kWh</td>
              <td>{money(r.price)}</td>
              <td>
                <Status value={r.status} />
              </td>
              {onSelect && (
                <td>
                  <button className="text-button" onClick={() => onSelect(r)}>
                    View →
                  </button>
                </td>
              )}
            </tr>
          ))}
        </tbody>
      </table>
      {!rows.length && <p className="empty">No trades match this filter.</p>}
    </div>
  );
}
