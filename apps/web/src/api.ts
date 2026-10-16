import { useUI } from "./store";
import type { components } from "../../../packages/api-client/schema";
export type Sample = components["schemas"]["SampleView"];
export type Process = components["schemas"]["ProcessView"];
export type Session = Omit<
  components["schemas"]["SessionView"],
  "config" | "quality"
> & {
  config: { mode: string; duration_seconds: number };
  quality: {
    coverage: string;
    lost_samples: number;
    incomplete: boolean;
    event_count?: number;
    lost_events?: number;
    lost_native?: number;
    native_failure?: string;
  };
};
export type Summary = {
  sample_count: number;
  rss_delta_bytes: number | null;
  rss_slope_bytes_per_second: number | null;
  classification: string;
  suspicion_score: number;
  confidence: string;
  supporting_evidence: string[];
  limitations: string[];
  followup: string;
};
export type Timeline = {
  items: Sample[];
  markers: { id: string; timestamp: number; name: string }[];
  summary: Summary;
  quality: Session["quality"];
};
export type Page<T> = { items: T[]; next_cursor: string | null };
export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}
export async function raw(path: string, init: RequestInit = {}) {
  const response = await fetch("/api/v1" + path, {
    ...init,
    headers: {
      Authorization: "Bearer " + useUI.getState().token,
      ...(init.body && typeof init.body === "string"
        ? { "Content-Type": "application/json" }
        : {}),
      ...init.headers,
    },
  });
  if (!response.ok) {
    const data = await response.json().catch(() => null);
    throw new ApiError(
      response.status,
      data?.error?.message || response.statusText,
    );
  }
  return response;
}
export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  return (await raw(path, init)).json();
}
export async function download(path: string, name: string) {
  const blob = await (await raw(path)).blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
export function bytes(v: number | null | undefined) {
  if (v == null) return "—";
  if (v === 0) return "0 B";
  const i = Math.min(3, Math.floor(Math.log(Math.abs(v)) / Math.log(1024)));
  return `${(v / 1024 ** Math.max(0, i)).toFixed(i > 0 ? 1 : 0)} ${["B", "KiB", "MiB", "GiB"][Math.max(0, i)]}`;
}
