import { useEffect, useRef, type ReactNode } from "react";
import {
  X,
  Sun,
  House,
  ArrowUpRight,
  ArrowLeftRight,
  Wallet,
  TrendingUp,
} from "lucide-react";
import type { Metrics, Period } from "./types";

export const num = (value: unknown) => Number(value ?? 0);
export const str = (value: unknown) => (value == null ? "—" : String(value));
export const fmt = (value: unknown, digits = 2) =>
  value == null
    ? "—"
    : num(value).toLocaleString("en-IN", { maximumFractionDigits: digits });
export const rupees = (value: unknown) => `₹${fmt(value)}`;
export const stamp = (value: unknown, full = false) =>
  value
    ? new Intl.DateTimeFormat("en-IN", {
        timeZone: "Asia/Kolkata",
        ...(full ? ({ day: "2-digit", month: "short" } as const) : {}),
        hour: "2-digit",
        minute: "2-digit",
        hour12: true,
      }).format(new Date(str(value)))
    : "—";
export const periodNames: Record<Period, string> = {
  hour: "Last hour",
  day: "Last day",
  week: "Last week",
  month: "Last month",
};

export function Card({
  title,
  note,
  action,
  children,
  className = "",
}: {
  title?: string;
  note?: string;
  action?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={`uw-card ${className}`}>
      {(title || action) && (
        <div className="ux-card-heading">
          <div>
            <h2>{title}</h2>
            {note && <p>{note}</p>}
          </div>
          {action}
        </div>
      )}
      {children}
    </section>
  );
}
export function Heading({
  title,
  subtitle,
  action,
}: {
  title: string;
  subtitle: string;
  action?: ReactNode;
}) {
  return (
    <div className="ux-heading">
      <div>
        <div className="uw-eyebrow">A LITTLE SUNSHINE GOES A LONG WAY</div>
        <h1>{title}</h1>
        <p>{subtitle}</p>
      </div>
      {action}
    </div>
  );
}
export function Tabs<T extends string>({
  value,
  options,
  onChange,
  label,
}: {
  value: T;
  options: readonly (readonly [T, string])[];
  onChange: (value: T) => void;
  label: string;
}) {
  return (
    <div className="ux-tabs" role="group" aria-label={label}>
      {options.map(([key, title]) => (
        <button
          key={key}
          type="button"
          aria-pressed={value === key}
          onClick={() => onChange(key)}
        >
          {title}
        </button>
      ))}
    </div>
  );
}
export function PeriodTabs({
  value,
  onChange,
  periods = ["day", "week", "month"],
}: {
  value: Period;
  onChange: (value: Period) => void;
  periods?: Period[];
}) {
  return (
    <Tabs
      label="Summary period"
      value={value}
      onChange={onChange}
      options={periods.map((p) => [p, periodNames[p]] as const)}
    />
  );
}
export function Avatar({
  name,
  src,
  size = "",
}: {
  name: string;
  src?: string | null;
  size?: string;
}) {
  return (
    <span
      className={`ux-avatar ${size}`}
      style={
        {
          "--avatar-hue": String(
            ([...name].reduce((s, c) => s + c.charCodeAt(0), 0) % 90) + 80,
          ),
        } as React.CSSProperties
      }
    >
      {src ? (
        <img src={src} alt={`${name}'s profile`} />
      ) : (
        name
          .split(" ")
          .slice(0, 2)
          .map((x) => x[0])
          .join("")
      )}
    </span>
  );
}
export function Tag({ value }: { value: unknown }) {
  return (
    <span
      className={`uw-tag ${["rejected", "unsafe", "cancelled"].includes(str(value)) ? "danger" : ["pending", "committed", "open", "partially_filled"].includes(str(value)) ? "amber" : ""}`}
    >
      {str(value).replaceAll("_", " ")}
    </span>
  );
}
export function Empty({ children }: { children: ReactNode }) {
  return (
    <div className="ux-empty">
      <Sun size={30} />
      <p>{children}</p>
    </div>
  );
}
export function Table({
  headers,
  children,
}: {
  headers: string[];
  children: ReactNode;
}) {
  return (
    <div className="uw-table-wrap">
      <table>
        <thead>
          <tr>
            {headers.map((h) => (
              <th key={h}>{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>{children}</tbody>
      </table>
    </div>
  );
}
export function Modal({
  title,
  close,
  children,
}: {
  title: string;
  close: () => void;
  children: ReactNode;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const dialog = ref.current;
    dialog?.showModal();
    return () => dialog?.close();
  }, []);
  return (
    <dialog
      aria-label={title}
      className="ux-modal"
      ref={ref}
      onCancel={(e) => {
        e.preventDefault();
        close();
      }}
      onClick={(e) => {
        if (e.target === e.currentTarget) {
          const r = e.currentTarget.getBoundingClientRect();
          if (
            e.clientX < r.left ||
            e.clientX > r.right ||
            e.clientY < r.top ||
            e.clientY > r.bottom
          )
            close();
        }
      }}
    >
      <div className="ux-card-heading">
        <h2>{title}</h2>
        <button type="button" aria-label="Close dialog" onClick={close}>
          <X size={18} />
        </button>
      </div>
      {children}
    </dialog>
  );
}
export function MetricCards({
  metrics,
  kind = "energy",
}: {
  metrics: Metrics;
  kind?: "energy" | "money";
}) {
  const cards =
    kind === "energy"
      ? ([
          [
            "Solar generation",
            metrics.generation_kwh,
            "kWh",
            Sun,
            "gold",
            "Produced by your rooftop",
          ],
          [
            "Household consumption",
            metrics.load_kwh,
            "kWh",
            House,
            "mint",
            "Energy used at home",
          ],
          [
            "Energy to grid",
            metrics.grid_export_kwh,
            "kWh",
            ArrowUpRight,
            "blue",
            "Surplus leaving your home",
          ],
          [
            "Energy traded",
            metrics.traded_kwh ?? 0,
            "kWh",
            ArrowLeftRight,
            "lilac",
            "Delivered purchases + sales",
          ],
        ] as const)
      : ([
          [
            "Savings comparison",
            metrics.savings_inr,
            "INR",
            TrendingUp,
            "mint",
            "Solar use + purchase savings",
          ],
          [
            "Sales earnings",
            metrics.earned_inr,
            "INR",
            Sun,
            "gold",
            "Credit from delivered energy",
          ],
          [
            "Energy purchases",
            metrics.spent_inr,
            "INR",
            Wallet,
            "blue",
            "Debit for delivered energy",
          ],
          [
            "Energy exchanged",
            metrics.traded_kwh,
            "kWh",
            ArrowLeftRight,
            "lilac",
            "Settled with your neighbours",
          ],
        ] as const);
  return (
    <div className="ux-metrics">
      {cards.map(([label, value, unit, Icon, color, hint]) => (
        <article className={`ux-metric ${color}`} key={label}>
          <div>
            <span>{label}</span>
            <Icon size={19} />
          </div>
          <strong>
            {unit === "INR" ? rupees(value) : fmt(value)}
            <small>{unit === "INR" ? "" : unit}</small>
          </strong>
          <p>{hint}</p>
        </article>
      ))}
    </div>
  );
}
