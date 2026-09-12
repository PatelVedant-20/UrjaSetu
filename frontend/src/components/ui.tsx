import { useEffect, useRef, useState } from "react";
import type { ReactNode } from "react";
import { useReducedMotion } from "motion/react";
import {
  X,
  ArrowUpRight,
  ChevronDown,
  ChevronUp,
  Sun,
  ShieldCheck,
  Clock,
} from "lucide-react";

export function ScrollProgressBar() {
  const [scroll, setScroll] = useState(0);
  useEffect(() => {
    const handleScroll = () => {
      const total = document.documentElement.scrollHeight - window.innerHeight;
      if (total > 0) {
        setScroll(Math.min(100, Math.max(0, (window.scrollY / total) * 100)));
      }
    };
    window.addEventListener("scroll", handleScroll, { passive: true });
    return () => window.removeEventListener("scroll", handleScroll);
  }, []);
  return (
    <div
      className="scroll-progress-bar"
      style={{ width: `${scroll}%` }}
      aria-hidden="true"
    />
  );
}

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
  showSnapshot = true,
}: {
  eyebrow: string;
  title: string;
  description: string;
  action?: ReactNode;
  showSnapshot?: boolean;
}) {
  const [expanded, setExpanded] = useState(false);

  return (
    <div className="header-wrapper">
      <ScrollProgressBar />
      <div className="page-heading">
        <div>
          <div className="eyebrow">{eyebrow}</div>
          <h1>{title}</h1>
          <p>{description}</p>
        </div>
        <div className="header-actions">
          {action}
          {showSnapshot && (
            <button
              type="button"
              className="header-pulse-btn"
              onClick={() => setExpanded(!expanded)}
              aria-expanded={expanded}
              aria-label="Toggle community health and grid snapshot"
            >
              <span className="pulse-indicator" />
              <span>Community Snapshot</span>
              {expanded ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
            </button>
          )}
        </div>
      </div>

      {showSnapshot && expanded && (
        <div
          className="header-snapshot-panel"
          role="region"
          aria-label="Community snapshot"
        >
          <div className="snapshot-card">
            <div className="snapshot-icon">
              <ShieldCheck size={18} color="#2e7d32" />
            </div>
            <div>
              <small>FEEDER STABILITY</small>
              <strong>99.4% · Normal</strong>
              <span>Voltage 0.99 pu · Feeder A</span>
            </div>
          </div>

          <div className="snapshot-card">
            <div className="snapshot-icon">
              <Sun size={18} color="#e65100" />
            </div>
            <div>
              <small>SOLAR IRRADIANCE</small>
              <strong>850 W/m² · Clear Sky</strong>
              <span>Peak solar factor · UV 7.8</span>
            </div>
          </div>

          <div className="snapshot-card">
            <div className="snapshot-icon">
              <Clock size={18} color="#00838f" />
            </div>
            <div>
              <small>DAY-AHEAD WINDOW</small>
              <strong>12:00–13:00 IST</strong>
              <span>Next clearing session: 18:00</span>
            </div>
          </div>
        </div>
      )}
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

export function AnimatedCounter({
  target,
  duration = 950,
  decimals = 1,
  prefix = "",
  suffix = "",
}: {
  target: number;
  duration?: number;
  decimals?: number;
  prefix?: string;
  suffix?: string;
}) {
  const reducedMotion = useReducedMotion();
  const [val, setVal] = useState(reducedMotion ? target : 0);

  useEffect(() => {
    if (reducedMotion) {
      setVal(target);
      return;
    }
    let startTimestamp: number | null = null;
    const startVal = 0;
    let animId: number;

    const step = (timestamp: number) => {
      if (!startTimestamp) startTimestamp = timestamp;
      const progress = Math.min((timestamp - startTimestamp) / duration, 1);
      // cubic ease-out
      const ease = 1 - Math.pow(1 - progress, 3);
      setVal(startVal + (target - startVal) * ease);
      if (progress < 1) {
        animId = requestAnimationFrame(step);
      }
    };

    animId = requestAnimationFrame(step);
    return () => cancelAnimationFrame(animId);
  }, [target, duration, reducedMotion]);

  return (
    <span>
      {prefix}
      {val.toFixed(decimals)}
      {suffix}
    </span>
  );
}
