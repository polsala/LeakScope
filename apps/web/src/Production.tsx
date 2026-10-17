import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import type { components } from "../../../packages/api-client/schema";
import {
  api,
  bytes,
  type Page,
  type Process,
  type Session,
  type Timeline,
} from "./api";
import { Chart, Empty, Failure, Loading, Metric } from "./components";
import { useT, useUI } from "./store";
import type { Key } from "./i18n";

type Monitor = components["schemas"]["MonitorView"];
type MonitorTimeline = components["schemas"]["MonitorTimelineView"];
type Finding = components["schemas"]["FindingsView"];
const go = (route: string) => {
  location.hash = "/" + route;
};
const clock = (value: number) => new Date(value * 1000).toLocaleString();
const classifications: Record<string, Key> = {
  sustained_growth: "sustainedGrowth",
  plateau: "boundedGrowth",
  transient_spike: "temporarySpike",
  insufficient_evidence: "insufficientFinding",
  no_sustained_growth: "stableMemory",
  possible_unbounded_cache: "possibleCache",
  likely_bounded_cache_or_warmup: "boundedGrowth",
  temporary_allocation_spike: "temporarySpike",
  likely_retained_python_references: "pythonRetention",
  likely_native_memory_retention: "nativeRetention",
  possible_allocator_fragmentation: "fragmentationFinding",
};
const classification = (value: string) =>
  classifications[value] || "insufficientFinding";

export function ObservationSummary() {
  const t = useT();
  const q = useQuery({
    queryKey: ["monitors"],
    queryFn: () => api<Page<Monitor>>("/monitors"),
    refetchInterval: 5000,
  });
  const rows = q.data?.items.filter((m) => m.state === "observing") || [];
  return (
    <section className="panel observation-summary">
      <div className="panel-head">
        <h2>{t("continuousMonitoring")}</h2>
        <button onClick={() => go("monitoring")}>{t("openMonitoring")}</button>
      </div>
      <p>{t("monitoringHelp")}</p>
      <div className="monitor-cards">
        {rows.slice(0, 6).map((m) => (
          <button key={m.id} onClick={() => go("monitoring/" + m.id)}>
            <span className="mono">{m.process_key.slice(0, 10)}</span>
            <strong>
              {t(
                classification(
                  String(
                    (
                      m.analysis.trend as
                        | { classification?: string }
                        | undefined
                    )?.classification || "",
                  ),
                ),
              )}
            </strong>
            <span>
              {t("rss")}:{" "}
              {bytes((m.latest.sample as { rss?: number } | undefined)?.rss)}
            </span>
          </button>
        ))}
        {!rows.length && <p className="muted">{t("noMonitors")}</p>}
      </div>
    </section>
  );
}

