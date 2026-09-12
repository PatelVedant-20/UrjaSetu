import { memo } from "react";
import {
  Handshake,
  Zap,
  Tag,
  FileCheck2,
  ArrowRight,
  ShieldCheck,
  ShieldAlert,
  HelpCircle,
} from "lucide-react";
import type { GridScenario } from "./gridData";

interface GridLifecycleStepperProps {
  scenario: GridScenario;
}

function GridLifecycleStepperComponent({
  scenario,
}: GridLifecycleStepperProps) {
  const isUnknown = scenario === "Missing data";
  const isCongested = scenario === "Congestion";

  const gridStepStatus = isUnknown
    ? "blocked"
    : isCongested
      ? "warning"
      : "passed";

  const gridStepBadge = isUnknown
    ? "Safety Blocked"
    : isCongested
      ? "Congestion Flagged"
      : "Clearance Granted";

  const gridStepExplanation = isUnknown
    ? "Observability blackout. Missing meter telemetry prevents thermal or voltage verification. Trade cannot proceed to physical execution."
    : isCongested
      ? "Transformer thermal rating exceeded (108% load) or voltage sag below 0.95 pu. Dispatch curtailed to preserve equipment life."
      : "All feeders <80% thermal rating and nodal voltages safely in 0.95–1.05 pu band. Physical delivery approved.";

  const steps = [
    {
      step: 1,
      name: "Order Matched",
      emoji: "🤝",
      icon: Handshake,
      badge: "Market Clearing",
      badgeTone: "step-badge-blue",
      desc: "Double-sided auction pairs buyer and seller orders at uniform clearing price.",
      statusText: "Cleared",
      isGridGate: false,
    },
    {
      step: 2,
      name: "Power Grid Validated",
      emoji: "⚡",
      icon: Zap,
      badge: gridStepBadge,
      badgeTone:
        gridStepStatus === "passed"
          ? "step-badge-green"
          : gridStepStatus === "warning"
            ? "step-badge-amber"
            : "step-badge-gray",
      desc: gridStepExplanation,
      statusText: isUnknown ? "Unknown" : isCongested ? "Unsafe" : "Safe",
      isGridGate: true,
    },
    {
      step: 3,
      name: "Dynamic Price Quoted",
      emoji: "🏷️",
      icon: Tag,
      badge: isCongested ? "Congestion Premium" : "Marginal Loss + Wheeling",
      badgeTone: isCongested ? "step-badge-amber" : "step-badge-green",
      desc: "Clearing price adjusted for physical line losses, wheeling charges, and grid node congestion.",
      statusText: isUnknown
        ? "Estimated"
        : isCongested
          ? "Surcharged"
          : "Optimal",
      isGridGate: false,
    },
    {
      step: 4,
      name: "Settlement Reconciled",
      emoji: "📝",
      icon: FileCheck2,
      badge: "Tamper-Evident Ledger",
      badgeTone: "step-badge-purple",
      desc: "Smart meter telemetry verified against committed dispatch before rupee transfer occurs.",
      statusText: "Audited",
      isGridGate: false,
    },
  ];

  return (
    <div className="lifecycle-stepper-card">
      <div className="lifecycle-stepper-header">
        <div className="lifecycle-stepper-title-area">
          <div className="lifecycle-eyebrow">PHYSICAL DISPATCH LIFECYCLE</div>
          <h3>Why Matching Alone Cannot Deliver Power</h3>
          <p>
            An order match is strictly an economic contract. Physical
            electricity travels through the utility network according to
            Kirchhoff's laws. See how the grid validation gate protects the
            community.
          </p>
        </div>

        <div className="lifecycle-grid-badge">
          {gridStepStatus === "passed" && (
            <span className="lifecycle-status-pill green">
              <ShieldCheck size={13} />
              Gate Status: All Clear (Safe)
            </span>
          )}
          {gridStepStatus === "warning" && (
            <span className="lifecycle-status-pill amber">
              <ShieldAlert size={13} />
              Gate Status: Thermal Overload (Unsafe)
            </span>
          )}
          {gridStepStatus === "blocked" && (
            <span className="lifecycle-status-pill gray">
              <HelpCircle size={13} />
              Gate Status: Missing Data (Unknown)
            </span>
          )}
        </div>
      </div>

      <div className="lifecycle-pipeline">
        {steps.map((stepItem, idx) => {
          const IconComp = stepItem.icon;
          const isHighlighted = stepItem.isGridGate;

          return (
            <div
              key={stepItem.step}
              className={`pipeline-step ${isHighlighted ? "pipeline-step-active" : ""}`}
            >
              <div className="pipeline-step-top">
                <div
                  className={`step-icon-wrap ${isHighlighted ? `highlight-${gridStepStatus}` : ""}`}
                >
                  <IconComp size={16} />
                </div>
                <span className="step-counter">STEP 0{stepItem.step}</span>
                <span className={`step-badge ${stepItem.badgeTone}`}>
                  {stepItem.badge}
                </span>
              </div>

              <div className="pipeline-step-title">
                <span className="step-emoji">{stepItem.emoji}</span>
                <strong>{stepItem.name}</strong>
              </div>

              <p className="pipeline-step-desc">{stepItem.desc}</p>

              {isHighlighted && (
                <div className={`pipeline-gate-callout gate-${gridStepStatus}`}>
                  <span className="gate-label">THE PHYSICAL GATE:</span>
                  <span>
                    {isUnknown
                      ? "Zero synthetic assumptions — unmeasured grid state blocks settlement."
                      : isCongested
                        ? "108% transformer loading detected. Trade dispatch throttled."
                        : "Verified safe capacity headroom. Proceed to dynamic pricing."}
                  </span>
                </div>
              )}

              {idx < steps.length - 1 && (
                <div className="pipeline-connector-arrow" aria-hidden="true">
                  <ArrowRight size={14} />
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

export const GridLifecycleStepper = memo(GridLifecycleStepperComponent);
