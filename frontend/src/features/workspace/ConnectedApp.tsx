import { useEffect, useState } from "react";
import { NavLink, Navigate, useLocation } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Zap,
  Sun,
  ArrowLeftRight,
  Wallet,
  Network,
  LogOut,
  ShieldCheck,
  Menu,
  X,
  Users,
  ChartNoAxesCombined,
  Settings,
  Layers,
  ChevronRight,
  RefreshCw,
} from "lucide-react";
import { ApiError, subscribeWorkspace, workspaceRequest } from "../../lib/api";
import { Avatar, stamp } from "./ui";
import { AuthPage, ProfilePage } from "./Profile";
import {
  EnergyPage,
  ForecastPage,
  TradesPage,
  SettlementsPage,
  AuditPage,
} from "./EnergyPages";
import { CommunityPage, GridPage } from "./Community";
import { MarketplacePage } from "./Marketplace";
import { Assistant } from "./Assistant";
import type { Experience, Perform } from "./types";
import "./workspace.css";
import "./experience.css";

const navigation = [
  {
    label: "YOUR HOME",
    items: [
      ["/energy", "My energy", Sun],
      ["/forecasts", "Forecasts", ChartNoAxesCombined],
    ],
  },
  {
    label: "SHARE & EARN",
    items: [
      ["/market", "Marketplace", ArrowLeftRight],
      ["/trades", "My trades", Layers],
      ["/settlements", "Settlements", Wallet],
      ["/audit", "Blockchain receipts", ShieldCheck],
    ],
  },
  {
    label: "YOUR NEIGHBOURHOOD",
    items: [
      ["/community", "Community", Users],
      ["/grid", "Grid monitor", Network],
    ],
  },
] as const;
const titles: Record<string, string> = {
  "/energy": "My energy",
  "/forecasts": "Forecasts",
  "/market": "Marketplace",
  "/trades": "My trades",
  "/settlements": "Settlements",
  "/audit": "Blockchain receipts",
  "/community": "Community",
  "/grid": "Grid monitor",
  "/settings": "Profile & settings",
};

