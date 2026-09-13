import { useState } from "react";
import { Link } from "react-router-dom";
import {
  ArrowRight,
  Download,
  ShieldCheck,
  Sun,
  Zap,
  ArrowUpRight,
} from "lucide-react";
import {
  ResponsiveContainer,
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
} from "recharts";
import { workspaceRequest } from "../../lib/api";
import { exportCsv } from "../../lib/format";
import { LiveChart, HistoryChart } from "./charts";
import { forecastSlots } from "./Marketplace";
import {
  Card,
  Empty,
  Heading,
  MetricCards,
  PeriodTabs,
  Table,
  Tag,
  fmt,
  num,
  rupees,
  stamp,
  str,
} from "./ui";
import type { Experience, Period } from "./types";

export function EnergyPage({ data }: { data: Experience }) {
  const [period, setPeriod] = useState<Period>("day");
  const [records, setRecords] = useState(false);
  return (
    <>
      <Heading
        title={`Good energy, ${data.user.name.split(" ")[0]}.`}
        subtitle="A clear view of your home, your sunshine, and what comes next."
      />
      <div className="ux-energy-hero">
        <div>
          <div className="uw-eyebrow">YOUR HOME, RIGHT NOW</div>
          <h2>
            {num(data.live?.generation_kw) > num(data.live?.load_kw)
              ? "A little extra sunshine to share."
              : num(data.live?.generation_kw) > 0
                ? "Your rooftop is working for you."
                : "Your home's energy, always in view."}
          </h2>
          <p>Small choices. Local connections. A brighter energy community.</p>
          <Link to="/market">
            Find your next energy trade <ArrowRight size={17} />
          </Link>
        </div>
        <div className="ux-live-readings" data-testid="live-readings">
          <span>
            <Sun />
            <strong>
              {fmt(data.live?.generation_kw, 3)}
              <small>kW</small>
            </strong>
            Solar generation
          </span>
          <span>
            <Zap />
            <strong>
              {fmt(data.live?.load_kw, 3)}
              <small>kW</small>
            </strong>
            Home consumption
          </span>
          <span>
            <ArrowUpRight />
            <strong>
              {fmt(data.live?.grid_export_kw, 3)}
              <small>kW</small>
            </strong>
            Energy to grid
          </span>
        </div>
      </div>
      <div className="ux-section-line">
        <h2>Your energy at a glance</h2>
        <PeriodTabs
          value={period}
          onChange={setPeriod}
          periods={["hour", "day", "week"]}
        />
      </div>
      <MetricCards metrics={data.periods[period]} />
      <LiveChart scope="energy" userId={data.user.id} />
      <div className="ux-two">
        <Card
          title="A little progress adds up"
          note={`${period === "hour" ? "Last hour" : period === "day" ? "Last day" : "Last week"} · Compared with your ₹${fmt(data.profile.retail_rate)}/kWh rate`}
        >
          <div className="ux-savings-spot">
            <ShieldCheck />
            <strong>{rupees(data.periods[period].savings_inr)}</strong>
            <span>Solar use + energy purchase savings</span>
          </div>
          <Link to="/settlements">
            Understand your savings <ArrowRight size={15} />
          </Link>
        </Card>
        <Card
          title="Ready for tomorrow?"
          note="Your next opportunity starts with a forecast."
        >
          <p>
            Check when your household is likely to generate surplus solar or
            need energy. Choose a matching 15-minute delivery slot in the
            marketplace.
          </p>
          <Link className="ux-link-button" to="/forecasts">
            Explore your forecast <ArrowRight size={15} />
          </Link>
        </Card>
      </div>
      <Card
        title="Household reading history"
        note="Completed 15-minute readings · Most recent first"
        action={
          <button onClick={() => setRecords(!records)}>
            {records ? "Hide readings" : "View readings"}
          </button>
        }
      >
        {records && (
          <>
            <button
              onClick={() =>
                exportCsv(
                  [...data.readings].reverse().map((r) => ({
                    time_ist: stamp(r.interval_start, true),
                    generation_kwh: num(r.generation_kwh),
                    consumption_kwh: num(r.load_kwh),
                    grid_export_kwh: num(r.grid_export_kwh),
                    grid_import_kwh: num(r.grid_import_kwh),
                  })),
                  "household-readings.csv",
                )
              }
            >
              <Download size={16} />
              Export readings
            </button>
            <Table
              headers={[
                "Interval start · IST",
                "Solar",
                "Consumption",
                "To grid",
                "From grid",
              ]}
            >
              {[...data.readings].reverse().map((r) => (
                <tr key={r.id}>
                  <td>{stamp(r.interval_start, true)}</td>
                  <td>{fmt(r.generation_kwh, 4)} kWh</td>
                  <td>{fmt(r.load_kwh, 4)} kWh</td>
                  <td>{fmt(r.grid_export_kwh, 4)} kWh</td>
                  <td>{fmt(r.grid_import_kwh, 4)} kWh</td>
                </tr>
              ))}
            </Table>
          </>
        )}
      </Card>
    </>
  );
}

