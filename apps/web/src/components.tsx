import type { ReactNode } from "react";
import * as Dialog from "@radix-ui/react-dialog";
import { X, Activity, AlertTriangle, Info, LoaderCircle } from "lucide-react";
import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { bytes, type Sample } from "./api";
import { useT } from "./store";
import type { Key } from "./i18n";

export function Modal({
  title,
  children,
  close,
}: {
  title: string;
  children: ReactNode;
  close: () => void;
}) {
  const t = useT();
  return (
    <Dialog.Root open onOpenChange={(v) => !v && close()}>
      <Dialog.Portal>
        <Dialog.Overlay className="modal-overlay" />
        <Dialog.Content className="modal">
          <div className="modal-head">
            <Dialog.Title>{title}</Dialog.Title>
            <Dialog.Close aria-label={t("close")} className="icon-button">
              <X size={18} />
            </Dialog.Close>
          </div>
          <Dialog.Description className="sr-only">{title}</Dialog.Description>
          {children}
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
export function Badge({ value }: { value: string }) {
  const t = useT();
  const known = [
    "recording",
    "ready",
    "degraded",
    "failed",
    "processing",
    "stopping",
    "starting",
    "created",
    "preflight",
    "cancelled",
    "expired",
  ];
  return (
    <span className={"badge " + value}>
      <span className="dot" />
      {known.includes(value) ? t(value as Key) : value}
    </span>
  );
}
export function Empty({
  title,
  description,
  action,
}: {
  title: string;
  description?: string;
  action?: ReactNode;
}) {
  return (
    <div className="empty">
      <Activity size={30} strokeWidth={1.3} />
      <h3>{title}</h3>
      {description && <p>{description}</p>}
      {action}
    </div>
  );
}
export function Loading() {
  const t = useT();
  return (
    <div className="loading" role="status">
      <LoaderCircle size={20} className="spin" />
      {t("loading")}
    </div>
  );
}
export function Failure({
  error,
  retry,
}: {
  error: unknown;
  retry?: () => void;
}) {
  const t = useT();
  return (
    <div role="alert" className="failure">
      <AlertTriangle size={20} />
      <div>
        <strong>{t("error")}</strong>
        <p>{error instanceof Error ? error.message : t("error")}</p>
        {retry && <button onClick={retry}>{t("retry")}</button>}
      </div>
    </div>
  );
}
export function Capability() {
  const t = useT();
  return (
    <div className="capability">
      <Info size={20} />
      <div>
        <strong>{t("capabilityTitle")}</strong>
        <p>{t("capabilityBody")}</p>
      </div>
      <span className="mono">OBSERVE</span>
    </div>
  );
}
export function Chart({ samples }: { samples: Sample[] }) {
  const t = useT();
  if (!samples.length)
    return <Empty title={t("noTimeline")} description={t("noTimelineSub")} />;
  return (
    <>
      <div
        className="chart"
        role="img"
        aria-label={`${t("memoryTrend")}: ${samples.length} ${t("samples")}, ${bytes(samples[0].rss)} → ${bytes(samples.at(-1)?.rss)}`}
      >
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart
            data={samples}
            margin={{ top: 20, right: 18, bottom: 0, left: 4 }}
          >
            <defs>
              <linearGradient id="memory-fill" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="#37cbbb" stopOpacity={0.24} />
                <stop offset="100%" stopColor="#37cbbb" stopOpacity={0} />
              </linearGradient>
            </defs>
            <CartesianGrid
              strokeDasharray="3 6"
              vertical={false}
              stroke="var(--border)"
            />
            <XAxis
              dataKey="timestamp"
              tickFormatter={(v) => new Date(v * 1000).toLocaleTimeString()}
              minTickGap={60}
              tick={{ fill: "var(--muted)", fontSize: 11 }}
              axisLine={false}
              tickLine={false}
            />
            <YAxis
              tickFormatter={(v) => bytes(v)}
              domain={["auto", "auto"]}
              tick={{ fill: "var(--muted)", fontSize: 11 }}
              width={76}
              axisLine={false}
              tickLine={false}
            />
            <Tooltip
              labelFormatter={(v) =>
                new Date(Number(v) * 1000).toLocaleTimeString()
              }
              formatter={(v) => [bytes(Number(v)), t("rss")]}
              contentStyle={{
                background: "var(--panel)",
                border: "1px solid var(--border)",
                borderRadius: 8,
              }}
            />
            <Area
              type="linear"
              dataKey="rss"
              stroke="#37cbbb"
              strokeWidth={2}
              fill="url(#memory-fill)"
              isAnimationActive={false}
            />
          </AreaChart>
        </ResponsiveContainer>
      </div>
      <p className="chart-note">{t("rssHelp")}</p>
    </>
  );
}
export function Metric({
  label,
  value,
  hint,
  icon,
}: {
  label: string;
  value: ReactNode;
  hint?: string;
  icon?: ReactNode;
}) {
  return (
    <div className="metric">
      <div className="metric-label">
        {label}
        {icon}
      </div>
      <div className="metric-value">{value}</div>
      {hint && <div className="metric-hint">{hint}</div>}
    </div>
  );
}
