import { useRef, useState } from "react";
import { Link } from "react-router-dom";
import { ArrowRight, Plus, ShieldCheck, Sun } from "lucide-react";
import {
  Avatar,
  Card,
  Empty,
  Heading,
  Modal,
  Table,
  Tabs,
  Tag,
  fmt,
  num,
  rupees,
  stamp,
  str,
} from "./ui";
import type { Experience, Perform, Row } from "./types";

export function forecastSlots(data: Experience) {
  const map = new Map<string, { start: string; solar: number; load: number }>();
  for (const p of data.forecasts) {
    const start = str(p.interval_start);
    const point = map.get(start) || { start, solar: 0, load: 0 };
    if (p.kind === "solar") point.solar = num(p.predicted_kwh);
    else point.load = num(p.predicted_kwh);
    map.set(start, point);
  }
  return [...map.values()].sort((a, b) => a.start.localeCompare(b.start));
}
function NewOrder({
  data,
  side,
  close,
  perform,
  pending,
  error,
}: {
  data: Experience;
  side: "buy" | "sell";
  close: () => void;
  perform: Perform;
  pending: boolean;
  error: string;
}) {
  const slots = forecastSlots(data);
  const best = [...slots].sort(
    (a, b) => b.solar - b.load - (a.solar - a.load),
  )[0];
  const [start, setStart] = useState(best?.start || slots[0]?.start || "");
  const [quantity, setQuantity] = useState("0.01");
  const [price, setPrice] = useState(side === "sell" ? "4" : "8");
  const slot = slots.find((s) => s.start === start);
  const reserved = data.orders
    .filter((o) => o.side === "sell" && o.delivery_start === start)
    .reduce(
      (s, o) =>
        s +
        num(o.matched_kwh) +
        (["open", "partially_filled"].includes(str(o.status))
          ? num(o.energy_kwh) - num(o.matched_kwh)
          : 0),
      0,
    );
  const available = Math.max(
    0,
    (slot?.solar || 0) - (slot?.load || 0) - reserved,
  );
  return (
    <Modal
      title={side === "sell" ? "Offer your sunshine" : "Create a buy order"}
      close={close}
    >
      <p>
        {side === "sell"
          ? "Choose when you can share surplus solar and the minimum rate you will accept."
          : "Tell neighbours how much energy you need and the most you want to pay."}
      </p>
      <form
        className="ux-form-stack"
        onSubmit={async (e) => {
          e.preventDefault();
          if (
            await perform(
              "/workspace/orders",
              { start, side, quantity, price },
              "Order published. Neighbours can now accept it.",
            )
          )
            close();
        }}
      >
        <label>
          Delivery slot · Tomorrow, IST
          <select
            required
            value={start}
            onChange={(e) => setStart(e.target.value)}
          >
            {slots.map((s) => (
              <option key={s.start} value={s.start}>
                {stamp(s.start, true)} · {fmt(Math.max(0, s.solar - s.load), 3)}{" "}
                kWh forecast surplus
              </option>
            ))}
          </select>
        </label>
        {side === "sell" && (
          <p className="ux-availability">
            <Sun size={17} />
            {fmt(available, 4)} kWh available after your reservations
          </p>
        )}
        <div className="ux-form-grid">
          <label>
            Energy quantity (kWh)
            <input
              type="number"
              min="0.0001"
              max={side === "sell" ? Math.min(10, available) : 10}
              step="0.0001"
              value={quantity}
              required
              onChange={(e) => setQuantity(e.target.value)}
            />
          </label>
          <label>
            {side === "sell" ? "Minimum price" : "Maximum price"} (₹/kWh)
            <input
              type="number"
              min="0.01"
              max="30"
              step="0.01"
              required
              value={price}
              onChange={(e) => setPrice(e.target.value)}
            />
          </label>
        </div>
        <p className="uw-hint">
          Each delivery slot lasts 15 minutes. Your limit is checked again when
          a neighbour accepts. An order becomes a trade only after a successful
          match.
        </p>
        <button
          className="uw-primary"
          disabled={pending || !start || (side === "sell" && available <= 0)}
        >
          {pending ? "Publishing…" : "Publish order"}
          <ArrowRight size={16} />
        </button>
        {error && (
          <p role="alert" className="uw-inline-error">
            {error}
          </p>
        )}
      </form>
    </Modal>
  );
}
function AcceptOffer({
  offer,
  data,
  perform,
  pending,
  close,
  error,
}: {
  offer: Row;
  data: Experience;
  perform: Perform;
  pending: boolean;
  close: () => void;
  error: string;
}) {
  const buying = offer.side === "sell";
  const compatible = data.orders.filter(
    (o) =>
      o.side === (buying ? "buy" : "sell") &&
      o.delivery_start === offer.delivery_start &&
      ["open", "partially_filled"].includes(str(o.status)),
  );
  const [ownId, setOwnId] = useState(compatible[0]?.id || "");
  const [quantity, setQuantity] = useState(
    String(
      Math.min(
        0.1,
        num(offer.energy_kwh),
        compatible[0]
          ? num(compatible[0].energy_kwh) - num(compatible[0].matched_kwh)
          : 10,
      ),
    ),
  );
  const [price, setPrice] = useState(
    String(
      buying
        ? Math.min(30, Math.max(num(offer.price) * 1.3, 8))
        : Math.max(0.01, num(offer.price) * 0.65),
    ),
  );
  const own = compatible.find((o) => o.id === ownId);
  const limit = own
    ? str(own[buying ? "max_price_inr_per_kwh" : "min_price_inr_per_kwh"])
    : price;
  const cap = Math.min(
    num(offer.energy_kwh),
    own ? num(own.energy_kwh) - num(own.matched_kwh) : 10,
  );
  const request = useRef({ body: "", id: crypto.randomUUID() });
  return (
    <Modal
      title={`${buying ? "Buy from" : "Sell to"} ${str(offer.owner_name)}`}
      close={close}
    >
      <div className="ux-offer-person">
        <Avatar
          name={str(offer.owner_name)}
          src={offer.avatar as string | null}
        />
        <div>
          <strong>{str(offer.owner_name)}</strong>
          <p>{stamp(offer.delivery_start, true)} IST · 15-minute delivery</p>
        </div>
      </div>
      <div className="ux-quote-line">
        <span>{buying ? "Seller's minimum" : "Buyer's maximum"}</span>
        <strong>{rupees(offer.price)}/kWh</strong>
      </div>
      <form
        className="ux-form-stack"
        onSubmit={async (e) => {
          e.preventDefault();
          const body = { quantity, price: limit, own_order_id: ownId || null };
          const signature = JSON.stringify(body);
          if (signature !== request.current.body)
            request.current = { body: signature, id: crypto.randomUUID() };
          if (
            await perform(
              `/workspace/orders/${offer.id}/accept`,
              { ...body, request_id: request.current.id },
              "Trade confirmed with your neighbour. Follow delivery in My trades.",
            )
          )
            close();
        }}
      >
        {compatible.length > 0 && (
          <label>
            Match with your order
            <select
              value={ownId}
              onChange={(e) => {
                setOwnId(e.target.value);
                const order = compatible.find((o) => o.id === e.target.value);
                const remaining = Math.min(
                  num(offer.energy_kwh),
                  order ? num(order.energy_kwh) - num(order.matched_kwh) : 10,
                );
                setQuantity((value) => String(Math.min(num(value), remaining)));
              }}
            >
              <option value="">Create a new matching order</option>
              {compatible.map((o) => (
                <option key={o.id} value={o.id}>
                  {fmt(num(o.energy_kwh) - num(o.matched_kwh), 4)} kWh remaining
                  ·{" "}
                  {rupees(
                    o[
                      buying ? "max_price_inr_per_kwh" : "min_price_inr_per_kwh"
                    ],
                  )}
                  /kWh limit
                </option>
              ))}
            </select>
          </label>
        )}
        <div className="ux-form-grid">
          <label>
            Quantity (kWh)
            <input
              type="number"
              required
              step="0.0001"
              min="0.0001"
              max={cap}
              value={quantity}
              onChange={(e) => setQuantity(e.target.value)}
            />
            <small>{fmt(cap, 4)} kWh available</small>
          </label>
          <label>
            {buying ? "Your maximum price" : "Your minimum price"} (₹/kWh)
            <input
              type="number"
              required
              disabled={Boolean(own)}
              step="0.01"
              min="0.01"
              max="30"
              value={limit}
              onChange={(e) => setPrice(e.target.value)}
            />
          </label>
        </div>
        <div className="ux-quote-line">
          <span>{buying ? "Maximum commitment" : "Minimum sale value"}</span>
          <strong>{rupees(num(quantity) * num(limit))}</strong>
        </div>
        <p className="uw-hint">
          <ShieldCheck size={16} /> Final pricing must fit both limits and pass
          the grid check. Payment is calculated after the delivery interval from
          allocated energy.
        </p>
        <button className="uw-primary" disabled={pending || cap <= 0}>
          {pending
            ? "Checking & confirming…"
            : buying
              ? "Confirm energy purchase"
              : "Confirm energy sale"}
        </button>
        {error && (
          <p role="alert" className="uw-inline-error">
            {error}
          </p>
        )}
      </form>
    </Modal>
  );
}