export function ForecastPage({ data }: { data: Experience }) {
  const slots = forecastSlots(data);
  const points = slots.map((s) => ({
    ...s,
    solar: s.solar * 4,
    load: s.load * 4,
  }));
  const best = [...slots]
    .sort((a, b) => b.solar - b.load - (a.solar - a.load))
    .slice(0, 4)
    .sort((a, b) => a.start.localeCompare(b.start));
  return (
    <>
      <Heading
        title="A little foresight. More sunshine."
        subtitle="Tomorrow's expected household demand and rooftop production, in 15-minute slots."
      />
      <div className="ux-metrics">
        <article className="ux-metric gold">
          <span>Tomorrow's solar</span>
          <strong>
            {fmt(slots.reduce((s, p) => s + p.solar, 0))}
            <small>kWh</small>
          </strong>
          <p>Expected rooftop production</p>
        </article>
        <article className="ux-metric mint">
          <span>Tomorrow's consumption</span>
          <strong>
            {fmt(slots.reduce((s, p) => s + p.load, 0))}
            <small>kWh</small>
          </strong>
          <p>Expected household demand</p>
        </article>
        <article className="ux-metric blue">
          <span>Potential surplus</span>
          <strong>
            {fmt(slots.reduce((s, p) => s + Math.max(0, p.solar - p.load), 0))}
            <small>kWh</small>
          </strong>
          <p>Before your existing reservations</p>
        </article>
        <article className="ux-metric lilac">
          <span>Planning window</span>
          <strong>
            15<small>minutes</small>
          </strong>
          <p>Every delivery slot uses IST</p>
        </article>
      </div>
      <Card
        title="Your day ahead"
        note="Recent household patterns inform the forecast; actual delivery can vary."
      >
        {points.length ? (
          <div
            className="uw-chart"
            role="img"
            aria-label="Tomorrow's household forecast"
          >
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={points}>
                <CartesianGrid vertical={false} strokeDasharray="3 5" />
                <XAxis
                  dataKey="start"
                  tickFormatter={(v) => stamp(v)}
                  minTickGap={55}
                />
                <YAxis unit=" kW" width={62} />
                <Tooltip
                  labelFormatter={(v) => stamp(v, true)}
                  formatter={(v, name) => [`${fmt(v)} kW`, name]}
                />
                <Legend />
                <Area
                  dataKey="solar"
                  name="Solar generation"
                  stroke="#d8a340"
                  fill="#e9cb86"
                  fillOpacity={0.25}
                />
                <Area
                  dataKey="load"
                  name="Household demand"
                  stroke="#347358"
                  fill="#c4dbce"
                  fillOpacity={0.2}
                />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        ) : (
          <Empty>Your forecast is being prepared.</Empty>
        )}
      </Card>
      <Card
        title="Promising times to share"
        note="Highest forecast surplus slots, displayed in time order."
      >
        <div className="ux-forecast-slots">
          {best.map((p) => (
            <Link to="/market" key={p.start}>
              <Sun />
              <strong>{stamp(p.start)}</strong>
              <span>{fmt(Math.max(0, p.solar - p.load), 3)} kWh surplus</span>
              <small>Explore marketplace →</small>
            </Link>
          ))}
        </div>
        {data.user.role === "consumer" && (
          <p className="uw-hint">
            Your household has no rooftop generation. Use the demand forecast to
            plan purchases from neighbours.
          </p>
        )}
      </Card>
    </>
  );
}