export default function ConnectedApp() {
  const qc = useQueryClient();
  const location = useLocation();
  const [pending, setPending] = useState(false);
  const [feedback, setFeedback] = useState("");
  const [failure, setFailure] = useState(false);
  const [connection, setConnection] = useState("Connecting");
  const [menu, setMenu] = useState(false);
  const query = useQuery<Experience | null>({
    queryKey: ["workspace", "dashboard"],
    queryFn: () => workspaceRequest<Experience>("/workspace/dashboard"),
    // An unauthenticated refetch re-enters the loading state and would unmount
    // the signup wizard. Poll only after an account has actually loaded.
    refetchInterval: (query) => (query.state.data?.user ? 5000 : false),
    refetchOnWindowFocus: (query) => Boolean(query.state.data?.user),
    staleTime: 4000,
    retry: (count, error) =>
      !(error instanceof ApiError && error.code === "401") && count < 1,
  });
  const data = query.data;
  useEffect(() => {
    if (!data?.user.id) return;
    return subscribeWorkspace(
      () => void qc.invalidateQueries({ queryKey: ["workspace", "dashboard"] }),
      setConnection,
    );
  }, [data?.user.id, qc]);
  useEffect(() => {
    setMenu(false);
    document.title = `${titles[location.pathname] || "My energy"} · UrjaSetu`;
    window.scrollTo({ top: 0 });
  }, [location.pathname]);
  const perform: Perform = async (path, body, message, method) => {
    setPending(true);
    setFeedback("");
    setFailure(false);
    try {
      await workspaceRequest(path, body, method);
      if (path.startsWith("/auth")) {
        await qc.cancelQueries({ queryKey: ["workspace"] });
        qc.removeQueries({ queryKey: ["workspace"], type: "inactive" });
        qc.setQueryData(["workspace", "dashboard"], null);
      }
      if (path !== "/auth/logout")
        await qc.invalidateQueries({ queryKey: ["workspace"] });
      setFeedback(message || "");
      return true;
    } catch (error) {
      setFailure(true);
      setFeedback(
        error instanceof Error
          ? error.message
          : "The request could not be completed.",
      );
      return false;
    } finally {
      setPending(false);
    }
  };
  const notice = feedback && (
    <div
      className={`uw-feedback ${failure ? "error" : ""}`}
      role={failure ? "alert" : "status"}
    >
      {feedback}
      <button aria-label="Dismiss message" onClick={() => setFeedback("")}>
        <X size={16} />
      </button>
    </div>
  );
  if (query.isPending)
    return (
      <div className="uw-loading">
        <Sun />
        Bringing your energy home…
      </div>
    );
  if (!data || (query.error instanceof ApiError && query.error.code === "401"))
    return (
      <>
        <AuthPage perform={perform} pending={pending} />
        {notice}
        {query.error &&
          !(query.error instanceof ApiError && query.error.code === "401") && (
            <div className="uw-feedback error" role="alert">
              Cannot connect to the energy service.{" "}
              <button onClick={() => void query.refetch()}>
                Retry connection
              </button>
            </div>
          )}
      </>
    );
  const path = location.pathname;
  return (
    <div className="uw-app ux-app">
      <a className="skip-link" href="#workspace-main">
        Skip to content
      </a>
      {menu && (
        <button
          className="ux-sidebar-shade"
          aria-label="Close navigation"
          onClick={() => setMenu(false)}
        />
      )}
      <aside className={`ux-sidebar ${menu ? "open" : ""}`}>
        <NavLink className="uw-brand" to="/energy">
          <span>
            <Zap />
          </span>
          UrjaSetu<span className="ux-brand-dot">.</span>
        </NavLink>
        <button
          className="ux-mobile-close"
          aria-label="Close menu"
          onClick={() => setMenu(false)}
        >
          <X size={18} />
        </button>
        <div className="ux-community-switch">
          <span className="ux-community-mark">
            <Users size={20} />
          </span>
          <div>
            <strong>Gujarat community</strong>
            <small>Your local energy circle</small>
          </div>
        </div>
        <nav aria-label="Main navigation">
          {navigation.map((group) => (
            <div className="ux-nav-group" key={group.label}>
              <small>{group.label}</small>
              {group.items.map(([url, label, Icon]) => (
                <NavLink key={url} to={url}>
                  <Icon size={19} />
                  <span>{label}</span>
                  {url === "/market" && data.order_book.length > 0 && (
                    <b>{data.order_book.length}</b>
                  )}
                </NavLink>
              ))}
            </div>
          ))}
        </nav>
        <div className="ux-sidebar-bottom">
          <div className="ux-sidebar-note">
            <Sun />
            <strong>Good energy travels.</strong>
            <small>Share a little. Change a lot.</small>
          </div>
          <NavLink to="/settings" className="ux-settings-link">
            <Settings size={18} />
            Profile & settings
          </NavLink>
          <div className="ux-user-slot">
            <NavLink to="/settings">
              <Avatar name={data.user.name} src={data.profile.avatar} />
              <span>
                <strong>{data.user.name}</strong>
                <small>{data.user.role}</small>
              </span>
              <ChevronRight size={15} />
            </NavLink>
            <button
              aria-label="Sign out"
              title="Sign out"
              disabled={pending}
              onClick={() => void perform("/auth/logout", {})}
            >
              <LogOut size={17} />
            </button>
          </div>
        </div>
      </aside>
      <div className="ux-workspace">
        <header className="ux-topbar">
          <button
            className="ux-menu-toggle"
            aria-label="Open menu"
            onClick={() => setMenu(true)}
          >
            <Menu size={21} />
          </button>
          <div className="ux-breadcrumb">
            My community
            <ChevronRight size={13} />
            <strong>{titles[path] || "My energy"}</strong>
          </div>
          <div className="ux-topbar-right">
            <span
              className={
                connection === "Connected" && !query.isError
                  ? "ux-live-dot"
                  : "ux-offline"
              }
            >
              {query.isError
                ? "Update interrupted"
                : connection === "Connected"
                  ? "Live · 5s updates"
                  : connection}
            </span>
            <span className="ux-header-clock">{stamp(data.as_of)} IST</span>
            <button
              aria-label="Refresh dashboard"
              onClick={() =>
                void qc.invalidateQueries({ queryKey: ["workspace"] })
              }
            >
              <RefreshCw size={16} />
            </button>
            <NavLink to="/settings" aria-label="Open your profile">
              <Avatar name={data.user.name} src={data.profile.avatar} />
            </NavLink>
          </div>
        </header>
        <main id="workspace-main" className="ux-main">
          {query.isError && (
            <p role="alert" className="uw-inline-error">
              Updates are interrupted. Showing the last received readings.
            </p>
          )}
          {path === "/" && <Navigate to="/energy" replace />}
          {path === "/energy" && <EnergyPage data={data} />}{" "}
          {path === "/forecasts" && <ForecastPage data={data} />}{" "}
          {path === "/market" && (
            <MarketplacePage data={data} perform={perform} pending={pending} />
          )}{" "}
          {path === "/trades" && <TradesPage data={data} />}{" "}
          {path === "/settlements" && <SettlementsPage data={data} />}{" "}
          {path === "/audit" && <AuditPage data={data} />}{" "}
          {path === "/community" && <CommunityPage data={data} />}{" "}
          {path === "/grid" && <GridPage data={data} />}{" "}
          {path === "/settings" && (
            <ProfilePage
              key={data.user.id}
              data={data}
              perform={perform}
              pending={pending}
            />
          )}{" "}
          {!titles[path] && path !== "/" && <Navigate to="/energy" replace />}
          <footer className="ux-footer">
            <span>Made for a brighter neighbourhood.</span>
            <span>All times in IST · Energy in kWh · Power in kW</span>
          </footer>
        </main>
      </div>
      <Assistant key={data.user.id} />
      {notice}
    </div>
  );
}
