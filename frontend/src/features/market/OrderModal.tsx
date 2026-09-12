import { ArrowRight } from "lucide-react";
import { Modal, Note } from "../../components/ui";

interface OrderModalProps {
  initialSide: string;
  onClose: () => void;
  onSaveDraft: (draft: {
    side: string;
    quantity: string;
    price: string;
  }) => void;
  saved: boolean;
  setSaved: (saved: boolean) => void;
}

export default function OrderModal({
  initialSide,
  onClose,
  onSaveDraft,
  saved,
  setSaved,
}: OrderModalProps) {
  return (
    <Modal
      title={saved ? "Demo draft saved" : "Prepare a day-ahead order"}
      onClose={onClose}
    >
      {saved ? (
        <>
          <Note>
            Your draft is visible below the order book. It has not been sent to
            the backend or matched.
          </Note>
          <button className="button primary full" onClick={onClose}>
            Back to marketplace
          </button>
        </>
      ) : (
        <form
          onSubmit={(e) => {
            e.preventDefault();
            const f = new FormData(e.currentTarget);
            onSaveDraft({
              side: String(f.get("side")),
              quantity: String(f.get("quantity")),
              price: String(f.get("price")),
            });
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
              defaultValue={initialSide === "Buy energy" ? "Buy" : "Sell"}
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
  );
}