export function TradesPage({ data }: { data: Experience }) {
  const [filter, setFilter] = useState("all");
  const trades = data.trades.filter(
    (t) => filter === "all" || t.status === filter,
  );
  return (
    <>
      <Heading
        title="Every exchange has a story."
        subtitle="Follow your energy from an agreed trade to delivery and a verifiable receipt."
      />
      <Card
        title="Your trades"
        note="Newest agreements first"
        action={
          <label>
            Trade status
            <select value={filter} onChange={(e) => setFilter(e.target.value)}>
              {["all", "committed", "settled", "rejected"].map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </select>
          </label>
        }
      >
        {trades.length ? (
          trades.map((t) => {
            const price = data.prices.find((p) => p.trade_id === t.id);
            const settlement = data.settlements.find(
              (s) => s.trade_id === t.id,
            );
            const grid = data.grid.find((g) => g.id === t.grid_validation_id);
            return (
              <article
                className="ux-trade-detail"
                key={t.id}
                data-trade-id={t.id}
              >
                <div className="ux-card-heading">
                  <div>
                    <h3>
                      {t.side === "buy"
                        ? "Buying local energy"
                        : "Sharing your solar"}
                    </h3>
                    <p>
                      {stamp(t.delivery_start, true)} IST · 15-minute delivery
                    </p>
                  </div>
                  <Tag value={t.status} />
                </div>
                <div className="ux-trade-numbers">
                  <span>
                    <small>Agreed energy</small>
                    <strong>{fmt(t.quantity_kwh, 4)} kWh</strong>
                  </span>
                  <span>
                    <small>Final unit price</small>
                    <strong>{rupees(price?.final_price)}/kWh</strong>
                  </span>
                  <span>
                    <small>Delivered energy</small>
                    <strong>
                      {settlement
                        ? `${fmt(settlement.settled_kwh, 4)} kWh`
                        : "Awaiting delivery"}
                    </strong>
                  </span>
                </div>
                <div className="ux-journey">
                  <span className="done">1 · Agreed</span>
                  <span className={t.status !== "rejected" ? "done" : ""}>
                    2 · Grid checked
                  </span>
                  <span className={settlement ? "done" : ""}>
                    3 · Delivered
                  </span>
                  <Link to={settlement ? "/audit" : "/settlements"}>
                    4 · Receipt →
                  </Link>
                </div>
                <details>
                  <summary>Price & grid details</summary>
                  <p>{str(grid?.reason)}</p>
                  <Table headers={["Price component", "₹/kWh"]}>
                    {[
                      "base_market_price",
                      "time_component",
                      "congestion_component",
                      "imbalance_component",
                      "local_renewable_component",
                      "final_price",
                    ].map((k) => (
                      <tr key={k}>
                        <td>{k.replaceAll("_", " ")}</td>
                        <td>{fmt(price?.[k], 4)}</td>
                      </tr>
                    ))}
                  </Table>
                  <small>Trade reference: {t.id}</small>
                </details>
              </article>
            );
          })
        ) : (
          <Empty>
            No trades in this view. Accept a neighbour's offer in Marketplace to
            start one.
          </Empty>
        )}
      </Card>
    </>
  );
}

export function SettlementsPage({ data }: { data: Experience }) {
  const [period, setPeriod] = useState<Period>("month");
  const days = period === "day" ? 1 : period === "week" ? 7 : 30;
  const end = new Date(data.as_of).getTime();
  const records = data.settlements.filter((r) => {
    const t = new Date(str(r.settled_at)).getTime();
    return t >= end - days * 86400000 && t <= end;
  });
  const csv = records.map((r) => {
    const buy = r.buyer_user_id === data.user.id;
    return {
      settled_at_ist: stamp(r.settled_at, true),
      settled_at_utc: str(r.settled_at),
      direction: buy ? "purchase" : "sale",
      energy_kwh: num(r.settled_kwh),
      amount_inr: num(buy ? r.buyer_debit_inr : r.seller_credit_inr),
      trade_id: str(r.trade_id),
      status: str(r.status),
    };
  });
  return (
    <>
      <Heading
        title="See what your sunshine earns."
        subtitle="A clear account of delivered energy, your savings comparison, and every exchange."
        action={
          <button
            onClick={() => exportCsv(csv, "energy-settlements.csv")}
            disabled={!csv.length}
          >
            <Download size={17} />
            Export to CSV
          </button>
        }
      />
      <div className="ux-section-line">
        <h2>Your energy account</h2>
        <PeriodTabs value={period} onChange={setPeriod} />
      </div>
      <MetricCards metrics={data.periods[period]} kind="money" />
      <div className="ux-two">
        <Card
          title="How your savings add up"
          note={`Compared with your ₹${fmt(data.profile.retail_rate)}/kWh rate`}
        >
          <dl className="ux-money-breakdown">
            <div>
              <dt>Solar used at home</dt>
              <dd>{rupees(data.periods[period].solar_savings_inr)}</dd>
            </div>
            <div>
              <dt>Savings from energy purchases</dt>
              <dd>{rupees(data.periods[period].trade_savings_inr)}</dd>
            </div>
            <div>
              <dt>Total savings comparison</dt>
              <dd>{rupees(data.periods[period].savings_inr)}</dd>
            </div>
          </dl>
          <p className="uw-hint">
            Sales earnings are listed separately. This comparison uses the rate
            in your profile and excludes your utility's fixed charges.
          </p>
        </Card>
        <Card title="From agreement to your account">
          <ol className="ux-explainer">
            <li>Agree on energy and a price with a neighbour.</li>
            <li>Wait for the selected delivery interval to finish.</li>
            <li>
              Available seller exports and buyer imports determine delivered
              energy.
            </li>
            <li>
              Delivered kWh × agreed price becomes your account credit or debit.
            </li>
          </ol>
        </Card>
      </div>
      <Card
        title="Progress through the month"
        note="Daily savings, sales earnings and purchases · INR"
      >
        <HistoryChart data={data.daily.slice(-days)} money />
      </Card>
      <Card title="Your energy statement" note="Most recent settlements first">
        {records.length ? (
          <Table
            headers={[
              "Settled · IST",
              "Exchange",
              "Neighbour",
              "Delivered",
              "Account movement",
              "Receipt",
            ]}
          >
            {records.map((r) => {
              const buy = r.buyer_user_id === data.user.id;
              const person = data.members.find(
                (m) => m.id === (buy ? r.seller_user_id : r.buyer_user_id),
              );
              return (
                <tr key={r.id}>
                  <td>{stamp(r.settled_at, true)}</td>
                  <td>
                    <Tag value={buy ? "purchase" : "sale"} />
                  </td>
                  <td>{person?.name || "Community household"}</td>
                  <td>{fmt(r.settled_kwh, 4)} kWh</td>
                  <td className={buy ? "ux-debit" : "ux-credit"}>
                    {buy ? "−" : "+"}
                    {rupees(buy ? r.buyer_debit_inr : r.seller_credit_inr)}
                  </td>
                  <td>
                    <Link to="/audit">View receipt →</Link>
                  </td>
                </tr>
              );
            })}
          </Table>
        ) : (
          <Empty>
            No completed settlements in this period. Your agreed trades will
            appear after their delivery intervals finish.
          </Empty>
        )}
      </Card>
    </>
  );
}

export function AuditPage({ data }: { data: Experience }) {
  const [verifying, setVerifying] = useState<string | null>(null);
  const [results, setResults] = useState<Record<string, string>>({});
  async function verify(id: string) {
    setVerifying(id);
    try {
      const result = await workspaceRequest<{
        verified: boolean;
        error?: string;
      }>(`/workspace/receipts/${id}/verify`);
      setResults((r) => ({
        ...r,
        [id]: result.verified
          ? "Verified. This settlement matches the record on the blockchain."
          : `Verification failed: ${result.error || "The stored record does not match."}`,
      }));
    } catch (e) {
      setResults((r) => ({
        ...r,
        [id]: e instanceof Error ? e.message : "Verification unavailable.",
      }));
    } finally {
      setVerifying(null);
    }
  }
  return (
    <>
      <Heading
        title="Trust you can check."
        subtitle="Every settled trade leaves a receipt. Verify it independently against your community's blockchain."
      />
      <Card
        title="Your blockchain receipts"
        note="Most recent settlements first"
      >
        {data.receipts.length ? (
          data.receipts.map((r) => (
            <article
              className="ux-receipt"
              key={r.id}
              data-trade-id={str(r.trade_id)}
            >
              <div className="ux-card-heading">
                <div>
                  <ShieldCheck />
                  <h3>Energy settlement receipt</h3>
                  <small>{stamp(r.created_at, true)} IST</small>
                </div>
                <Tag value={r.status} />
              </div>
              <div className="ux-receipt-meta">
                <span>
                  Block<strong>{str(r.block_number)}</strong>
                </span>
                <span>
                  Network<strong>EVM · {str(r.chain_id)}</strong>
                </span>
              </div>
              <label>
                Transaction hash<code>{str(r.transaction_hash)}</code>
              </label>
              <button
                onClick={() => void verify(r.id)}
                disabled={Boolean(verifying) || r.status !== "confirmed"}
              >
                {verifying === r.id ? "Verifying…" : "Verify on blockchain"}
                <ShieldCheck size={16} />
              </button>
              {results[r.id] && <p role="status">{results[r.id]}</p>}
              {r.status === "pending" && (
                <p className="uw-hint">
                  The receipt is queued. Publication retries automatically when
                  the blockchain is available.
                </p>
              )}
              <details>
                <summary>Receipt reference</summary>
                <p>Trade: {str(r.trade_id)}</p>
                <p>Contract: {str(r.contract_address)}</p>
                <p>Content hash: {str(r.payload_hash)}</p>
              </details>
            </article>
          ))
        ) : (
          <Empty>
            Your first receipt appears when a trade settles. Find a neighbour's
            offer in Marketplace.
          </Empty>
        )}
      </Card>
      <Card title="Your activity timeline" note="Most recent events first">
        <div className="ux-timeline">
          {data.audit.map((a) => (
            <article key={a.id}>
              <span />
              <div>
                <h3>{str(a.event_type).replaceAll("_", " ")}</h3>
                <p>{stamp(a.recorded_at || a.event_time, true)} IST</p>
                <small>Reference {str(a.entity_id).slice(0, 8)}</small>
              </div>
            </article>
          ))}
        </div>
        {!data.audit.length && (
          <Empty>Place an order to start your energy history.</Empty>
        )}
      </Card>
    </>
  );
}
