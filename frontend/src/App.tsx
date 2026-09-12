import { lazy, Suspense, useState, useEffect, useRef } from "react";
import { NavLink, Route, Routes, useLocation, Link } from "react-router-dom";
import { MotionConfig, motion, AnimatePresence } from "motion/react";
import {
  LayoutDashboard,
  ArrowLeftRight,
  Layers,
  Sun,
  ChartNoAxesCombined,
  Network,
  Users,
  Wallet,
  ScrollText,
  Settings,
  Zap,
  ArrowUpRight,
  Menu,
  X,
  ChevronRight,
  HelpCircle,
  Radio,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { Modal } from "./components/ui";
import { readConnection, subscribe } from "./lib/api";

const Overview = lazy(() => import("./features/overview/OverviewPage"));
const Market = lazy(() => import("./features/market/MarketPage"));
const Trades = lazy(() => import("./features/trades/TradesPage"));
const Energy = lazy(() => import("./features/energy/EnergyPage"));
const Forecasts = lazy(() => import("./features/forecasts/ForecastsPage"));
const Grid = lazy(() => import("./features/grid/GridPage"));
const Community = lazy(() => import("./features/community/CommunityPage"));
const Settlements = lazy(
  () => import("./features/settlements/SettlementsPage"),
);
const Audit = lazy(() => import("./features/audit/AuditPage"));
const SettingsPage = lazy(() => import("./features/settings/SettingsPage"));

const links: {
  path: string;
  label: string;
  icon: LucideIcon;
  group: string;
}[] = [
  { path: "/", label: "Overview", icon: LayoutDashboard, group: "WORKSPACE" },
  { path: "/market", label: "Marketplace", icon: ArrowLeftRight, group: "" },
  { path: "/trades", label: "My trades", icon: Layers, group: "" },
  { path: "/energy", label: "My energy", icon: Sun, group: "INTELLIGENCE" },
  {
    path: "/forecasts",
    label: "Forecasts",
    icon: ChartNoAxesCombined,
    group: "",
  },
  { path: "/grid", label: "Grid monitor", icon: Network, group: "" },
  { path: "/community", label: "Community", icon: Users, group: "COMMUNITY" },
  { path: "/settlements", label: "Settlements", icon: Wallet, group: "" },
  { path: "/audit", label: "Audit trail", icon: ScrollText, group: "" },
];

export interface ToastItem {
  id: string;
  title: string;
  message: string;
  channel: string;
  time: string;
}

export default function App() {
  const [menu, setMenu] = useState(false);
  const [help, setHelp] = useState(false);
  const [toasts, setToasts] = useState<ToastItem[]>([]);
  const [wsStatus, setWsStatus] = useState("Standby");
  const location = useLocation();

  const current =
    links.find((l) => l.path === location.pathname)?.label ||
    (location.pathname === "/settings" ? "Settings" : "Page not found");

  useEffect(() => {
    setMenu(false);
    document.title = `${current} · UrjaSetu`;
    window.scrollTo(0, 0);
    document.getElementById("main")?.focus();
  }, [location.pathname, current]);

  // Realtime WebSocket hub connection with toast notification feed
  const connRef = useRef(readConnection());
  useEffect(() => {
    const conn = connRef.current;
    if (!conn.userId) {
      setWsStatus("Demo Standby");
      return;
    }

    const activeId = conn.userId;

    const addToast = (title: string, message: string, channel: string) => {
      const id = `${Date.now()}-${Math.random().toString(36).slice(2, 6)}`;
      const time = new Date().toLocaleTimeString("en-IN", {
        hour: "2-digit",
        minute: "2-digit",
      });
      setToasts((prev) => [
        ...prev.slice(-3),
        { id, title, message, channel, time },
      ]);
      setTimeout(() => {
        setToasts((prev) => prev.filter((t) => t.id !== id));
      }, 5000);
    };

    const cleanupMarket = subscribe(
      "market",
      activeId,
      () => {
        addToast(
          "Market Session Updated",
          "A day-ahead order book or clearing event was broadcast.",
          "market",
        );
      },
      (status) => setWsStatus(status),
    );

    const cleanupGrid = subscribe(
      "grid",
      activeId,
      () => {
        addToast(
          "Grid State Refresh",
          "Feeder telemetry or power-flow state has been validated.",
          "grid",
        );
      },
      () => {},
    );

    return () => {
      cleanupMarket();
      cleanupGrid();
    };
  }, []);

  return (
    <MotionConfig reducedMotion="user">
      <a className="skip-link" href="#main">
        Skip to content
      </a>

      {menu && (
        <button
          className="sidebar-backdrop"
          aria-label="Close navigation"
          onClick={() => setMenu(false)}
        />
      )}

      <aside className={`sidebar ${menu ? "open" : ""}`}>
        <Link className="brand" to="/">
          <span className="brand-mark">
            <Zap size={22} fill="currentColor" />
          </span>
          <span>
            UrjaSetu<small>GOOD ENERGY. TOGETHER.</small>
          </span>
        </Link>

        <button className="community-switch" onClick={() => setHelp(true)}>
          <span className="community-symbol">
            <Users size={18} />
          </span>
          <span>
            Ahmedabad community<small>Hackathon workspace</small>
          </span>
          <ChevronRight size={15} />
        </button>

        <nav aria-label="Main navigation">
          {links.map(({ path, label, icon: Icon, group }) => (
            <div key={path}>
              {group && <div className="nav-group">{group}</div>}
              <NavLink to={path} end={path === "/"}>
                <Icon size={18} />
                {label}
                {path === "/market" && <span className="nav-pill">NEW</span>}
              </NavLink>
            </div>
          ))}
        </nav>

        <div className="sidebar-bottom">
          <div className="sidebar-callout">
            <span>SMALL ACTIONS. SHARED IMPACT.</span>
            <p>
              Your sunshine could be
              <br />
              someone’s brighter day.
            </p>
            <Link to="/market">
              Find your opportunity <ArrowUpRight size={15} />
            </Link>
          </div>

          <NavLink className="settings-link" to="/settings">
            <Settings size={18} />
            Settings
          </NavLink>

          <Link className="profile" to="/settings">
            <span className="avatar">YS</span>
            <span>
              Your workspace<small>Community demo</small>
            </span>
            <ChevronRight size={16} />
          </Link>
        </div>
      </aside>

      <div className="workspace">
        <header className="topbar">
          <div className="breadcrumb">
            <button
              className="icon-button mobile-toggle"
              aria-label="Toggle navigation"
              aria-expanded={menu}
              onClick={() => setMenu(!menu)}
            >
              {menu ? <X size={20} /> : <Menu size={20} />}
            </button>
            <span>Workspace</span>
            <ChevronRight size={13} />
            <strong>{current}</strong>
          </div>

          <div className="topbar-right">
            <span className="live-peer-pill" title={`WebSocket: ${wsStatus}`}>
              <span className="pulse-indicator" />
              <span>Peer Sync</span>
            </span>

            <span className="demo-label">
              <span className="status-dot" /> Illustrative demo
            </span>

            <span className="topbar-divider" />

            <button
              className="icon-button"
              aria-label="About this workspace"
              onClick={() => setHelp(true)}
            >
              <HelpCircle size={19} />
            </button>

            <Link
              to="/settings"
              className="avatar small"
              aria-label="Open profile settings"
            >
              YS
            </Link>
          </div>
        </header>

        <main id="main" tabIndex={-1}>
          <div className="demo-notice">
            <span>COMMUNITY PREVIEW</span> Sample data, real possibilities. All
            dashboard figures are illustrative.
            <Link to="/settings">
              API connection <ArrowUpRight size={13} />
            </Link>
          </div>

          <Suspense
            fallback={
              <div className="loading" role="status">
                Opening your workspace…
              </div>
            }
          >
            <motion.div
              key={location.pathname}
              initial={{ opacity: 0, y: 6 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.2 }}
              className="page-content"
            >
              <Routes>
                <Route path="/" element={<Overview />} />
                <Route path="/market" element={<Market />} />
                <Route path="/trades" element={<Trades />} />
                <Route path="/energy" element={<Energy />} />
                <Route path="/forecasts" element={<Forecasts />} />
                <Route path="/grid" element={<Grid />} />
                <Route path="/community" element={<Community />} />
                <Route path="/settlements" element={<Settlements />} />
                <Route path="/audit" element={<Audit />} />
                <Route path="/settings" element={<SettingsPage />} />
                <Route
                  path="*"
                  element={
                    <div className="empty">
                      <h1>This page isn’t here yet.</h1>
                      <Link to="/">Return to overview →</Link>
                    </div>
                  }
                />
              </Routes>
            </motion.div>
          </Suspense>

          <footer>
            <span>
              UrjaSetu <span className="footer-dot">·</span> Energy connects us.
            </span>
            <span>
              Hackathon prototype <span className="footer-dot">·</span>{" "}
              Asia/Kolkata
            </span>
          </footer>
        </main>
      </div>

      {/* Floating Realtime WebSocket Notifications Toast Container */}
      <div className="toast-container" aria-live="polite">
        <AnimatePresence>
          {toasts.map((t) => (
            <motion.div
              key={t.id}
              initial={{ opacity: 0, y: 16, scale: 0.95 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={{ opacity: 0, scale: 0.9, y: 8 }}
              transition={{ duration: 0.22 }}
              className="toast"
            >
              <div className="toast-top">
                <Radio size={13} color="#2e7d32" />
                <strong>{t.title}</strong>
                <small>{t.time}</small>
                <button
                  className="toast-close"
                  onClick={() =>
                    setToasts((prev) => prev.filter((x) => x.id !== t.id))
                  }
                  aria-label="Close notification"
                >
                  <X size={12} />
                </button>
              </div>
              <p>{t.message}</p>
            </motion.div>
          ))}
        </AnimatePresence>
      </div>

      {help && (
        <Modal
          title="A community powered by possibility"
          onClose={() => setHelp(false)}
        >
          <p className="body-copy">
            UrjaSetu is a grid-aware local renewable-energy marketplace. This
            initial frontend lets your team explore the complete energy journey
            with clearly labeled sample data.
          </p>
          <p className="body-copy">
            The community selector represents one illustrative Ahmedabad feeder.
            Physical energy stays on the existing DISCOM network. Use Settings
            to inspect real backend records.
          </p>
          <Link
            className="button primary"
            to="/settings"
            onClick={() => setHelp(false)}
          >
            Open connection settings <ArrowUpRight size={16} />
          </Link>
        </Modal>
      )}
    </MotionConfig>
  );
}