export function Monitoring({
  processes,
  role,
  id,
}: {
  processes: Process[];
  role: string;
  id?: string;
}) {
  const t = useT(),
    notify = useUI((s) => s.notify),
    cache = useQueryClient();
  const [target, setTarget] = useState("");
  const [automatic, setAutomatic] = useState(false);
  const [trigger, setTrigger] = useState("growth");
  const [seconds, setSeconds] = useState(5);
  const canOperate = ["operator", "admin"].includes(role);
  const list = useQuery({
    queryKey: ["monitors"],
    queryFn: () => api<Page<Monitor>>("/monitors?limit=100"),
    refetchInterval: 2000,
  });
  const selected = id || list.data?.items.at(-1)?.id;
  const current = useQuery({
    queryKey: ["monitor", selected],
    queryFn: () => api<Monitor>("/monitors/" + selected),
    enabled: !!selected,
    refetchInterval: 2000,
  });
  const timeline = useQuery({
    queryKey: ["monitorTimeline", selected],
    queryFn: () => api<MonitorTimeline>(`/monitors/${selected}/timeline`),
    enabled: !!selected,
    refetchInterval: 2000,
  });
  const settings = useQuery({
    queryKey: ["monitoringPolicy"],
    queryFn: () =>
      api<{
        config: {
          profiling: {
            allow_automatic_native_capture: boolean;
            max_automatic_native_seconds: number;
          };
        };
      }>("/settings"),
  });
  const allowed =
    settings.data?.config.profiling.allow_automatic_native_capture;
  const create = useMutation({
    mutationFn: () =>
      api<Monitor>("/monitors", {
        method: "POST",
        body: JSON.stringify({
          process_key: target,
          automatic_policy: automatic ? "native_light" : null,
          trigger,
          capture_seconds: seconds,
        }),
      }),
    onSuccess: (m) => {
      void cache.invalidateQueries({ queryKey: ["monitors"] });
      go("monitoring/" + m.id);
    },
    onError: (e) => notify(e.message),
  });
  const action = useMutation({
    mutationFn: (kind: "stop" | "capture") =>
      api<{ session_id?: string }>(`/monitors/${selected}/${kind}`, {
        method: "POST",
      }),
    onSuccess: (v) => {
      void cache.invalidateQueries({ queryKey: ["monitor"] });
      if (v.session_id) go("session/" + v.session_id);
    },
    onError: (e) => notify(e.message),
  });
  const monitor = current.data;
  const sample = timeline.data?.items.at(-1);
  const trend = monitor?.analysis.trend as
    | {
        classification?: string;
        slope_bytes_per_second?: number;
        anomaly?: boolean;
      }
    | undefined;
  return (
    <>
      <h1>{t("continuousMonitoring")}</h1>
      <p className="muted">{t("monitoringHelp")}</p>
      {canOperate && (
        <section className="panel form-panel">
          <form
            onSubmit={(e) => {
              e.preventDefault();
              create.mutate();
            }}
          >
            <div className="form-grid">
              <label>
                {t("processes")}
                <select
                  required
                  value={target}
                  onChange={(e) => setTarget(e.target.value)}
                >
                  <option value="">—</option>
                  {processes.map((p) => (
                    <option key={p.key} value={p.key}>
                      {p.pid} · {p.name}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                {t("windowDuration")}
                <input
                  type="number"
                  min="1"
                  max={
                    settings.data?.config.profiling
                      .max_automatic_native_seconds || 15
                  }
                  value={seconds}
                  onChange={(e) => setSeconds(Number(e.target.value))}
                />
              </label>
            </div>
            <label className="check">
              <input
                type="checkbox"
                checked={automatic}
                disabled={!allowed}
                onChange={(e) => setAutomatic(e.target.checked)}
              />
              {t("authorizeAutomatic")}
            </label>
            {!allowed && (
              <p className="small muted">{t("automaticDisabled")}</p>
            )}
            {automatic && (
              <label>
                {t("captureTrigger")}
                <select
                  value={trigger}
                  onChange={(e) => setTrigger(e.target.value)}
                >
                  <option value="growth">{t("sustainedGrowth")}</option>
                  <option value="periodic">{t("periodicWindows")}</option>
                </select>
              </label>
            )}
            <button className="primary" disabled={!target || create.isPending}>
              {t("startMonitoring")}
            </button>
          </form>
        </section>
      )}
      {list.isLoading ? (
        <Loading />
      ) : list.error ? (
        <Failure error={list.error} />
      ) : !list.data?.items.length ? (
        <Empty title={t("noMonitors")} />
      ) : (
        <div className="monitor-layout">
          <aside
            className="panel monitor-list"
            aria-label={t("continuousMonitoring")}
          >
            {list.data.items.map((m) => (
              <button
                className={m.id === selected ? "selected" : ""}
                key={m.id}
                onClick={() => go("monitoring/" + m.id)}
              >
                <strong className="mono">{m.process_key.slice(0, 12)}</strong>
                <span>
                  {m.state === "observing"
                    ? t("monitoringActive")
                    : t("finished")}
                </span>
                <small>{clock(m.created_at)}</small>
              </button>
            ))}
          </aside>
          <div>
            {current.error && <Failure error={current.error} />}{" "}
            {monitor && (
              <>
                <div className="panel-head">
                  <h2>{t(classification(trend?.classification || ""))}</h2>
                  {canOperate && monitor.state === "observing" && (
                    <div className="button-row">
                      <button
                        onClick={() => action.mutate("capture")}
                        disabled={action.isPending}
                      >
                        {t("captureWindow")}
                      </button>
                      <button onClick={() => action.mutate("stop")}>
                        {t("stopMonitoring")}
                      </button>
                    </div>
                  )}
                </div>
                <div className="metrics-grid">
                  <Metric label={t("rss")} value={bytes(sample?.rss)} />
                  <Metric label={t("pss")} value={bytes(sample?.pss)} />
                  <Metric
                    label={t("growthPerHour")}
                    value={bytes(
                      trend?.slope_bytes_per_second === undefined
                        ? undefined
                        : trend.slope_bytes_per_second * 3600,
                    )}
                  />
                  <Metric
                    label={t("cpu")}
                    value={
                      sample?.target_cpu_percent == null
                        ? "—"
                        : sample.target_cpu_percent.toFixed(1) + "%"
                    }
                  />
                </div>
                {monitor.last_error && <p role="alert">{monitor.last_error}</p>}
                <p className="native-warning">{t("windowGapHelp")}</p>
                {timeline.data && (
                  <section className="panel">
                    <Chart
                      samples={timeline.data.items}
                      windows={timeline.data.windows.map((w) => ({
                        start: w.created_at,
                        end: w.ended_at ?? Date.now() / 1000,
                      }))}
                    />
                    {!!timeline.data.windows.length && (
                      <p className="muted small">{t("windowBoundsHelp")}</p>
                    )}
                  </section>
                )}
                <h3>{t("captureWindows")}</h3>
                {timeline.error && <Failure error={timeline.error} />}
                <div className="table-scroll">
                  <table>
                    <thead>
                      <tr>
                        <th>{t("session")}</th>
                        <th>{t("start")}</th>
                        <th>{t("end")}</th>
                        <th>{t("coverage")}</th>
                      </tr>
                    </thead>
                    <tbody>
                      {timeline.data?.windows.map((w) => (
                        <tr key={w.session_id}>
                          <td>
                            <button
                              onClick={() => go("findings/" + w.session_id)}
                              className="mono"
                            >
                              {w.session_id.slice(0, 10)}
                            </button>
                          </td>
                          <td>{clock(w.created_at)}</td>
                          <td>
                            {w.ended_at ? clock(w.ended_at) : t("recording")}
                          </td>
                          <td>{t("independentWindow")}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <details>
                  <summary>{t("diagnosticEvidence")}</summary>
                  <pre>{JSON.stringify(monitor.analysis, null, 2)}</pre>
                </details>
              </>
            )}
          </div>
        </div>
      )}
    </>
  );
}

export function Findings({
  sessions,
  role,
  id,
}: {
  sessions: Session[];
  role: string;
  id?: string;
}) {
  const t = useT(),
    notify = useUI((s) => s.notify);
  const [experiment, setExperiment] = useState("");
  const [operation, setOperation] = useState("");
  const selected = id || sessions.at(-1)?.id;
  const current = sessions.find((s) => s.id === selected);
  const experiments = useQuery({
    queryKey: ["experiments", selected, experiment],
    queryFn: () =>
      api<{ items: { id: string; operation: string }[] }>(
        `/sessions/${selected}/experiments`,
      ),
    enabled: !!selected,
  });
  const q = useQuery({
    queryKey: ["findings", selected, experiment, current?.state],
    queryFn: () =>
      api<Finding>(
        experiment
          ? "/experiments/" + experiment
          : `/sessions/${selected}/findings`,
      ),
    enabled: !!selected,
    refetchInterval: current?.state === "recording" ? 3000 : false,
  });
  const begin = useMutation({
    mutationFn: () =>
      api<{ id: string }>(`/sessions/${selected}/experiments`, {
        method: "POST",
        body: JSON.stringify({ operation }),
      }),
    onSuccess: (r) => setExperiment(r.id),
    onError: (e) => notify(e.message),
  });
  const phase = useMutation({
    mutationFn: (p: string) =>
      api(`/experiments/${experiment}/phases`, {
        method: "POST",
        body: JSON.stringify({ phase: p }),
      }),
    onSuccess: () => {
      void q.refetch();
    },
    onError: (e) => notify(e.message),
  });
  const canAnalyze = role !== "viewer";
  return (
    <>
      <h1>{t("findings")}</h1>
      <p>{t("findingsHelp")}</p>
      <label>
        {t("session")}
        <select
          value={selected || ""}
          onChange={(e) => {
            setExperiment("");
            go("findings/" + e.target.value);
          }}
        >
          <option value="">—</option>
          {sessions.map((s) => (
            <option value={s.id} key={s.id}>
              {s.id.slice(0, 12)} · {t(s.state as Key)}
            </option>
          ))}
        </select>
      </label>
      {!!experiments.data?.items.length && (
        <label>
          {t("operation")}
          <select
            value={experiment}
            onChange={(e) => setExperiment(e.target.value)}
          >
            <option value="">—</option>
            {experiments.data.items.map((e) => (
              <option key={e.id} value={e.id}>
                {e.operation} · {e.id.slice(0, 8)}
              </option>
            ))}
          </select>
        </label>
      )}
      {q.isLoading ? (
        <Loading />
      ) : q.error ? (
        <Failure error={q.error} />
      ) : (
        q.data && (
          <>
            <section className="panel finding-summary">
              <h2>{t(classification(q.data.hypothesis.classification))}</h2>
              <p>{t("rankingHelp")}</p>
              <div className="metrics-grid">
                <Metric
                  label={t("suspicion")}
                  value={
                    q.data.hypothesis.score === null
                      ? "—"
                      : String(q.data.hypothesis.score)
                  }
                />
                <Metric
                  label={t("knownRetained")}
                  value={bytes(q.data.hypothesis.known_retained_bytes)}
                />
              </div>
              {q.data.hypothesis.known_retained_bytes === null && (
                <p className="native-warning">{t("inexactNative")}</p>
              )}
              <p>{t("temporalEvidence")}</p>
              <button onClick={() => go("session/" + selected)}>
                {t("inspectCapture")}
              </button>
            </section>
            <h2>{t("retainedSites")}</h2>
            {!q.data.sites.length ? (
              <Empty title={t("noExactSites")} />
            ) : (
              q.data.sites.map((site) => (
                <section className="panel retained-finding" key={site.stack_id}>
                  <h3>{site.frames[0]?.function || t("unknownStack")}</h3>
                  <strong>{bytes(site.known_retained_bytes)}</strong>
                  <span className="domain-tag">{site.domain}</span>
                  <p>
                    {site.attribution_quality ===
                    "allocation_time_python_frames"
                      ? t("exactLabEvidence")
                      : t("temporalEvidence")}
                  </p>
                  <ol>
                    {site.frames.slice(0, 8).map((f, i) => (
                      <li key={i}>
                        <code>{f.function}</code>
                        <span className="mono">
                          {" "}
                          {f.file || f.module}
                          {f.line ? ":" + f.line : ""}
                        </span>
                      </li>
                    ))}
                  </ol>
                  <button onClick={() => go("session/" + selected)}>
                    {t("inspectCapture")}
                  </button>
                </section>
              ))
            )}
            <h2>{t("repeatedInvestigation")}</h2>
            <p>{t("noBusinessExecution")}</p>
            {canAnalyze && current?.state === "recording" && !experiment && (
              <form
                onSubmit={(e) => {
                  e.preventDefault();
                  begin.mutate();
                }}
              >
                <label>
                  {t("operation")}
                  <input
                    value={operation}
                    onChange={(e) => setOperation(e.target.value)}
                    maxLength={80}
                    required
                  />
                </label>
                <button disabled={begin.isPending || !operation}>
                  {t("startExperiment")}
                </button>
              </form>
            )}
            {experiment && (
              <div className="panel">
                <div className="button-row">
                  {[
                    "warmup",
                    "baseline",
                    "repetitions",
                    "cooldown",
                    "comparison",
                  ].map((p) => (
                    <button
                      key={p}
                      disabled={
                        phase.isPending || current?.state !== "recording"
                      }
                      onClick={() => phase.mutate(p)}
                    >
                      {t(("phase_" + p) as Key)}
                    </button>
                  ))}
                </div>
                <ol>
                  {q.data.phases.map((p, i) => (
                    <li key={i}>
                      {t(("phase_" + String(p.phase)) as Key)} ·{" "}
                      {clock(Number(p.timestamp))}
                    </li>
                  ))}
                </ol>
              </div>
            )}
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>{t("operation")}</th>
                    <th>TID</th>
                    <th>{t("executionCount")}</th>
                    <th>p50 / p95</th>
                    <th>{t("retainedPerIteration")}</th>
                  </tr>
                </thead>
                <tbody>
                  {q.data.operations.groups.map((g) => (
                    <tr key={g.operation + g.thread}>
                      <td>{g.operation}</td>
                      <td>{g.thread}</td>
                      <td>{g.execution_count}</td>
                      <td>
                        {g.p50_duration_ms?.toFixed(2)} /{" "}
                        {g.p95_duration_ms?.toFixed(2)} ms
                      </td>
                      <td>{bytes(g.known_retained_bytes_per_iteration)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <details>
              <summary>{t("diagnosticEvidence")}</summary>
              <pre>
                {JSON.stringify(
                  {
                    hypothesis: q.data.hypothesis,
                    recommendations: q.data.recommendations,
                    gc_type_deltas: q.data.gc_type_deltas,
                    quality: q.data.quality,
                  },
                  null,
                  2,
                )}
              </pre>
            </details>
          </>
        )
      )}
      {selected && (
        <IntervalComparison
          key={selected}
          id={selected}
          recording={current?.state === "recording"}
        />
      )}
    </>
  );
}

function IntervalComparison({
  id,
  recording,
}: {
  id: string;
  recording: boolean;
}) {
  const t = useT(),
    notify = useUI((s) => s.notify);
  const [target, setTarget] = useState<"a" | "b">("a");
  const [ranges, setRanges] = useState({ a: [0, 0], b: [0, 0] });
  const timeline = useQuery({
    queryKey: ["comparisonTimeline", id, recording],
    queryFn: () => api<Timeline>(`/sessions/${id}/timeline?points=600`),
    refetchInterval: recording ? 3000 : false,
  });
  const submit = useMutation({
    mutationFn: () =>
      api("/comparisons", {
        method: "POST",
        body: JSON.stringify({
          a: { session_id: id, start: ranges.a[0], end: ranges.a[1] },
          b: { session_id: id, start: ranges.b[0], end: ranges.b[1] },
        }),
      }),
    onSuccess: () => go("comparisons"),
    onError: (e) => notify(e.message),
  });
  return (
    <section className="panel">
      <h2>{t("intervalSelection")}</h2>
      <p>{t("intervalSelectionHelp")}</p>
      <label>
        {t("selectInterval")}
        <select
          value={target}
          onChange={(e) => setTarget(e.target.value as "a" | "b")}
        >
          <option value="a">A</option>
          <option value="b">B</option>
        </select>
      </label>
      {timeline.data && (
        <Chart
          samples={timeline.data.items}
          onSelect={(a, b) => setRanges({ ...ranges, [target]: [a, b] })}
        />
      )}
      <div className="form-grid">
        {(["a", "b"] as const).map((key) => (
          <fieldset key={key}>
            <legend>{key.toUpperCase()}</legend>
            {[0, 1].map((i) => (
              <label key={i}>
                {t(i ? "end" : "start")}
                <input
                  aria-label={key.toUpperCase() + " " + t(i ? "end" : "start")}
                  type="number"
                  step=".001"
                  min="0"
                  value={ranges[key][i]}
                  onChange={(e) => {
                    const next = [...ranges[key]];
                    next[i] = Number(e.target.value);
                    setRanges({ ...ranges, [key]: next });
                  }}
                />
              </label>
            ))}
          </fieldset>
        ))}
      </div>
      <button
        disabled={
          ranges.a[1] <= ranges.a[0] ||
          ranges.b[1] <= ranges.b[0] ||
          submit.isPending
        }
        onClick={() => submit.mutate()}
      >
        {t("compare")}
      </button>
    </section>
  );
}

export function SafetyStatus({ id }: { id: string }) {
  const t = useT();
  const q = useQuery({
    queryKey: ["performance", id],
    queryFn: () =>
      api<{
        effective_policy: string;
        controller: {
          target_cpu_percent?: number;
          sensor_cpu_percent?: number;
          collector_lag_ms?: number;
        };
        capture_window?: { physically_detached?: boolean };
        lost_events: number;
        policy_transitions: unknown[];
      }>(`/sessions/${id}/performance`),
    refetchInterval: 2000,
  });
  if (q.error) return <Failure error={q.error} />;
  if (!q.data) return null;
  const p = q.data,
    c = p.controller;
  return (
    <section className="panel safety-status">
      <div className="panel-head">
        <h3>{t("profilingSafety")}</h3>
        <strong>
          {p.capture_window
            ? p.capture_window.physically_detached
              ? t("instrumentationDetached")
              : t("instrumentationActive")
            : t("metricsNoProbes")}
        </strong>
      </div>
      <div className="button-row">
        <span>
          {t("cpu")}:{" "}
          {c.target_cpu_percent == null
            ? "—"
            : c.target_cpu_percent.toFixed(1) + "%"}
        </span>
        <span>
          {t("sensorCpu")}:{" "}
          {c.sensor_cpu_percent == null
            ? "—"
            : c.sensor_cpu_percent.toFixed(1) + "%"}
        </span>
        <span>
          {t("collectorLag")}:{" "}
          {c.collector_lag_ms == null
            ? "—"
            : c.collector_lag_ms.toFixed(0) + " ms"}
        </span>
        <span>
          {t("lost")}: {p.lost_events}
        </span>
      </div>
      <p className="small">{t("cpuUsageHelp")}</p>
      {p.policy_transitions.length > 0 && (
        <p className="native-warning">{t("policyChanged")}</p>
      )}
    </section>
  );
}

export function ReleaseReadiness() {
  const t = useT();
  const q = useQuery({
    queryKey: ["releaseReadiness"],
    queryFn: () =>
      api<{
        production_ready: boolean;
        release_label: string;
        gates: { key: string; title: string; status: string; reason: string }[];
      }>("/release/readiness"),
  });
  const status: Record<string, Key> = {
    verified: "gateVerified",
    partially_verified: "gatePartial",
    experimental: "gateExperimental",
    unsupported: "gateUnsupported",
    blocked: "gateBlocked",
  };
  return (
    <section className="panel form-panel">
      <h2>{t("releaseReadiness")}</h2>
      {q.isLoading ? (
        <Loading />
      ) : q.error ? (
        <Failure error={q.error} />
      ) : (
        q.data && (
          <>
            <p className={q.data.production_ready ? "" : "native-warning"}>
              {q.data.production_ready ? t("gateCandidate") : t("gatePreview")}
            </p>
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>{t("releaseGate")}</th>
                    <th>{t("state")}</th>
                  </tr>
                </thead>
                <tbody>
                  {q.data.gates.map((g) => (
                    <tr key={g.key}>
                      <td>{t(("gate_" + g.key) as Key)}</td>
                      <td>{t(status[g.status] || "gateBlocked")}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <details>
              <summary>{t("diagnosticEvidence")}</summary>
              <pre>{JSON.stringify(q.data, null, 2)}</pre>
            </details>
          </>
        )
      )}
    </section>
  );
}

export function DeploymentHealth() {
  const t = useT();
  const query = useQuery({
    queryKey: ["deploymentHealth"],
    queryFn: () =>
      api<components["schemas"]["DeploymentHealth"]>("/deployment/health"),
    refetchInterval: 30000,
  });
  const labels: Record<string, Key> = {
    database: "databaseHealth",
    sensor: "sensorHealth",
    native: "nativeAttribution",
  };
  return (
    <section className="panel form-panel" aria-labelledby="deployment-heading">
      <h2 id="deployment-heading">{t("deploymentHealth")}</h2>
      {query.isLoading ? (
        <Loading />
      ) : query.error ? (
        <Failure error={query.error} />
      ) : (
        query.data && (
          <>
            <p>{t("deploymentHealthHelp")}</p>
            <div className="metric-grid">
              <Metric
                label={t("storage")}
                value={bytes(query.data.free_storage_bytes)}
              />
              <Metric
                label={t("activeSessions")}
                value={String(query.data.active_captures)}
              />
            </div>
            <p>
              Linux {query.data.kernel} · Python {query.data.runtime} · SQLite{" "}
              {bytes(query.data.database_bytes)} · WAL{" "}
              {bytes(query.data.wal_bytes)}
            </p>
            <ul>
              {query.data.items.map((item) => (
                <li key={item.component}>
                  <strong>
                    {t(labels[item.component] || "deploymentHealth")}:{" "}
                    {t(
                      item.status === "available" ? "available" : "unavailable",
                    )}
                  </strong>
                  <p>{item.detail}</p>
                </li>
              ))}
            </ul>
            {!query.data.production_ready && (
              <p className="warning">{t("gatePreview")}</p>
            )}
          </>
        )
      )}
    </section>
  );
}
