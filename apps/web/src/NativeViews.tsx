import { useEffect, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api, bytes } from "./api";
import { useT } from "./store";

import type { components } from "../../../packages/api-client/schema";
type Node = components["schemas"]["NativeTreeView"];
export type NativeAnalysis = components["schemas"]["NativeAnalysisView"];
type Rect = { node: Node; x: number; y: number; width: number };
function Flame({
  root,
  search,
  icicle,
}: {
  root: Node;
  search: string;
  icicle: boolean;
}) {
  const t = useT();
  const canvas = useRef<HTMLCanvasElement>(null);
  const [zoom, setZoom] = useState<Node | null>(null);
  const [selected, setSelected] = useState<Node | null>(null);
  const [width, setWidth] = useState(600);
  const rects = useRef<Rect[]>([]);
  const node = zoom || root;
  useEffect(() => {
    setZoom(null);
    setSelected(null);
  }, [root]);
  useEffect(() => {
    if (!canvas.current) return;
    const observer = new ResizeObserver(([entry]) =>
      setWidth(entry.contentRect.width),
    );
    observer.observe(canvas.current);
    return () => observer.disconnect();
  }, []);
  useEffect(() => {
    const ctx = canvas.current?.getContext("2d");
    if (!ctx || !canvas.current) return;
    const ratio = window.devicePixelRatio || 1;
    canvas.current.width = width * ratio;
    canvas.current.height = 360 * ratio;
    ctx.scale(ratio, ratio);
    ctx.clearRect(0, 0, width, 360);
    rects.current = [];
    function draw(n: Node, x: number, w: number, depth: number) {
      if (w < 1 || depth > 15) return;
      const y = icicle ? depth * 22 : 338 - depth * 22;
      rects.current.push({ node: n, x, y, width: w });
      const match =
        search && n.name.toLowerCase().includes(search.toLowerCase());
      ctx!.fillStyle = match
        ? "#f59e0b"
        : `hsl(${155 + depth * 9} 45% ${35 + (depth % 4) * 6}%)`;
      ctx!.fillRect(x, y, Math.max(0, w - 1), 21);
      if (w > 35) {
        ctx!.save();
        ctx!.beginPath();
        ctx!.rect(x + 4, y, w - 8, 21);
        ctx!.clip();
        ctx!.fillStyle = "#fff";
        ctx!.font = "11px monospace";
        ctx!.fillText(n.name.split(" · ").at(-1) || n.name, x + 5, y + 15);
        ctx!.restore();
      }
      let cursor = x;
      for (const c of Object.values(n.children)) {
        const cw = (w * c.value) / Math.max(1, n.value);
        draw(c, cursor, cw, depth + 1);
        cursor += cw;
      }
    }
    draw(node, 0, width, 0);
  }, [node, search, icicle, width]);
  return (
    <div className="native-flame">
      <div className="native-toolbar">
        <button onClick={() => setZoom(null)}>{t("resetZoom")}</button>
        <span>
          {bytes(node.value)} · {node.count.toLocaleString()} {t("allocations")}
        </span>
      </div>
      <canvas
        ref={canvas}
        role="img"
        tabIndex={0}
        aria-label={t("nativeFlameHelp")}
        style={{ width: "100%", height: 360 }}
        onMouseMove={(e) => {
          const bounds = e.currentTarget.getBoundingClientRect();
          setSelected(
            [...rects.current]
              .reverse()
              .find(
                (r) =>
                  e.clientX - bounds.left >= r.x &&
                  e.clientX - bounds.left <= r.x + r.width &&
                  e.clientY - bounds.top >= r.y &&
                  e.clientY - bounds.top < r.y + 22,
              )?.node || null,
          );
        }}
        onClick={() => selected && setZoom(selected)}
        onKeyDown={(e) => {
          if (e.key === "Escape") setZoom(null);
          if (e.key === "Enter" && selected) setZoom(selected);
        }}
      />
      <p className="mono native-selection" aria-live="polite">
        {selected
          ? `${selected.name} · ${bytes(selected.value)} · ${selected.count}`
          : t("nativeFlameHelp")}
      </p>
      <details>
        <summary>{t("calltree")}</summary>
        <CallTree root={node} />
      </details>
    </div>
  );
}
function CallTree({ root }: { root: Node }) {
  const t = useT();
  function branch(n: Node, depth: number): React.ReactNode {
    if (depth > 12) return null;
    return (
      <li key={n.name}>
        <details open={depth < 1}>
          <summary>
            <span>{depth === 0 ? t("allocations") : n.name}</span>{" "}
            <strong>{bytes(n.value)}</strong> <small>{n.count}</small>
          </summary>
          <ul>
            {Object.values(n.children)
              .slice(0, 100)
              .map((c) => branch(c, depth + 1))}
          </ul>
        </details>
      </li>
    );
  }
  return <ul className="native-calltree">{branch(root, 0)}</ul>;
}
export function NativeViews({
  id,
  tab,
  start,
  end,
  active,
  state,
}: {
  id: string;
  tab: string;
  start?: number;
  end?: number;
  active: boolean;
  state: string;
}) {
  const t = useT();
  const saved = new URLSearchParams(window.location.search);
  const [symbol, setSymbol] = useState(saved.get("symbol") || "");
  const [library, setLibrary] = useState(saved.get("library") || "");
  const [thread, setThread] = useState(saved.get("thread") || "");
  const [minimum, setMinimum] = useState("");
  const [retained, setRetained] = useState(tab === "survivors");
  const [icicle, setIcicle] = useState(false);
  const params = new URLSearchParams();
  if (symbol) params.set("symbol", symbol);
  if (library) params.set("library", library);
  if (thread && Number(thread) > 0) params.set("thread", thread);
  if (minimum && Number(minimum) >= 0) params.set("min_size", minimum);
  if (start !== undefined) params.set("start", String(start));
  if (end !== undefined) params.set("end", String(end));
  useEffect(() => {
    const p = new URLSearchParams();
    if (symbol) p.set("symbol", symbol);
    if (library) p.set("library", library);
    if (thread) p.set("thread", thread);
    window.history.replaceState(
      null,
      "",
      window.location.pathname + (p.size ? "?" + p : "") + window.location.hash,
    );
  }, [symbol, library, thread]);
  const q = useQuery({
    queryKey: ["native", id, params.toString(), state],
    queryFn: () => api<NativeAnalysis>(`/sessions/${id}/allocations?${params}`),
    refetchInterval: active ? 2000 : false,
  });
  const data = q.data;
  const tree = data
    ? retained || tab === "survivors"
      ? data.exact_survivors
        ? data.retained_tree
        : null
      : data.allocation_tree
    : null;
  return (
    <div className="native-view">
      <p className="small muted">{t("nativeOnly")}</p>
      <div className="native-filters">
        <label>
          {t("symbolFilter")}
          <input
            value={symbol}
            onChange={(e) => setSymbol(e.target.value)}
            maxLength={256}
          />
        </label>
        <label>
          {t("libraryFilter")}
          <input
            value={library}
            onChange={(e) => setLibrary(e.target.value)}
            maxLength={256}
          />
        </label>
        <label>
          {t("threadFilter")}
          <input
            type="number"
            min="1"
            value={thread}
            onChange={(e) => setThread(e.target.value)}
          />
        </label>
        <label>
          {t("minimumSize")}
          <input
            type="number"
            min="0"
            value={minimum}
            onChange={(e) => setMinimum(e.target.value)}
          />
        </label>
      </div>
      {q.isLoading && <p role="status">{t("loading")}</p>}
      {q.error && <p role="alert">{q.error.message}</p>}
      {data && (
        <>
          <div className="native-totals">
            <span>
              {t("observedAllocated")}:{" "}
              <strong>{bytes(data.selected_allocated_bytes)}</strong>
            </span>
            <span>
              {t("nativeLive")}:{" "}
              <strong>
                {data.exact_survivors ? bytes(data.retained_tree.value) : "—"}
              </strong>
            </span>
            <span>
              {t("lost")}: <strong>{data.lost_events}</strong>
            </span>
          </div>
          {!data.exact_survivors && (
            <p className="native-warning" role="status">
              {t("inexactNative")}
            </p>
          )}
          <div className="native-toolbar">
            <label>
              <input
                type="checkbox"
                checked={retained || tab === "survivors"}
                onChange={(e) => setRetained(e.target.checked)}
              />
              {t("survivors")}
            </label>
            <label>
              <input
                type="checkbox"
                checked={icicle}
                onChange={(e) => setIcicle(e.target.checked)}
              />
              {t("icicle")}
            </label>
          </div>
          {tree && tree.value > 0 ? (
            tab === "calltree" ? (
              <CallTree root={tree} />
            ) : (
              <Flame root={tree} search={symbol} icicle={icicle} />
            )
          ) : (
            <p>{t("noNativeSites")}</p>
          )}
          <div className="table-scroll">
            <table>
              <caption>{t("nativeSites")}</caption>
              <thead>
                <tr>
                  <th>{t("symbolFilter")}</th>
                  <th>{t("observedAllocated")}</th>
                  <th>{t("nativeLive")}</th>
                </tr>
              </thead>
              <tbody>
                {data.top_sites.slice(0, 100).map((site) => (
                  <tr key={site.stack_id}>
                    <td>
                      <button
                        className="native-site"
                        onClick={() =>
                          setSymbol(
                            site.frames?.find(
                              (f) =>
                                ![
                                  "malloc",
                                  "calloc",
                                  "realloc",
                                  "__libc_malloc",
                                  "__libc_calloc",
                                  "__libc_realloc",
                                ].includes(f.function) &&
                                !f.function.startsWith("["),
                            )?.function ||
                              site.frames?.[1]?.function ||
                              "",
                          )
                        }
                        title={site.frames
                          ?.map((f) => `${f.module} · ${f.function}`)
                          .join("\n")}
                      >
                        {site.frames?.find(
                          (f) =>
                            ![
                              "malloc",
                              "calloc",
                              "realloc",
                              "__libc_malloc",
                              "__libc_calloc",
                              "__libc_realloc",
                            ].includes(f.function) &&
                            !f.function.startsWith("["),
                        )?.function ||
                          site.frames?.[1]?.function ||
                          t("unknownStack")}
                      </button>
                    </td>
                    <td>
                      <details>
                        <summary>{bytes(site.allocated_bytes)}</summary>
                        <ol>
                          {site.frames?.map((frame, i) => (
                            <li key={i}>
                              <code>
                                {frame.module} · {frame.function}
                              </code>
                              {frame.file && (
                                <small>
                                  {frame.file}
                                  {frame.line ? `:${frame.line}` : ""}
                                </small>
                              )}
                            </li>
                          ))}
                        </ol>
                      </details>
                    </td>
                    <td>{bytes(site.known_live_bytes)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  );
}

export function NativeStats({
  id,
  active,
  state,
}: {
  id: string;
  active: boolean;
  state: string;
}) {
  const t = useT();
  const q = useQuery({
    queryKey: ["native-stats", id, state],
    queryFn: () => api<NativeAnalysis>(`/sessions/${id}/allocations`),
    refetchInterval: active ? 2000 : false,
  });
  return (
    <div className="native-totals" aria-live="polite">
      <span>
        {t("nativeLive")}:{" "}
        <strong>
          {q.data?.exact_survivors ? bytes(q.data.retained_tree.value) : "—"}
        </strong>
      </span>
      <span>
        {t("allocations")}: <strong>{q.data?.allocation_count ?? "—"}</strong>
      </span>
      <span>
        {t("observedAllocated")}:{" "}
        <strong>{bytes(q.data?.allocated_bytes)}</strong>
      </span>
    </div>
  );
}
