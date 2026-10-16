import { NativeViews, NativeStats } from "./NativeViews";
import {
  useEffect,
  useMemo,
  useRef,
  useState,
  useSyncExternalStore,
  type FormEvent,
} from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  useReactTable,
  getCoreRowModel,
  getSortedRowModel,
  flexRender,
  type ColumnDef,
  type SortingState,
} from "@tanstack/react-table";
import { useVirtualizer } from "@tanstack/react-virtual";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import {
  Activity,
  ArrowDownToLine,
  ArrowRight,
  ArrowUpRight,
  Bell,
  BookOpen,
  Box,
  Check,
  ChevronDown,
  ChevronRight,
  CircleHelp,
  FileText,
  FlaskConical,
  GitCompareArrows,
  Layers,
  LayoutDashboard,
  LogOut,
  MemoryStick,
  PanelLeftClose,
  Pause,
  Play,
  Plus,
  Radio,
  Search,
  Server,
  Settings as SettingsIcon,
  ShieldCheck,
  Square,
  Terminal,
  Waypoints,
} from "lucide-react";
import {
  api,
  raw,
  download,
  bytes,
  type Page,
  type Process,
  type Session,
  type Timeline,
  type Summary,
} from "./api";
import { useT, useUI } from "./store";
import type { Key, Locale } from "./i18n";
import {
  Badge,
  Capability,
  Chart,
  Empty,
  Failure,
  Loading,
  Metric,
  Modal,
} from "./components";

const nav = [
  { key: "overview", icon: LayoutDashboard },
  { key: "processes", icon: Layers },
  { key: "sessions", icon: Radio },
  { key: "investigations", icon: Waypoints },
  { key: "comparisons", icon: GitCompareArrows },
  { key: "reports", icon: FileText },
  { key: "settings", icon: SettingsIcon },
] as const;
const navigate = (path: string) => {
  location.hash = "/" + path;
};
const subscribe = (fn: () => void) => {
  window.addEventListener("hashchange", fn);
  return () => window.removeEventListener("hashchange", fn);
};
function useRoute() {
  return useSyncExternalStore(
    subscribe,
    () => location.hash.slice(2) || "overview",
  );
}
const useSessions = () =>
  useQuery({
    queryKey: ["sessions"],
    queryFn: () => api<Page<Session>>("/sessions?limit=200"),
    refetchInterval: 5000,
  });
function useHosts() {
  return useQuery({
    queryKey: ["hosts"],
    queryFn: () =>
      api<Page<{ id: string; name: string; imported?: boolean }>>("/hosts"),
    refetchInterval: 15000,
  });
}
function useProcesses(host?: string) {
  return useQuery({
    queryKey: ["processes", host],
    queryFn: () => api<Page<Process>>(`/hosts/${host}/processes?limit=2000`),
    enabled: !!host,
    refetchInterval: 5000,
  });
}
function useAction() {
  const notify = useUI((s) => s.notify);
  const t = useT();
  const client = useQueryClient();
  return useMutation({
    mutationFn: async ({ path, body }: { path: string; body?: unknown }) =>
      api<Record<string, unknown>>(path, {
        method: "POST",
        ...(body ? { body: JSON.stringify(body) } : {}),
      }),
    onSuccess: () => {
      notify(t("saved"));
      void client.invalidateQueries();
    },
    onError: (e) => notify(e.message),
  });
}

export default function App() {
  const { token, setToken, locale, theme } = useUI();
  const me = useQuery({
    queryKey: ["me", token],
    queryFn: () => api<{ role: string }>("/me"),
    enabled: !!token,
    retry: false,
  });
  useEffect(() => {
    const media = matchMedia("(prefers-color-scheme: dark)");
    const update = () => {
      document.documentElement.dataset.theme =
        theme === "system" ? (media.matches ? "dark" : "light") : theme;
    };
    update();
    media.addEventListener("change", update);
    return () => media.removeEventListener("change", update);
  }, [theme]);
  useEffect(() => {
    document.documentElement.lang = locale;
  }, [locale]);
  if (!token || me.isError)
    return <Login error={me.error} connect={setToken} />;
  if (!me.data) return <Loading />;
  return <Shell role={me.data.role} />;
}
function Login({
  error,
  connect,
}: {
  error: unknown;
  connect: (v: string) => void;
}) {
  const t = useT();
  const [value, setValue] = useState("");
  return (
    <main className="login">
      <div className="login-brand">
        <span className="logo">
          <Activity />
        </span>
        LeakScope<span className="version">0.1</span>
      </div>
      <div className="login-card">
        <div className="eyebrow">LOCAL MEMORY INTELLIGENCE</div>
        <h1>{t("loginTitle")}</h1>
        <p>{t("loginSub")}</p>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            connect(value.trim());
          }}
        >
          <label>
            {t("token")}
            <input
              type="password"
              autoComplete="off"
              value={value}
              onChange={(e) => setValue(e.target.value)}
              required
              minLength={32}
            />
          </label>
          <p className="muted small">{t("tokenHint")}</p>
          {Boolean(error) && <Failure error={error} />}
          <button className="primary wide" type="submit">
            {t("connect")}
            <ArrowRight size={16} />
          </button>
        </form>
        <div className="login-footer">
          <ShieldCheck size={16} />
          {t("privacy")}
        </div>
      </div>
    </main>
  );
}