export function MarketplacePage({
  data,
  perform,
  pending,
  error,
}: {
  data: Experience;
  perform: Perform;
  pending: boolean;
  error: string;
}) {
  const [tab, setTab] = useState<"buy" | "sell" | "orders">("buy");
  const [creating, setCreating] = useState<"buy" | "sell" | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const selected = data.order_book.find((offer) => offer.id === selectedId);
  const [orderFilter, setOrderFilter] = useState("all");
  const book = data.order_book.filter(
    (o) => !o.mine && o.side === (tab === "buy" ? "sell" : "buy"),
  );
  const orders = data.orders.filter(
    (o) => orderFilter === "all" || o.status === orderFilter,
  );
  return (
    <>
      <Heading
        title="A fairer share of sunshine."
        subtitle="Buy local solar, offer your surplus, and trade directly with your neighbours."
        action={
          <button
            className="uw-primary"
            onClick={() =>
              setCreating(
                tab === "sell" && data.user.role === "prosumer"
                  ? "sell"
                  : "buy",
              )
            }
            disabled={!data.sites.length}
          >
            <Plus size={17} />
            Create an order
          </button>
        }
      />
      <div className="ux-market-intro">
        <Sun />
        <div>
          <strong>Made locally. Shared directly.</strong>
          <p>
            Choose an offer to match a household now. Delivery is scheduled for
            tomorrow's selected 15-minute slot.
          </p>
        </div>
        <Link to="/forecasts">
          Explore your forecast <ArrowRight size={16} />
        </Link>
      </div>
      <Tabs
        label="Marketplace view"
        value={tab}
        onChange={setTab}
        options={[
          ["buy", "Buy energy"],
          ["sell", "Sell energy"],
          ["orders", `My orders (${data.orders.length})`],
        ]}
      />
      {tab !== "orders" ? (
        <>
          <div className="ux-section-line">
            <h2>
              {tab === "buy"
                ? "Solar from your neighbours"
                : "Neighbours looking for energy"}
            </h2>
            <span>
              {book.length} available offers · Delivery time, then best price
            </span>
          </div>
          {book.length ? (
            <div className="ux-offer-grid">
              {book.map((o) => (
                <article
                  className="uw-card ux-offer"
                  key={o.id}
                  data-offer-id={o.id}
                >
                  <div className="ux-offer-person">
                    <Avatar
                      name={str(o.owner_name)}
                      src={o.avatar as string | null}
                    />
                    <div>
                      <h3>{str(o.owner_name)}</h3>
                      <small>
                        {o.side === "sell"
                          ? "Sharing rooftop solar"
                          : "Looking for local energy"}
                      </small>
                    </div>
                    <Tag value="open" />
                  </div>
                  <div className="ux-offer-price">
                    <strong>
                      {rupees(o.price)}
                      <small>/kWh</small>
                    </strong>
                    <span>
                      {o.side === "sell"
                        ? "minimum asking price"
                        : "maximum buying price"}
                    </span>
                  </div>
                  <div className="ux-offer-facts">
                    <span>
                      Available<strong>{fmt(o.energy_kwh, 4)} kWh</strong>
                    </span>
                    <span>
                      Delivery · IST
                      <strong>{stamp(o.delivery_start, true)}</strong>
                    </span>
                  </div>
                  <button
                    className="uw-primary"
                    onClick={() => setSelectedId(str(o.id))}
                    disabled={
                      !data.sites.length ||
                      (tab === "sell" && data.user.role !== "prosumer")
                    }
                  >
                    {tab === "buy" ? "Buy energy" : "Sell energy"}
                    <ArrowRight size={16} />
                  </button>
                </article>
              ))}
            </div>
          ) : (
            <Card>
              <Empty>
                {tab === "buy"
                  ? "No sell offers yet. Create a buy order so your neighbours know what you need."
                  : "No buy orders yet. Publish your surplus so neighbours can find it."}
              </Empty>
            </Card>
          )}
          {tab === "sell" && data.user.role === "prosumer" && (
            <button onClick={() => setCreating("sell")}>
              <Plus size={16} />
              Offer your surplus
            </button>
          )}
          {tab === "sell" && data.user.role !== "prosumer" && (
            <p className="uw-hint">
              Selling requires a household with rooftop solar. You can buy
              energy from the Buy energy tab.
            </p>
          )}
        </>
      ) : (
        <Card
          title="Your order history"
          note="Newest orders first"
          action={
            <label>
              Filter orders
              <select
                value={orderFilter}
                onChange={(e) => setOrderFilter(e.target.value)}
              >
                {[
                  "all",
                  "open",
                  "partially_filled",
                  "filled",
                  "cancelled",
                  "rejected",
                ].map((v) => (
                  <option value={v} key={v}>
                    {v.replaceAll("_", " ")}
                  </option>
                ))}
              </select>
            </label>
          }
        >
          {orders.length ? (
            <Table
              headers={[
                "Created · IST",
                "Direction",
                "Delivery · IST",
                "Quantity",
                "Matched",
                "Limit",
                "Status",
                "Action",
              ]}
            >
              {orders.map((o) => (
                <tr key={o.id}>
                  <td>{stamp(o.created_at, true)}</td>
                  <td>
                    <Tag value={o.side} />
                  </td>
                  <td>{stamp(o.delivery_start, true)}</td>
                  <td>{fmt(o.energy_kwh, 4)} kWh</td>
                  <td>{fmt(o.matched_kwh, 4)} kWh</td>
                  <td>
                    {rupees(o.min_price_inr_per_kwh ?? o.max_price_inr_per_kwh)}
                  </td>
                  <td>
                    <Tag value={o.status} />
                  </td>
                  <td>
                    {o.status === "open" && !num(o.matched_kwh) ? (
                      <button
                        disabled={pending}
                        onClick={() =>
                          void perform(
                            `/workspace/orders/${o.id}/cancel`,
                            {},
                            "Order cancelled. Its reserved energy is available again.",
                          )
                        }
                      >
                        Cancel
                      </button>
                    ) : (
                      "—"
                    )}
                  </td>
                </tr>
              ))}
            </Table>
          ) : (
            <Empty>No orders match this view.</Empty>
          )}
        </Card>
      )}
      {creating && (
        <NewOrder
          data={data}
          side={creating}
          close={() => {
            setCreating(null);
          }}
          perform={async (...args) => {
            const success = await perform(...args);
            if (success) {
              setTab("orders");
              setOrderFilter("all");
            }
            return success;
          }}
          pending={pending}
          error={error}
        />
      )}{" "}
      {selected && (
        <AcceptOffer
          offer={selected}
          data={data}
          perform={perform}
          pending={pending}
          close={() => setSelectedId(null)}
          error={error}
        />
      )}
    </>
  );
}
