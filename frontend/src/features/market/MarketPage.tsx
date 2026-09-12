import { useState } from "react";
import { Plus, ArrowRight } from "lucide-react";
import {
  PageHeader,
  Card,
  Tabs,
  Badge,
  Modal,
  Note,
} from "../../components/ui";
import EnergyChart from "../../components/EnergyChart";
import { money } from "../../lib/format";
export default function MarketPage() {
  const [side, setSide] = useState("Buy energy");
  const [open, setOpen] = useState(false);
  const [drafts, setDrafts] = useState<
    { side: string; quantity: string; price: string }[]
  >([]);
  const [saved, setSaved] = useState(false);
  return (
    <>
      <PageHeader
        eyebrow="LOCAL SUPPLY. SHARED OPPORTUNITY."
        title="Energy marketplace"
        description="Explore tomorrow’s energy offers and find a place for your surplus."
        action={
          <button
            className="button primary"
            onClick={() => {
              setSaved(false);
              setOpen(true);
            }}
          >
            <Plus size={17} /> Create demo order
          </button>
        }
      />
      <div className="market-banner">
        <div>
          <Badge>DAY-AHEAD MARKET</Badge>
          <h2>Tomorrow starts with today’s sunshine.</h2>
          <p>Illustrative delivery date: 13 September 2026 · Asia/Kolkata</p>
        </div>
        <div className="market-price">
          <small>INDICATIVE PRICE</small>
          <strong>
            ₹4.65 <span>/ kWh</span>
          </strong>
        </div>
      </div>
      <div className="split-main">
        <Card
          title="Market price trend"
          subtitle="Illustrative INR/kWh · not a live price feed"
        >
          <EnergyChart kind="price" />
        </Card>
        <Card
          title="What makes up the price?"
          subtitle="Illustrative composition · INR/kWh"
        >
          <div className="price-breakdown">
            {[
              ["Base market price", "₹4.50"],
              ["Time component", "+ ₹0.20"],
              ["Congestion component", "₹0.00"],
              ["Imbalance component", "+ ₹0.10"],
              ["Local renewable incentive", "− ₹0.15"],
            ].map(([k, v]) => (
              <div className="metric-line" key={k}>
                <span>{k}</span>
                <strong>{v}</strong>
              </div>
            ))}
            <div className="price-total">
              <span>Indicative final price</span>
              <strong>₹4.65</strong>
            </div>
          </div>
          <Note>
            Final prices and decisions come from the backend pricing engine.
          </Note>
        </Card>
      </div>
      <Card
        title="Community order book"
        subtitle="Illustrative offers · delivery 13 Sep, 12:00–13:00 IST"
        action={
          <Tabs
            items={["Buy energy", "Sell energy"]}
            value={side}
            onChange={setSide}
          />
        }
      >
        <div className="offer-grid">
          {(side === "Buy energy"
            ? [
                ["Mehta Rooftop", "8.2", "4.45"],
                ["Patel Residence", "10.0", "4.70"],
                ["Aarav Residence", "12.5", "4.65"],
              ]
            : [
                ["Greenview Society", "18.0", "4.80"],
                ["Community Library", "6.0", "4.60"],
              ]
          ).map(([name, energy, price]) => (
            <div className="offer" key={name}>
              <div className="offer-top">
                <span className="avatar pale">
                  {name
                    .split(" ")
                    .map((s) => s[0])
                    .join("")}
                </span>
                <Badge tone="neutral">
                  {side === "Buy energy" ? "SELL OFFER" : "BUY BID"}
                </Badge>
              </div>
              <h3>{name}</h3>
              <p>Community feeder · Solar energy</p>
              <div className="offer-values">
                <div>
                  <strong>{energy}</strong>
                  <small>kWh available</small>
                </div>
                <div>
                  <strong>{money(price)}</strong>
                  <small>per kWh</small>
                </div>
              </div>
              <button
                className="button secondary full"
                onClick={() => {
                  setSaved(false);
                  setOpen(true);
                }}
              >
                Prepare demo {side === "Buy energy" ? "buy" : "sell"} order{" "}
                <ArrowRight size={15} />
              </button>
            </div>
          ))}
        </div>
      </Card>
      {drafts.length > 0 && (
        <Card
          title="Your local drafts"
          subtitle="Browser memory only · not submitted"
        >
          <div className="simple-list">
            {drafts.map((d, i) => (
              <div key={i}>
                <strong>{d.side}</strong>
                <span>
                  {d.quantity} kWh · {money(d.price)}/kWh
                </span>
                <Badge tone="neutral">Local draft</Badge>
              </div>
            ))}
          </div>
        </Card>
      )}
      {open && (
        <Modal
          title={saved ? "Demo draft saved" : "Prepare a day-ahead order"}
          onClose={() => setOpen(false)}
        >
          {saved ? (
            <>
              <Note>
                Your draft is visible below the order book. It has not been sent
                to the backend or matched.
              </Note>
              <button
                className="button primary full"
                onClick={() => setOpen(false)}
              >
                Back to marketplace
              </button>
            </>
          ) : (
            <form
              onSubmit={(e) => {
                e.preventDefault();
                const f = new FormData(e.currentTarget);
                setDrafts([
                  ...drafts,
                  {
                    side: String(f.get("side")),
                    quantity: String(f.get("quantity")),
                    price: String(f.get("price")),
                  },
                ]);
                setSaved(true);
              }}
            >
              <Note>
                Demo draft only. A connected order requires a verified identity,
                site, open market session and backend eligibility.
              </Note>
              <label>
                Order side
                <select
                  name="side"
                  defaultValue={side === "Buy energy" ? "Buy" : "Sell"}
                >
                  <option>Buy</option>
                  <option>Sell</option>
                </select>
              </label>
              <div className="form-grid">
                <label>
                  Energy (kWh)
                  <input
                    name="quantity"
                    type="number"
                    min="0.001"
                    step="0.001"
                    required
                    placeholder="12.5"
                  />
                </label>
                <label>
                  Limit price (INR/kWh)
                  <input
                    name="price"
                    type="number"
                    min="0"
                    step="0.01"
                    required
                    placeholder="4.65"
                  />
                </label>
              </div>
              <label>
                Illustrative delivery window
                <input value="13 Sep 2026 · 12:00–13:00 IST" readOnly />
              </label>
              <button className="button primary full" type="submit">
                Save local draft <ArrowRight size={16} />
              </button>
            </form>
          )}
        </Modal>
      )}
    </>
  );
}