function Shell({ role }: { role: string }) {
  const t = useT();
  const route = useRoute();
  const current = route.split(/[/?]/)[0];
  const ui = useUI();
  const client = useQueryClient();
  const hosts = useHosts();
  const [host, setHost] = useState("");
  const selectedHost = host || hosts.data?.items.find((h) => !h.imported)?.id;
  const processes = useProcesses(selectedHost);
  const sessions = useSessions();
  const [wizard, setWizard] = useState<Process | null>(null);
  const [command, setCommand] = useState(false);
  const [help, setHelp] = useState(false);
  const [notifications, setNotifications] = useState(false);
  const [search, setSearch] = useState("");
  const [stream, setStream] = useState(false);
  const canOperate = ["operator", "admin"].includes(role);
  useEffect(() => {
    const fn = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key === "k") {
        e.preventDefault();
        setCommand((v) => !v);
        return;
      }
      if (
        (e.target as HTMLElement).matches(
          "input,textarea,select,[contenteditable]",
        )
      )
        return;
      if (e.key === "?") setHelp(true);
      if (e.key === "g") navigate("overview");
      if (e.key === "p") navigate("processes");
      if (e.key === "s") navigate("sessions");
    };
    window.addEventListener("keydown", fn);
    return () => window.removeEventListener("keydown", fn);
  }, []);
  useEffect(() => {
    const controller = new AbortController();
    async function listen() {
      while (!controller.signal.aborted) {
        try {
          const response = await raw("/events/stream", {
            signal: controller.signal,
          });
          if (!response.body) break;
          setStream(true);
          const reader = response.body.getReader();
          const decoder = new TextDecoder();
          let buffer = "";
          while (!controller.signal.aborted) {
            const { done, value } = await reader.read();
            if (done) break;
            buffer += decoder.decode(value, { stream: true });
            if (buffer.length > 256000)
              throw new Error("SSE frame exceeds limit");
            let end;
            while ((end = buffer.indexOf("\n\n")) >= 0) {
              const block = buffer.slice(0, end);
              buffer = buffer.slice(end + 2);
              const line = block
                .split("\n")
                .find((l) => l.startsWith("data: "));
              if (line) {
                const payload = JSON.parse(line.slice(6));
                client.setQueryData(["sessions"], {
                  items: payload.sessions,
                  next_cursor: null,
                });
                void client.invalidateQueries({ queryKey: ["timeline"] });
              }
            }
          }
        } catch {
          setStream(false);
        }
        if (!controller.signal.aborted) {
          setStream(false);
          await new Promise((r) => setTimeout(r, 1500));
        }
      }
    }
    void listen();
    return () => controller.abort();
  }, [client]);
  useEffect(() => {
    if (!ui.notice) return;
    const id = setTimeout(() => ui.notify(""), 6000);
    return () => clearTimeout(id);
  }, [ui.notice, ui.notify]);
  const active =
    sessions.data?.items.filter((s) => s.state === "recording").length || 0;
  const latest = sessions.data?.items.toSorted(
    (a, b) => b.created_at - a.created_at,
  )[0];
  function diagnose(p?: Process) {
    if (p) {
      setWizard(p);
      return;
    }
    navigate("processes");
  }
  return (
    <div className={"app " + (ui.collapsed ? "collapsed" : "")}>
      <aside className="sidebar">
        <a className="brand" href="#/overview">
          <span className="logo">
            <Activity size={23} />
          </span>
          <span className="brand-name">
            LeakScope<span className="version">0.1</span>
          </span>
        </a>
        <div className="workspace-box">
          <span className="host-icon">
            <Server size={16} />
          </span>
          <div>
            <strong>{t("localHost")}</strong>
            <small>
              <span className={"dot " + (stream ? "online" : "")} />
              {stream ? t("connected") : t("disconnected")}
            </small>
          </div>
          <ChevronDown size={14} />
        </div>
        <p className="nav-label">{t("workspace")}</p>
        <nav aria-label={t("workspace")}>
          {nav.slice(0, 6).map((n) => (
            <a
              key={n.key}
              href={"#/" + n.key}
              className={
                current === n.key ||
                (current === "session" && n.key === "sessions")
                  ? "active"
                  : ""
              }
              title={t(n.key)}
            >
              <n.icon size={18} />
              <span>{t(n.key)}</span>
              {n.key === "sessions" && active > 0 && <b>{active}</b>}
            </a>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <div className="safety-note">
            <ShieldCheck size={20} />
            <strong>{t("safeDefault")}</strong>
            <p>{t("privacyBody")}</p>
          </div>
          <p className="nav-label">{t("platform")}</p>
          <nav>
            <a
              href="#/settings"
              className={current === "settings" ? "active" : ""}
            >
              <SettingsIcon size={18} />
              <span>{t("settings")}</span>
            </a>
            <button onClick={() => setHelp(true)}>
              <CircleHelp size={18} />
              <span>{t("shortcutHelp")}</span>
              <kbd>?</kbd>
            </button>
          </nav>
          <div className="user">
            <span className="avatar">L</span>
            <div>
              <strong>{t("localHost")}</strong>
              <small>{role}</small>
            </div>
            <button
              className="icon-button"
              aria-label={t("logout")}
              onClick={() => {
                client.clear();
                ui.setToken("");
              }}
            >
              <LogOut size={16} />
            </button>
          </div>
        </div>
      </aside>
      <div className="main-shell">
        <header className="topbar">
          <div className="breadcrumb">
            <button
              className="icon-button"
              aria-label={t("collapse")}
              onClick={() => ui.setCollapsed(!ui.collapsed)}
            >
              <PanelLeftClose size={18} />
            </button>
            <span>LeakScope</span>
            <ChevronRight size={14} />
            <strong>
              {current === "session"
                ? t("session")
                : t(nav.find((n) => n.key === current)?.key || "overview")}
            </strong>
          </div>
          <div className="top-actions">
            <button className="search-command" onClick={() => setCommand(true)}>
              <Search size={15} />
              <span>{t("search")}</span>
              <kbd>⌘ K</kbd>
            </button>
            {active > 0 && (
              <span className="recording-indicator">
                <span className="dot" />
                {active} {t("recording")}
              </span>
            )}
            <button
              className="icon-button"
              aria-label={t("notifications")}
              onClick={() => setNotifications(true)}
            >
              <Bell size={18} />
            </button>
            <select
              aria-label={t("language")}
              value={ui.locale}
              onChange={(e) => ui.setLocale(e.target.value as Locale)}
            >
              <option value="ca">CA</option>
              <option value="es">ES</option>
              <option value="en">EN</option>
            </select>
          </div>
        </header>
        <main className="content" id="main">
          <div className="context-bar">
            <span className="eyebrow">
              <span className={"dot " + (stream ? "online" : "")} />
              {t("localHost")}
              <span className="slash">/</span>
              {t("coverage")}
            </span>
            <select
              className="host-select"
              aria-label={t("hosts")}
              value={selectedHost || ""}
              onChange={(e) => setHost(e.target.value)}
            >
              {hosts.data?.items
                .filter((h) => !h.imported)
                .map((h) => (
                  <option key={h.id} value={h.id}>
                    {h.name}
                  </option>
                ))}
            </select>
          </div>
          {current === "overview" && (
            <Overview
              hosts={hosts.data?.items.length || 0}
              processes={processes.data?.items || []}
              sessions={sessions.data?.items || []}
              connected={stream}
              latest={latest}
              diagnose={diagnose}
              canOperate={canOperate}
            />
          )}
          {current === "processes" && (
            <Processes
              items={processes.data?.items || []}
              loading={processes.isLoading}
              error={processes.error || hosts.error}
              refresh={() => void processes.refetch()}
              diagnose={diagnose}
              canOperate={canOperate}
            />
          )}
          {current === "sessions" && (
            <SessionList
              sessions={sessions.data?.items || []}
              loading={sessions.isLoading}
              error={sessions.error}
              canOperate={canOperate}
            />
          )}
          {current === "session" && (
            <SessionDetail id={route.split("/")[1]} role={role} />
          )}
          {current === "investigations" && (
            <Investigations sessions={sessions.data?.items || []} role={role} />
          )}
          {current === "comparisons" && (
            <Comparisons sessions={sessions.data?.items || []} role={role} />
          )}
          {current === "reports" && (
            <Reports sessions={sessions.data?.items || []} role={role} />
          )}
          {current === "settings" && <Settings role={role} />}
        </main>
        <footer className="app-footer">
          <span>
            <ShieldCheck size={12} />
            {t("privacy")}
          </span>
          <span>
            LeakScope 0.1.0<span className="slash">/</span>Linux · CPython
          </span>
        </footer>
      </div>
      {ui.notice && (
        <div role="status" className="toast">
          <InfoIcon />
          {ui.notice}
          <button
            className="icon-button"
            aria-label={t("close")}
            onClick={() => ui.notify("")}
          >
            ×
          </button>
        </div>
      )}
      {wizard && <Wizard process={wizard} close={() => setWizard(null)} />}
      {command && (
        <Modal title={t("command")} close={() => setCommand(false)}>
          <label className="command-input">
            <Search size={18} />
            <input
              autoFocus
              aria-label={t("search")}
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder={t("search")}
            />
          </label>
          <div className="command-results">
            {nav
              .filter((n) =>
                t(n.key).toLowerCase().includes(search.toLowerCase()),
              )
              .map((n) => (
                <button
                  key={n.key}
                  onClick={() => {
                    navigate(n.key);
                    setCommand(false);
                  }}
                >
                  <n.icon size={18} />
                  {t(n.key)}
                  <ArrowRight size={15} />
                </button>
              ))}
          </div>
        </Modal>
      )}
      {help && (
        <Modal title={t("shortcutHelp")} close={() => setHelp(false)}>
          <p>{t("shortcutText")}</p>
        </Modal>
      )}
      {notifications && (
        <Modal title={t("notifications")} close={() => setNotifications(false)}>
          <Empty title={t("noNotifications")} />
        </Modal>
      )}
    </div>
  );
}
function InfoIcon() {
  return <Activity size={18} />;
}
function PageHead({
  title,
  description,
  children,
}: {
  title: string;
  description: string;
  children?: React.ReactNode;
}) {
  return (
    <div className="page-head">
      <div>
        <h1>{title}</h1>
        <p>{description}</p>
      </div>
      <div className="page-actions">{children}</div>
    </div>
  );
}

function Overview({
  hosts,
  processes,
  sessions,
  connected,
  latest,
  diagnose,
  canOperate,
}: {
  hosts: number;
  processes: Process[];
  sessions: Session[];
  connected: boolean;
  latest?: Session;
  diagnose: (p?: Process) => void;
  canOperate: boolean;
}) {
  const t = useT();
  const q = useQuery({
    queryKey: ["timeline", latest?.id],
    queryFn: () => api<Timeline>(`/sessions/${latest!.id}/timeline`),
    enabled: !!latest,
  });
  const python = processes.filter(
    (p) =>
      p.python_version || p.worker_type === "uwsgi" || p.worker_type === "rq",
  );
  return (
    <>
      <PageHead title={t("welcome")} description={t("overviewSub")}>
        {canOperate && (
          <button className="primary" onClick={() => diagnose()}>
            <Plus size={17} />
            {t("diagnose")}
          </button>
        )}
      </PageHead>
      <div className="metrics-grid">
        <Metric
          label={t("hosts")}
          value={hosts.toString().padStart(2, "0")}
          hint={t("localHost")}
          icon={<Server size={17} />}
        />
        <Metric
          label={t("pythonProcesses")}
          value={python.length.toString().padStart(2, "0")}
          hint={t("runningProcesses")}
          icon={<Box size={17} />}
        />
        <Metric
          label={t("activeSessions")}
          value={sessions
            .filter((s) => s.state === "recording")
            .length.toString()
            .padStart(2, "0")}
          hint={t("safeDefault")}
          icon={<Radio size={17} />}
        />
        <Metric
          label={t("sensor")}
          value={
            <span className="sensor-value">
              <span className={"dot " + (connected ? "online" : "")} />
              {connected ? t("connected") : t("disconnected")}
            </span>
          }
          hint={t("metricsOnly")}
          icon={<Activity size={17} />}
        />
      </div>
      <Capability />
      <div className="overview-grid">
        <section className="panel">
          <div className="panel-head">
            <div>
              <h2>{t("memoryTrend")}</h2>
              <p>{t("memorySub")}</p>
            </div>
            {latest && (
              <button
                className="text-button"
                onClick={() => navigate("session/" + latest.id)}
              >
                {t("lastCapture")}
                <ArrowUpRight size={15} />
              </button>
            )}
          </div>
          {q.isError ? (
            <Failure error={q.error} />
          ) : (
            <Chart samples={q.data?.items || []} />
          )}
        </section>
        <section className="panel collection">
          <div className="panel-head">
            <h2>{t("evidence")}</h2>
            <ShieldCheck size={18} />
          </div>
          <div className="evidence-icon">
            <Waypoints size={36} strokeWidth={1.1} />
          </div>
          <h3>{t("safeDefault")}</h3>
          <p>{t("qualityHelp")}</p>
          <div className="quality-row">
            <span>{t("coverage")}</span>
            <b>{t("metricsOnly")}</b>
          </div>
          <div className="quality-row">
            <span>{t("nativeLive")}</span>
            <span>—</span>
          </div>
          <div className="quality-row">
            <span>{t("gc")}</span>
            <span>—</span>
          </div>
        </section>
      </div>
      <section className="panel">
        <div className="panel-head">
          <div>
            <h2>{t("runningProcesses")}</h2>
            <p>{t("processSub")}</p>
          </div>
          <a className="text-button" href="#/processes">
            {t("allProcesses")}
            <ArrowRight size={15} />
          </a>
        </div>
        <ProcessTable
          items={(python.length ? python : processes).slice(0, 8)}
          diagnose={diagnose}
          canOperate={canOperate}
          compact
        />
      </section>
    </>
  );
}

function Processes({
  items,
  loading,
  error,
  refresh,
  diagnose,
  canOperate,
}: {
  items: Process[];
  loading: boolean;
  error: unknown;
  refresh: () => void;
  diagnose: (p: Process) => void;
  canOperate: boolean;
}) {
  const t = useT();
  const initial = new URLSearchParams(location.hash.split("?")[1] || "");
  const [filter, setFilter] = useState(initial.get("q") || "");
  const [python, setPython] = useState(initial.get("python") === "1");
  const filtered = useMemo(
    () =>
      items.filter(
        (p) =>
          (!python || p.python_version || p.worker_type !== "native") &&
          (p.name + " " + p.executable + " " + p.pid)
            .toLowerCase()
            .includes(filter.toLowerCase()),
      ),
    [items, filter, python],
  );
  useEffect(() => {
    const params = new URLSearchParams();
    if (filter) params.set("q", filter);
    if (python) params.set("python", "1");
    history.replaceState(
      null,
      "",
      "#/processes" + (params.size ? "?" + params : ""),
    );
  }, [filter, python]);
  return (
    <>
      <PageHead title={t("processes")} description={t("processSub")}>
        <button onClick={refresh}>
          <Activity size={16} />
          {t("refresh")}
        </button>
      </PageHead>
      <Capability />
      <section className="panel">
        <div className="table-toolbar">
          <label className="filter-input">
            <Search size={16} />
            <input
              aria-label={t("filter")}
              placeholder={t("filter")}
              value={filter}
              onChange={(e) => setFilter(e.target.value)}
            />
          </label>
          <label className="checkbox">
            <input
              type="checkbox"
              checked={python}
              onChange={(e) => setPython(e.target.checked)}
            />
            {t("pythonOnly")}
          </label>
          <span className="muted mono">{filtered.length}</span>
        </div>
        {loading ? (
          <Loading />
        ) : error ? (
          <Failure error={error} retry={refresh} />
        ) : (
          <ProcessTable
            items={filtered}
            diagnose={diagnose}
            canOperate={canOperate}
          />
        )}
      </section>
    </>
  );
}
function ProcessTable({
  items,
  diagnose,
  canOperate,
  compact = false,
}: {
  items: Process[];
  diagnose: (p: Process) => void;
  canOperate: boolean;
  compact?: boolean;
}) {
  const t = useT();
  const [sorting, setSorting] = useState<SortingState>([
    { id: "rss", desc: true },
  ]);
  const [selected, setSelected] = useState<Process | null>(null);
  const parent = useRef<HTMLDivElement>(null);
  const columns = useMemo<ColumnDef<Process>[]>(
    () => [
      {
        accessorKey: "name",
        header: t("process"),
        cell: ({ row }) => (
          <button
            className="process-name"
            onClick={() => setSelected(row.original)}
          >
            <span
              className={
                "process-icon " + (row.original.python_version ? "python" : "")
              }
            >
              <Terminal size={15} />
            </span>
            <span>
              <strong>{row.original.name}</strong>
              <small>
                {row.original.python_version || row.original.worker_type}
              </small>
            </span>
          </button>
        ),
      },
      {
        accessorKey: "pid",
        header: t("pid"),
        cell: ({ getValue }) => (
          <span className="mono muted">{getValue<number>()}</span>
        ),
      },
      {
        accessorKey: "ppid",
        header: t("parent"),
        cell: ({ getValue }) => (
          <span className="mono muted">↳ {getValue<number>()}</span>
        ),
      },
      {
        id: "rss",
        accessorFn: (p) => p.sample.rss,
        header: "RSS",
        cell: ({ getValue }) => (
          <strong className="mono">{bytes(getValue<number>())}</strong>
        ),
      },
      {
        id: "pss",
        accessorFn: (p) => p.sample.pss,
        header: "PSS",
        cell: ({ getValue }) => (
          <span className="mono muted">{bytes(getValue<number | null>())}</span>
        ),
      },
      {
        id: "threads",
        accessorFn: (p) => p.sample.threads,
        header: t("threads"),
      },
      {
        id: "modes",
        header: t("modes"),
        cell: () => <span className="mode-badge">Observe</span>,
      },
      {
        id: "action",
        header: t("action"),
        cell: ({ row }) =>
          canOperate ? (
            <button
              className="diagnose-button"
              onClick={() => diagnose(row.original)}
            >
              {t("diagnose")}
              <ArrowUpRight size={14} />
            </button>
          ) : (
            <button onClick={() => setSelected(row.original)}>
              {t("inspect")}
            </button>
          ),
      },
    ],
    [t, diagnose, canOperate],
  );
  const table = useReactTable({
    data: items,
    columns,
    state: { sorting },
    onSortingChange: setSorting,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
  });
  const rows = table.getRowModel().rows;
  const virtual = useVirtualizer({
    count: rows.length,
    getScrollElement: () => parent.current,
    estimateSize: () => 65,
    overscan: 6,
  });
  const visible = compact
    ? rows.map((_, index) => ({ index, start: index * 65, size: 65 }))
    : virtual.getVirtualItems();
  if (!items.length) return <Empty title={t("noProcesses")} />;
  return (
    <>
      <div
        className="table-scroll"
        ref={parent}
        style={{ maxHeight: compact ? "none" : 520 }}
        role="table"
        aria-label={t("processes")}
        aria-rowcount={rows.length + 1}
      >
        <div className="table-header process-row" role="row">
          {table.getHeaderGroups()[0].headers.map((h) => (
            <div
              role="columnheader"
              key={h.id}
              aria-sort={
                h.column.getIsSorted() === "asc"
                  ? "ascending"
                  : h.column.getIsSorted() === "desc"
                    ? "descending"
                    : "none"
              }
            >
              <button onClick={h.column.getToggleSortingHandler()}>
                {flexRender(h.column.columnDef.header, h.getContext())}
                {h.column.getCanSort() && <ChevronDown size={12} />}
              </button>
            </div>
          ))}
        </div>
        <div
          className="table-body"
          style={{
            height: compact ? rows.length * 65 : virtual.getTotalSize(),
            position: "relative",
          }}
        >
          {visible.map((v) => {
            const row = rows[v.index];
            return (
              <div
                key={row.original.key}
                role="row"
                aria-rowindex={v.index + 2}
                className="process-row"
                style={{
                  position: "absolute",
                  top: 0,
                  left: 0,
                  width: "100%",
                  height: v.size,
                  transform: `translateY(${v.start}px)`,
                }}
                data-pid={row.original.pid}
              >
                {row.getVisibleCells().map((cell) => (
                  <div role="cell" key={cell.id}>
                    {flexRender(cell.column.columnDef.cell, cell.getContext())}
                  </div>
                ))}
              </div>
            );
          })}
        </div>
      </div>
      {selected && (
        <Modal
          title={`${selected.name} · ${selected.pid}`}
          close={() => setSelected(null)}
        >
          <dl className="details">
            <dt>{t("process")}</dt>
            <dd className="mono">{selected.executable}</dd>
            <dt>{t("rss")}</dt>
            <dd>{bytes(selected.sample.rss)}</dd>
            <dt>{t("pss")}</dt>
            <dd>{bytes(selected.sample.pss)}</dd>
            <dt>{t("parent")}</dt>
            <dd>{selected.ppid}</dd>
            <dt>{t("worker")}</dt>
            <dd>{selected.worker_type}</dd>
          </dl>
          <Capability />
          {canOperate && (
            <button
              className="primary"
              onClick={() => {
                diagnose(selected);
                setSelected(null);
              }}
            >
              {t("diagnose")}
              <ArrowRight size={16} />
            </button>
          )}
        </Modal>
      )}
    </>
  );
}

const wizardSchema = z.object({
  duration_seconds: z.coerce.number().int().min(1).max(600),
  sample_interval_ms: z.coerce.number().int().min(100).max(60000),
  max_capture_mb: z.coerce.number().int().min(1).max(50),
});
function Wizard({ process, close }: { process: Process; close: () => void }) {
  const t = useT();
  const [step, setStep] = useState(1);
  const [purpose, setPurpose] = useState("growth");
  const [mode, setMode] = useState("observe");
  const capabilities = useQuery({
    queryKey: ["process-capabilities", process.key],
    queryFn: () =>
      api<{
        capabilities: {
          deep: boolean;
          external_allocations: boolean;
          reason: string;
        };
      }>(`/processes/${process.key}/capabilities`),
    enabled: step >= 2,
  });
  const deepAvailable = capabilities.data?.capabilities.deep === true;
  const nativeAvailable =
    capabilities.data?.capabilities.external_allocations === true;
  const [nativeRequested, setNativeRequested] = useState(false);
  const requestKey = useRef(crypto.randomUUID());
  const client = useQueryClient();
  const notify = useUI((s) => s.notify);
  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<z.infer<typeof wizardSchema>>({
    resolver: zodResolver(wizardSchema),
    defaultValues: {
      duration_seconds: 60,
      sample_interval_ms: 1000,
      max_capture_mb: 50,
    },
  });
  const mutation = useMutation({
    mutationFn: (values: z.infer<typeof wizardSchema>) =>
      api<Session>("/sessions", {
        method: "POST",
        headers: { "Idempotency-Key": requestKey.current },
        body: JSON.stringify({
          ...values,
          process_key: process.key,
          mode,
          allocation_domains: [
            "os_process",
            ...(mode === "deep" ? ["gc_objects"] : []),
            ...(nativeRequested ? ["native"] : []),
          ],
          purpose,
        }),
      }),
    onSuccess: (s) => {
      void client.invalidateQueries();
      notify(t("saved"));
      close();
      navigate("session/" + s.id);
    },
  });
  const purposes = [
    ["growth", "growthPurpose"],
    ["operation", "operationPurpose"],
    ["worker", "workerPurpose"],
    ["large", "largePurpose"],
    ["comparison", "comparePurpose"],
  ] as const;
  return (
    <Modal title={t("wizard")} close={close}>
      <div className="wizard-progress">
        {[1, 2, 3].map((n) => (
          <div key={n} className={n <= step ? "complete" : ""}>
            <span>{n < step ? <Check size={12} /> : n}</span>
          </div>
        ))}
      </div>
      <p className="eyebrow">
        {t("step")} {step} {t("of")} 3
      </p>
      <h2>{t(step === 1 ? "what" : step === 2 ? "depth" : "configure")}</h2>
      <div className="target">
        <Terminal size={18} />
        <strong>{process.name}</strong>
        <span className="mono">PID {process.pid}</span>
        <b>{bytes(process.sample.rss)}</b>
      </div>
      <form onSubmit={handleSubmit((values) => mutation.mutate(values))}>
        {step === 1 && (
          <fieldset className="choice-list">
            <legend className="sr-only">{t("what")}</legend>
            {purposes.map(([v, label]) => (
              <label key={v} className={purpose === v ? "chosen" : ""}>
                <input
                  type="radio"
                  name="purpose"
                  checked={purpose === v}
                  onChange={() => setPurpose(v)}
                />
                {t(label)}
              </label>
            ))}
          </fieldset>
        )}
        {step === 2 && (
          <div className="depth-list">
            <button
              type="button"
              className={"depth " + (mode === "observe" ? "chosen" : "")}
              onClick={() => setMode("observe")}
            >
              <ShieldCheck size={23} />
              <div>
                <strong>Observe</strong>
                <p>{t("observeDesc")}</p>
              </div>
              <span className="badge ready">{t("safeDefault")}</span>
            </button>
            <button
              type="button"
              disabled={!deepAvailable}
              className={"depth " + (mode === "deep" ? "chosen" : "")}
              onClick={() => setMode("deep")}
            >
              <Waypoints size={23} />
              <div>
                <strong>Deep</strong>
                <p>{t("deepDesc")}</p>
              </div>
              <span>{t(deepAvailable ? "ready" : "unavailable")}</span>
            </button>
            <div className="depth disabled">
              <FlaskConical size={23} />
              <div>
                <strong>Lab</strong>
                <p>{t("labDesc")}</p>
              </div>
              <span>{t("unavailable")}</span>
            </div>
          </div>
        )}
        {step === 3 && (
          <>
            <div className="form-grid">
              <label>
                {t("duration")}
                <input type="number" {...register("duration_seconds")} />
                {errors.duration_seconds && <span role="alert">1–600</span>}
              </label>
              <label>
                {t("interval")}
                <input type="number" {...register("sample_interval_ms")} />
                {errors.sample_interval_ms && (
                  <span role="alert">100–60000</span>
                )}
              </label>
              <label>
                {t("captureLimit")}
                <input type="number" {...register("max_capture_mb")} />
                {errors.max_capture_mb && <span role="alert">1–50</span>}
              </label>
            </div>
            <label className="native-optin">
              <input
                type="checkbox"
                checked={nativeRequested}
                disabled={!nativeAvailable}
                onChange={(e) => setNativeRequested(e.target.checked)}
              />
              {t("enableNative")}
            </label>
            <p className="small muted">{t("nativeRisk")}</p>
            {!nativeAvailable && (
              <p className="small muted">
                {capabilities.data?.capabilities.reason}
              </p>
            )}
            <p className="small muted">{t("budgets")}</p>
            <div className="privacy-block">
              <ShieldCheck size={19} />
              <div>
                <strong>{t("privacy")}</strong>
                <p>{t("privacyBody")}</p>
              </div>
            </div>
          </>
        )}
        {mutation.error && <Failure error={mutation.error} />}
        <div className="modal-footer">
          <button
            type="button"
            onClick={step === 1 ? close : () => setStep(step - 1)}
          >
            {t(step === 1 ? "cancel" : "back")}
          </button>
          {step < 3 ? (
            <button
              className="primary"
              type="button"
              key="wizard-next"
              onClick={(e) => {
                e.preventDefault();
                setStep(step + 1);
              }}
            >
              {t("next")}
              <ArrowRight size={16} />
            </button>
          ) : (
            <button
              className="primary"
              key="wizard-submit"
              disabled={mutation.isPending}
              type="submit"
            >
              <Radio size={16} />
              {mutation.isPending ? t("starting") : t("start")}
            </button>
          )}
        </div>
      </form>
    </Modal>
  );
}

function SessionList({
  sessions,
  loading,
  error,
  canOperate,
}: {
  sessions: Session[];
  loading: boolean;
  error: unknown;
  canOperate: boolean;
}) {
  const t = useT();
  const action = useAction();
  const upload = useRef<HTMLInputElement>(null);
  const notify = useUI((s) => s.notify);
  const client = useQueryClient();
  async function importFile(file?: File) {
    if (!file) return;
    try {
      const s = await api<Session>("/captures/import", {
        method: "POST",
        body: file,
      });
      notify(t("uploaded"));
      void client.invalidateQueries();
      navigate("session/" + s.id);
    } catch (e) {
      notify((e as Error).message);
    }
  }
  return (
    <>
      <PageHead title={t("sessions")} description={t("noSessionsSub")}>
        {canOperate && (
          <>
            <input
              ref={upload}
              type="file"
              accept=".lscap"
              className="sr-only"
              onChange={(e) => void importFile(e.target.files?.[0])}
            />
            <button onClick={() => upload.current?.click()}>
              <ArrowDownToLine size={16} />
              {t("import")}
            </button>
            <button className="primary" onClick={() => navigate("processes")}>
              <Plus size={16} />
              {t("diagnose")}
            </button>
          </>
        )}
      </PageHead>
      {loading ? (
        <Loading />
      ) : error ? (
        <Failure error={error} />
      ) : !sessions.length ? (
        <Empty title={t("noSessions")} description={t("noSessionsSub")} />
      ) : (
        <section className="panel">
          <div className="list-table">
            {sessions
              .toSorted((a, b) => b.created_at - a.created_at)
              .map((s) => (
                <div className="list-row" key={s.id}>
                  <span className="session-icon">
                    <Radio size={18} />
                  </span>
                  <div>
                    <button
                      className="text-button mono"
                      onClick={() => navigate("session/" + s.id)}
                    >
                      {s.id.slice(0, 12)}
                      <ArrowUpRight size={14} />
                    </button>
                    <small>
                      {new Date(s.created_at * 1000).toLocaleString()}
                    </small>
                  </div>
                  <span className="mode-badge">Observe</span>
                  <Badge value={s.state} />
                  <span className="mono muted">
                    {s.last_sequence} {t("samples")}
                  </span>
                  {s.state === "recording" && canOperate ? (
                    <button
                      onClick={() =>
                        action.mutate({ path: `/sessions/${s.id}/stop` })
                      }
                    >
                      <Square size={13} />
                      {t("stop")}
                    </button>
                  ) : (
                    <button onClick={() => navigate("session/" + s.id)}>
                      {t("open")}
                      <ArrowRight size={14} />
                    </button>
                  )}
                </div>
              ))}
          </div>
        </section>
      )}
    </>
  );
}

function SessionDetail({ id, role }: { id: string; role: string }) {
  const t = useT();
  const notify = useUI((s) => s.notify);
  const [paused, setPaused] = useState(false);
  const [tab, setTab] = useState<Key>("timeline");
  const [range, setRange] = useState("all");
  const [marker, setMarker] = useState(false);
  const [name, setName] = useState("");
  const [repeat, setRepeat] = useState(false);
  const action = useAction();
  const s = useQuery({
    queryKey: ["session", id],
    queryFn: () => api<Session>("/sessions/" + id),
    refetchInterval: 2000,
  });
  const q = useQuery({
    queryKey: ["timeline", id],
    queryFn: () => api<Timeline>(`/sessions/${id}/timeline?points=600`),
    refetchInterval: 2000,
  });
  const frozen = useRef<Timeline | undefined>(undefined);
  if (!paused) frozen.current = q.data;
  const timeline = frozen.current;
  const samples = timeline?.items || [];
  const midpoint = samples.length
    ? (samples[0].timestamp + samples[samples.length - 1].timestamp) / 2
    : 0;
  const filtered = samples.filter(
    (p) =>
      range === "all" ||
      (range === "a" ? p.timestamp <= midpoint : p.timestamp >= midpoint),
  );
  const active = s.data?.state === "recording";
  const canOperate = ["operator", "admin"].includes(role);
  const canAnalyze = role !== "viewer";
  const tabs: Key[] = [
    "timeline",
    "flamegraph",
    "calltree",
    "allocations",
    "survivors",
    "gcTypes",
    "references",
  ];
  async function compareIntervals() {
    if (samples.length < 2) return;
    try {
      await api("/comparisons", {
        method: "POST",
        body: JSON.stringify({
          a: { session_id: id, start: samples[0].timestamp, end: midpoint },
          b: {
            session_id: id,
            start: midpoint,
            end: samples.at(-1)!.timestamp,
          },
        }),
      });
      navigate("comparisons");
    } catch (e) {
      notify((e as Error).message);
    }
  }
  if (s.isLoading) return <Loading />;
  if (s.error) return <Failure error={s.error} />;
  if (!s.data) return null;
  return (
    <>
      <div className="session-top">
        <a href="#/sessions">{t("sessions")}</a>
        <ChevronRight size={13} />
        <span className="mono">{id.slice(0, 12)}</span>
        <Badge value={s.data.state} />
      </div>
      <PageHead
        title={t("session") + " " + id.slice(0, 8)}
        description={
          s.data.state === "failed"
            ? t("failed")
            : active
              ? t("live")
              : t("finished")
        }
      >
        <button onClick={() => setPaused(!paused)}>
          {paused ? <Play size={14} /> : <Pause size={14} />}{" "}
          {t(paused ? "resume" : "pause")}
        </button>
        {s.data.ended_at && ["ready", "degraded"].includes(s.data.state) && (
          <button
            onClick={() =>
              void download(`/sessions/${id}/export`, id + ".lscap").catch(
                (e) => notify(e.message),
              )
            }
          >
            <ArrowDownToLine size={15} />
            {t("export")}
          </button>
        )}
        {active && canOperate && (
          <button
            className="danger"
            onClick={() => action.mutate({ path: `/sessions/${id}/stop` })}
          >
            <Square size={13} />
            {t("stop")}
          </button>
        )}
      </PageHead>
      {s.data.state === "failed" && (
        <Failure error={new Error(s.data.reason)} />
      )}
      {s.data.quality.native_failure && (
        <p role="alert" className="native-warning">
          {s.data.quality.native_failure}
        </p>
      )}
      <div className="session-metrics">
        <Metric
          label={t("rss")}
          value={bytes(filtered.at(-1)?.rss)}
          hint={t("rssHelp")}
        />
        <Metric
          label={t("pss")}
          value={bytes(
            [...filtered].reverse().find((p) => p.pss !== null)?.pss,
          )}
          hint={t("pssHelp")}
        />
        <Metric
          label={t("growth")}
          value={bytes(timeline?.summary.rss_delta_bytes)}
        />
        <Metric
          label={t("lost")}
          value={
            (s.data.quality.lost_samples || 0) +
            (s.data.quality.lost_events || 0) +
            (s.data.quality.lost_native || 0)
          }
          hint={t("metricsOnly")}
        />
      </div>
      {s.data.quality.coverage === "native_observed" && (
        <NativeStats id={id} active={active && !paused} state={s.data.state} />
      )}
      <div className="investigation-layout">
        <aside className="panel investigation-left">
          <div className="panel-head">
            <h2>{t("coverage")}</h2>
          </div>
          <div className="domain-selected">
            <Activity size={16} />
            {t("rss")}
            <Check size={14} />
          </div>
          <div
            className={
              "domain " +
              (s.data.quality.coverage === "native_observed"
                ? "domain-selected"
                : "disabled")
            }
          >
            <MemoryStick size={16} />
            {t("nativeLive")}
            <span>—</span>
          </div>
          <div className="domain disabled">
            <Box size={16} />
            {t("gc")}
            <span>—</span>
          </div>
          <hr />
          <label className="range-label">
            {t("range")}
            <select value={range} onChange={(e) => setRange(e.target.value)}>
              <option value="all">{t("allTime")}</option>
              <option value="a">{t("firstHalf")}</option>
              <option value="b">{t("secondHalf")}</option>
            </select>
          </label>
          <p className="small muted">
            {t(
              s.data.quality.coverage === "native_observed"
                ? "nativeOnly"
                : "qualityHelp",
            )}
          </p>
          <hr />
          <button className="wide" onClick={() => setRepeat(!repeat)}>
            <FlaskConical size={16} />
            {t("repeated")}
          </button>
          {repeat && (
            <div className="repeated">
              <p>{t("repeatedSub")}</p>
              {(
                [
                  "warmup",
                  "baseline",
                  "repetition",
                  "cooldown",
                  "final",
                ] as const
              ).map((k) => (
                <button
                  disabled={!active || !canAnalyze || action.isPending}
                  key={k}
                  onClick={() =>
                    action.mutate({
                      path: `/sessions/${id}/markers`,
                      body: { name: k },
                    })
                  }
                >
                  <Plus size={13} />
                  {t(k)}
                </button>
              ))}
            </div>
          )}
        </aside>
        <section className="panel investigation-center">
          <div className="tabbar" role="tablist" aria-label={t("session")}>
            {tabs.map((k) => (
              <button
                role="tab"
                aria-selected={tab === k}
                aria-controls="session-tab"
                key={k}
                onClick={() => setTab(k)}
              >
                {t(k)}
                {k !== "timeline" && <span className="tab-dot" />}
              </button>
            ))}
          </div>
          <div id="session-tab" role="tabpanel">
            {tab === "timeline" ? (
              <>
                {q.error && <Failure error={q.error} />}
                <div className="panel-head">
                  <div>
                    <h2>{t("memoryTrend")}</h2>
                    <p>{t("memorySub")}</p>
                  </div>
                  <span className="mode-badge">RSS</span>
                </div>
                <Chart samples={filtered} />
                <div className="timeline-actions">
                  {active && canAnalyze && (
                    <button onClick={() => setMarker(true)}>
                      <Plus size={14} />
                      {t("mark")}
                    </button>
                  )}
                  <button disabled title={t("deepDesc")}>
                    <Box size={14} />
                    {t("snapshot")}
                  </button>
                  {canAnalyze && (
                    <button
                      disabled={samples.length < 2}
                      onClick={() => void compareIntervals()}
                    >
                      <GitCompareArrows size={14} />
                      {t("compareIntervals")}
                    </button>
                  )}
                </div>
                <div className="marker-list">
                  {timeline?.markers.map((m) => (
                    <div key={m.id}>
                      <span className="marker-diamond" />
                      <strong>{m.name}</strong>
                      <span className="mono muted">
                        {new Date(m.timestamp * 1000).toLocaleTimeString()}
                      </span>
                    </div>
                  ))}
                </div>
              </>
            ) : ["flamegraph", "calltree", "allocations", "survivors"].includes(
                tab,
              ) ? (
              <NativeViews
                id={id}
                tab={tab}
                start={range === "b" ? midpoint : undefined}
                end={range === "a" ? midpoint : undefined}
                active={active && !paused}
                state={s.data.state}
              />
            ) : tab === "gcTypes" ? (
              <GCTypes
                id={id}
                start={range === "b" ? midpoint : undefined}
                end={range === "a" ? midpoint : undefined}
              />
            ) : (
              <Empty
                title={t("unavailable")}
                description={t("allocationUnavailable")}
              />
            )}
          </div>
        </section>
        <aside className="panel investigation-right">
          <div className="panel-head">
            <h2>{t("evidence")}</h2>
            <BookOpen size={16} />
          </div>
          {timeline && (
            <Evidence
              summary={timeline.summary}
              native={s.data.quality.coverage === "native_observed"}
            />
          )}
          <div className="right-actions">
            {canAnalyze && (
              <button onClick={() => navigate("reports")}>
                <FileText size={15} />
                {t("createReport")}
              </button>
            )}
          </div>
        </aside>
      </div>
      <Capability native={s.data.quality.coverage === "native_observed"} />
      {marker && (
        <Modal title={t("mark")} close={() => setMarker(false)}>
          <form
            onSubmit={(e) => {
              e.preventDefault();
              action.mutate(
                { path: `/sessions/${id}/markers`, body: { name } },
                {
                  onSuccess: () => {
                    setMarker(false);
                    setName("");
                  },
                },
              );
            }}
          >
            <label>
              {t("markerName")}
              <input
                autoFocus
                required
                maxLength={80}
                pattern="[\w .:\-]+"
                placeholder={t("markerPlaceholder")}
                value={name}
                onChange={(e) => setName(e.target.value)}
              />
            </label>
            <div className="modal-footer">
              <button type="button" onClick={() => setMarker(false)}>
                {t("cancel")}
              </button>
              <button className="primary" disabled={action.isPending}>
                {t("save")}
              </button>
            </div>
          </form>
        </Modal>
      )}
    </>
  );
}
function GCTypes({
  id,
  start,
  end,
}: {
  id: string;
  start?: number;
  end?: number;
}) {
  const t = useT();
  const q = useQuery({
    queryKey: ["gc-types", id],
    queryFn: () =>
      api<{
        items: {
          timestamp: number;
          snapshot: {
            name: string;
            visibility: string;
            partial: boolean;
            types: Record<
              string,
              { count: number; shallow_bytes_estimate: number }
            >;
          };
        }[];
      }>(`/sessions/${id}/gc/types`),
    refetchInterval: 3000,
  });
  if (q.isLoading) return <Loading />;
  if (q.error)
    return <Empty title={t("unavailable")} description={t("deepDesc")} />;
  const rows =
    q.data?.items.filter(
      (r) =>
        (start === undefined || r.timestamp >= start) &&
        (end === undefined || r.timestamp <= end),
    ) || [];
  return (
    <div className="form-panel">
      <h2>{t("gcGenerationZero")}</h2>
      <p className="small muted">{t("gcScope")}</p>
      {rows.map((r, i) => (
        <div key={i}>
          <h3>
            {r.snapshot.name} ·{" "}
            {new Date(r.timestamp * 1000).toLocaleTimeString()}
            {r.snapshot.partial ? " · " + t("degraded") : ""}
          </h3>
          <table className="gc-table">
            <thead>
              <tr>
                <th>{t("objectType")}</th>
                <th>{t("gc")}</th>
                <th>{t("shallowEstimate")}</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(r.snapshot.types)
                .sort((a, b) => b[1].count - a[1].count)
                .map(([type, value]) => (
                  <tr key={type}>
                    <td className="mono">{type}</td>
                    <td>{value.count}</td>
                    <td>{bytes(value.shallow_bytes_estimate)} ≈</td>
                  </tr>
                ))}
            </tbody>
          </table>
        </div>
      ))}
    </div>
  );
}
function Evidence({
  summary,
  native = false,
}: {
  summary: Summary;
  native?: boolean;
}) {
  const t = useT();
  return (
    <div className="evidence-body">
      <span className="eyebrow">{t("hypothesis")}</span>
      <h3>{t(summary.classification as Key)}</h3>
      <div className="score">
        <span>{summary.suspicion_score}</span>
        <small>/ 100</small>
        <b>{t("score")}</b>
      </div>
      <div className="score-bar">
        <span style={{ width: summary.suspicion_score + "%" }} />
      </div>
      <p>{t("noProof")}</p>
      <dl className="evidence-numbers">
        <div>
          <dt>{t("samples")}</dt>
          <dd>{summary.sample_count}</dd>
        </div>
        <div>
          <dt>{t("slope")}</dt>
          <dd>
            {bytes(summary.rss_slope_bytes_per_second)}
            {t("perSecond")}
          </dd>
        </div>
      </dl>
      <h4>{t("limitations")}</h4>
      <p>{t(native ? "nativeOnly" : "capabilityBody")}</p>
      <h4>{t("followup")}</h4>
      <p>{t("repeatedSub")}</p>
    </div>
  );
}

type Comparison = {
  id: string;
  created_at: number;
  result: {
    a: Summary;
    b: Summary;
    rss_slope_change: number | null;
    warnings: string[];
    native?: {
      a: import("./NativeViews").NativeAnalysis;
      b: import("./NativeViews").NativeAnalysis;
      allocated_delta_bytes: number;
      survivor_delta_bytes: number | null;
    };
  };
};
function Comparisons({
  sessions,
  role,
}: {
  sessions: Session[];
  role: string;
}) {
  const t = useT();
  const action = useAction();
  const [a, setA] = useState("");
  const [b, setB] = useState("");
  const list = useQuery({
    queryKey: ["comparisons"],
    queryFn: () => api<Page<Comparison>>("/comparisons"),
  });
  return (
    <>
      <PageHead title={t("comparisons")} description={t("compareSub")} />
      <section className="panel form-panel">
        <div className="compare-selectors">
          <label>
            {t("sessionA")}
            <SessionSelect sessions={sessions} value={a} set={setA} />
          </label>
          <GitCompareArrows size={23} />
          <label>
            {t("sessionB")}
            <SessionSelect sessions={sessions} value={b} set={setB} />
          </label>
          <button
            className="primary"
            disabled={!a || !b || role === "viewer" || action.isPending}
            onClick={() =>
              action.mutate({
                path: "/comparisons",
                body: { a: { session_id: a }, b: { session_id: b } },
              })
            }
          >
            {t("compare")}
            <ArrowRight size={15} />
          </button>
        </div>
      </section>
      {list.isLoading ? (
        <Loading />
      ) : list.error ? (
        <Failure error={list.error} />
      ) : !list.data?.items.length ? (
        <Empty title={t("noComparison")} />
      ) : (
        list.data.items
          .toSorted((a, b) => b.created_at - a.created_at)
          .map((c) => (
            <section className="panel comparison" key={c.id}>
              <div className="panel-head">
                <h2>
                  {t("compare")} · {c.id.slice(0, 8)}
                </h2>
                <span className="mono muted">
                  Δ {bytes(c.result.rss_slope_change)}
                  {t("perSecond")}
                </span>
              </div>
              <div className="comparison-grid">
                <div>
                  <h3>{t("sessionA")}</h3>
                  <Evidence summary={c.result.a} />
                </div>
                <div>
                  <h3>{t("sessionB")}</h3>
                  <Evidence summary={c.result.b} />
                </div>
              </div>
              {c.result.native && (
                <div className="native-view">
                  <p>{t("nativeOnly")}</p>
                  <div className="comparison-grid">
                    <p>
                      A · {t("observedAllocated")}:{" "}
                      {bytes(c.result.native.a.selected_allocated_bytes)} ·{" "}
                      {t("nativeLive")}:{" "}
                      {c.result.native.a.exact_survivors
                        ? bytes(c.result.native.a.retained_tree.value)
                        : "—"}
                    </p>
                    <p>
                      B · {t("observedAllocated")}:{" "}
                      {bytes(c.result.native.b.selected_allocated_bytes)} ·{" "}
                      {t("nativeLive")}:{" "}
                      {c.result.native.b.exact_survivors
                        ? bytes(c.result.native.b.retained_tree.value)
                        : "—"}
                    </p>
                  </div>
                  <p>Δ {bytes(c.result.native.survivor_delta_bytes)}</p>
                </div>
              )}
              {c.result.warnings.length > 0 && <Capability />}
            </section>
          ))
      )}
    </>
  );
}
function SessionSelect({
  sessions,
  value,
  set,
}: {
  sessions: Session[];
  value: string;
  set: (s: string) => void;
}) {
  const t = useT();
  return (
    <select
      required
      aria-label={t("session")}
      value={value}
      onChange={(e) => set(e.target.value)}
    >
      <option value="">—</option>
      {sessions
        .toSorted((a, b) => b.created_at - a.created_at)
        .map((s) => (
          <option key={s.id} value={s.id}>
            {s.id.slice(0, 10)} ·{" "}
            {new Date(s.created_at * 1000).toLocaleTimeString()} ·{" "}
            {t(s.state as Key)}
          </option>
        ))}
    </select>
  );
}
function Reports({ sessions, role }: { sessions: Session[]; role: string }) {
  const t = useT();
  const notify = useUI((s) => s.notify);
  const action = useAction();
  const [session, setSession] = useState("");
  const [title, setTitle] = useState("");
  const [steps, setSteps] = useState("");
  const list = useQuery({
    queryKey: ["reports"],
    queryFn: () =>
      api<Page<{ id: string; title: string; created_at: number }>>("/reports"),
  });
  return (
    <>
      <PageHead title={t("reports")} description={t("reportSub")} />
      {role !== "viewer" && (
        <section className="panel form-panel">
          <form
            onSubmit={(e) => {
              e.preventDefault();
              action.mutate({
                path: "/reports",
                body: { session_id: session, title, reproduction_steps: steps },
              });
            }}
          >
            <div className="form-grid">
              <label>
                {t("session")}
                <SessionSelect
                  sessions={sessions}
                  value={session}
                  set={setSession}
                />
              </label>
              <label>
                {t("reportTitle")}
                <input
                  required
                  maxLength={160}
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                />
              </label>
            </div>
            <label>
              {t("reproduction")}
              <textarea
                value={steps}
                onChange={(e) => setSteps(e.target.value)}
                maxLength={10000}
              />
            </label>
            <button className="primary" disabled={!session || action.isPending}>
              <FileText size={15} />
              {t("createReport")}
            </button>
          </form>
        </section>
      )}
      {list.isLoading ? (
        <Loading />
      ) : list.error ? (
        <Failure error={list.error} />
      ) : !list.data?.items.length ? (
        <Empty title={t("noReports")} description={t("offline")} />
      ) : (
        <div className="reports-grid">
          {list.data.items.map((r) => (
            <section className="panel report-card" key={r.id}>
              <span className="report-icon">
                <FileText size={25} />
              </span>
              <h3>{r.title}</h3>
              <p>{new Date(r.created_at * 1000).toLocaleString()}</p>
              <small>
                <ShieldCheck size={13} />
                {t("offline")}
              </small>
              <div className="report-downloads">
                <button
                  onClick={() =>
                    void download(
                      `/reports/${r.id}/download`,
                      r.id + ".html",
                    ).catch((e) => notify(e.message))
                  }
                >
                  <ArrowDownToLine size={14} />
                  {t("download")}
                </button>
                <button
                  onClick={() =>
                    void download(
                      `/reports/${r.id}/download?format=json`,
                      r.id + ".json",
                    ).catch((e) => notify(e.message))
                  }
                >
                  {t("downloadJson")}
                </button>
              </div>
            </section>
          ))}
        </div>
      )}
    </>
  );
}
function Investigations({
  sessions,
  role,
}: {
  sessions: Session[];
  role: string;
}) {
  const t = useT();
  const action = useAction();
  const [session, setSession] = useState("");
  const [title, setTitle] = useState("");
  const [notes, setNotes] = useState("");
  const list = useQuery({
    queryKey: ["investigations"],
    queryFn: () =>
      api<
        Page<{ id: string; title: string; session_id: string; notes: string }>
      >("/investigations"),
  });
  return (
    <>
      <PageHead title={t("investigations")} description={t("repeatedSub")} />
      {role !== "viewer" && (
        <section className="panel form-panel">
          <form
            onSubmit={(e) => {
              e.preventDefault();
              action.mutate({
                path: "/investigations",
                body: { session_id: session, title, notes },
              });
            }}
          >
            <div className="form-grid">
              <label>
                {t("session")}
                <SessionSelect
                  sessions={sessions}
                  value={session}
                  set={setSession}
                />
              </label>
              <label>
                {t("investigationTitle")}
                <input
                  required
                  maxLength={160}
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                />
              </label>
            </div>
            <label>
              {t("notes")}
              <textarea
                value={notes}
                maxLength={10000}
                onChange={(e) => setNotes(e.target.value)}
              />
            </label>
            <button className="primary" disabled={!session || action.isPending}>
              <Plus size={16} />
              {t("createInvestigation")}
            </button>
          </form>
        </section>
      )}
      {list.error ? (
        <Failure error={list.error} />
      ) : !list.data?.items.length ? (
        <Empty title={t("noInvestigations")} />
      ) : (
        list.data.items.map((v) => (
          <section className="panel investigation-card" key={v.id}>
            <Waypoints size={22} />
            <div>
              <h3>{v.title}</h3>
              <p>{v.notes}</p>
              <button
                className="text-button"
                onClick={() => navigate("session/" + v.session_id)}
              >
                {t("open")}
                <ArrowRight size={15} />
              </button>
            </div>
          </section>
        ))
      )}
    </>
  );
}

type SettingsData = {
  config: {
    listen: string;
    max_storage_mb: number;
    allow_remote_access: boolean;
    profiling: Record<string, number>;
    retention: {
      process_metrics_days: number;
      raw_captures_hours: number;
      summaries_days: number;
    };
  };
  storage_bytes: number;
  role: string;
};
function Settings({ role }: { role: string }) {
  const t = useT();
  const ui = useUI();
  const q = useQuery({
    queryKey: ["settings"],
    queryFn: () => api<SettingsData>("/settings"),
  });
  const diagnostics = useQuery({
    queryKey: ["capabilities"],
    queryFn: () => api<Record<string, unknown>>("/capabilities"),
  });
  const audit = useQuery({
    queryKey: ["audit"],
    queryFn: () =>
      api<
        Page<{ id: number; timestamp: number; action: string; role: string }>
      >("/audit"),
    enabled: role === "admin",
  });
  const mutation = useMutation({
    mutationFn: (body: unknown) =>
      api("/settings", { method: "PATCH", body: JSON.stringify(body) }),
    onSuccess: () => ui.notify(t("saved")),
    onError: (e) => ui.notify(e.message),
  });
  function save(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = new FormData(e.currentTarget);
    const config = q.data!.config;
    mutation.mutate({
      ...config,
      data_path: ".data",
      max_storage_mb: Number(form.get("quota")),
      retention: {
        process_metrics_days: Number(form.get("metrics")),
        raw_captures_hours: Number(form.get("captures")),
        summaries_days: Number(form.get("summaries")),
      },
    });
  }
  return (
    <>
      <PageHead title={t("settings")} description={t("uidPolicy")} />
      <div className="settings-grid">
        <section className="panel form-panel">
          <h2>{t("theme")}</h2>
          <select
            aria-label={t("theme")}
            value={ui.theme}
            onChange={(e) =>
              ui.setTheme(e.target.value as "dark" | "light" | "system")
            }
          >
            <option value="dark">{t("dark")}</option>
            <option value="light">{t("light")}</option>
            <option value="system">{t("system")}</option>
          </select>
          <hr />
          <h2>{t("storage")}</h2>
          {q.isLoading ? (
            <Loading />
          ) : q.error ? (
            <Failure error={q.error} />
          ) : (
            q.data && (
              <form onSubmit={save}>
                <p className="mono muted">
                  {bytes(q.data.storage_bytes)} /{" "}
                  {bytes(q.data.config.max_storage_mb * 1024 * 1024)}
                </p>
                <label>
                  {t("quota")}
                  <input
                    name="quota"
                    type="number"
                    min={10}
                    max={1048576}
                    defaultValue={q.data.config.max_storage_mb}
                    disabled={role !== "admin"}
                  />
                </label>
                <h3>{t("retention")}</h3>
                <div className="form-grid">
                  <label>
                    {t("metricDays")}
                    <input
                      name="metrics"
                      type="number"
                      min={1}
                      max={365}
                      defaultValue={
                        q.data.config.retention.process_metrics_days
                      }
                      disabled={role !== "admin"}
                    />
                  </label>
                  <label>
                    {t("captureHours")}
                    <input
                      name="captures"
                      type="number"
                      min={1}
                      max={8760}
                      defaultValue={q.data.config.retention.raw_captures_hours}
                      disabled={role !== "admin"}
                    />
                  </label>
                  <label>
                    {t("summaryDays")}
                    <input
                      name="summaries"
                      type="number"
                      min={1}
                      max={3650}
                      defaultValue={q.data.config.retention.summaries_days}
                      disabled={role !== "admin"}
                    />
                  </label>
                </div>
                {role === "admin" && (
                  <button className="primary" disabled={mutation.isPending}>
                    {t("save")}
                  </button>
                )}
              </form>
            )
          )}
        </section>
        <section className="panel form-panel">
          <h2>{t("diagnostics")}</h2>
          {diagnostics.isLoading ? (
            <Loading />
          ) : diagnostics.error ? (
            <Failure error={diagnostics.error} />
          ) : (
            <pre className="diagnostics">
              {JSON.stringify(diagnostics.data, null, 2)}
            </pre>
          )}
          <h3>{t("security")}</h3>
          <p className="muted">{t("uidPolicy")}</p>
          <span className="badge ready">
            {t("role")}: {role}
          </span>
        </section>
      </div>
      {role === "admin" && (
        <section className="panel">
          <div className="panel-head">
            <h2>{t("audit")}</h2>
          </div>
          {audit.error ? (
            <Failure error={audit.error} />
          ) : (
            <div className="audit-list">
              {audit.data?.items.map((a) => (
                <div key={a.id}>
                  <span className="mono muted">
                    {new Date(a.timestamp * 1000).toLocaleString()}
                  </span>
                  <strong className="mono">{a.action}</strong>
                  <span>{a.role}</span>
                </div>
              ))}
            </div>
          )}
        </section>
      )}
    </>
  );
}
