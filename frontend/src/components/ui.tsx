import { useEffect, useRef } from "react";
import type { ReactNode } from "react";
import { X, ArrowUpRight } from "lucide-react";
export function Badge({
  children,
  tone = "green",
}: {
  children: ReactNode;
  tone?: string;
}) {
  return (
    <span className={`badge ${tone}`}>
      <span className="status-dot" />
      {children}
    </span>
  );
}
export function Status({ value }: { value: string }) {
  return (
    <Badge
      tone={
        ["rejected", "invalid_value", "unsafe"].includes(value)
          ? "red"
          : [
                "pending",
                "proposed",
                "stale",
                "unknown",
                "self_declared",
                "document_verified",
              ].includes(value)
            ? "amber"
            : "green"
      }
    >
      {value.replaceAll("_", " ")}
    </Badge>
  );
}
export function Card({
  title,
  subtitle,
  action,
  children,
  className = "",
}: {
  title?: string;
  subtitle?: string;
  action?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={`card ${className}`}>
      {title && (
        <div className="card-heading">
          <div>
            <h2>{title}</h2>
            {subtitle && <p>{subtitle}</p>}
          </div>
          {action}
        </div>
      )}
      {children}
    </section>
  );
}
export function PageHeader({
  eyebrow,
  title,
  description,
  action,
}: {
  eyebrow: string;
  title: string;
  description: string;
  action?: ReactNode;
}) {
  return (
    <div className="page-heading">
      <div>
        <div className="eyebrow">{eyebrow}</div>
        <h1>{title}</h1>
        <p>{description}</p>
      </div>
      {action}
    </div>
  );
}
export function Stat({
  label,
  value,
  unit,
  note,
  icon,
  tone = "",
}: {
  label: string;
  value: string;
  unit?: string;
  note: string;
  icon: ReactNode;
  tone?: string;
}) {
  return (
    <div className={`stat card ${tone}`}>
      <div className="stat-top">
        <span>{label}</span>
        <span className="stat-icon">{icon}</span>
      </div>
      <div className="stat-value">
        {value}
        <small>{unit}</small>
      </div>
      <div className="stat-note">
        <ArrowUpRight size={14} />
        {note}
      </div>
    </div>
  );
}
export function Tabs({
  items,
  value,
  onChange,
}: {
  items: string[];
  value: string;
  onChange: (v: string) => void;
}) {
  return (
    <div className="tabs" role="group" aria-label="View selection">
      {items.map((i) => (
        <button
          key={i}
          aria-pressed={i === value}
          className={i === value ? "selected" : ""}
          onClick={() => onChange(i)}
        >
          {i}
        </button>
      ))}
    </div>
  );
}
export function Modal({
  title,
  children,
  onClose,
}: {
  title: string;
  children: ReactNode;
  onClose: () => void;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const el = ref.current;
    el?.showModal();
    return () => el?.close();
  }, []);
  return (
    <dialog
      ref={ref}
      onCancel={onClose}
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div className="modal-heading">
        <h2>{title}</h2>
        <button
          className="icon-button"
          aria-label="Close dialog"
          onClick={onClose}
        >
          <X size={20} />
        </button>
      </div>
      {children}
    </dialog>
  );
}
export function Note({ children }: { children: ReactNode }) {
  return <div className="note">{children}</div>;
}
