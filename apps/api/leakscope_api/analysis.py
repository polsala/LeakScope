"""Resistant, bounded metrics analysis. RSS is never proof of retained allocations."""

import statistics

LIMITATIONS = [
    "RSS growth alone does not establish a leak.",
    "Allocations predating attachment are unknown.",
    "OS memory, native allocations, Python blocks and GC objects are separate non-additive domains.",
    "Metrics-only capture cannot identify allocation sites or reference ownership.",
]


def slope(points):
    points = points[:: max(1, len(points) // 256)][:256]
    rates = [
        (b[1] - a[1]) / (b[0] - a[0])
        for i, a in enumerate(points)
        for b in points[i + 1 :]
        if b[0] > a[0]
    ]
    return statistics.median(rates) if rates else None


def summarize(samples: list[dict], quality: dict | None = None) -> dict:
    quality = quality or {}
    points = [(s["timestamp"], s["rss"]) for s in samples]
    rate = slope(points)
    delta = points[-1][1] - points[0][1] if points else None
    kind = "insufficient_evidence"
    score = 0
    supporting = []
    followup = "Collect at least ten samples spanning a controlled workload and cooldown."
    if len(points) >= 10 and points[-1][0] - points[0][0] >= 2:
        noise = max(4096, points[0][1] * 0.005)
        recent = slope(points[-max(4, len(points) // 3) :]) or 0
        if delta is not None and delta > noise and rate and rate > 0:
            kind, score = "sustained_growth", 40
            supporting.append("Positive median pairwise RSS slope across the capture.")
            followup = "Repeat the operation with a control, add cooldown markers, then collect cooperative GC evidence."
            if recent < rate * 0.1:
                kind, score = "possible_cache_plateau", 20
                supporting.append(
                    "Recent growth is much lower than the whole-capture slope; bounded cache growth is possible."
                )
        elif max(v for _, v in points) - max(points[0][1], points[-1][1]) > noise:
            kind, score = "transient_spike", 5
            supporting.append("RSS returned near its starting level after an intermediate peak.")
        else:
            kind, score = "no_sustained_growth_observed", 0
            supporting.append(
                "This observation window does not show sustained positive RSS growth."
            )
    lost = quality.get("lost_samples", 0)
    if lost or quality.get("incomplete"):
        score = max(0, score - 20)
    return {
        "sample_count": len(points),
        "rss_delta_bytes": delta,
        "rss_slope_bytes_per_second": rate,
        "classification": kind,
        "suspicion_score": score,
        "score_kind": "hypothesis_ranking_only",
        "confidence": "low" if len(points) < 10 or lost else "metrics_only",
        "supporting_evidence": supporting,
        "limitations": LIMITATIONS,
        "followup": followup,
        "known_live_allocations": None,
        "lost_samples": lost,
    }


def compare(a, b, aq, bq):
    sa, sb = summarize(a, aq), summarize(b, bq)
    warnings = []
    if aq.get("coverage") != bq.get("coverage"):
        warnings.append(
            "Coverage differs. Allocation and GC metrics must not be compared across these sessions."
        )
    if aq.get("incomplete") or bq.get("incomplete"):
        warnings.append("At least one capture is incomplete; interpretation is limited.")
    ar, br = sa["rss_slope_bytes_per_second"], sb["rss_slope_bytes_per_second"]
    return {
        "a": sa,
        "b": sb,
        "rss_slope_change": br - ar if ar is not None and br is not None else None,
        "metric": "os_process.rss",
        "warnings": warnings,
        "limitations": LIMITATIONS,
    }
