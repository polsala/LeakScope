//! Deterministic evidence ranking. Scores are heuristic ranks, never probabilities.
//! Metrics establish growth; only complete allocation lifetimes establish observed
//! survivors. Independent capture windows cannot establish cross-window lifetimes.
use crate::theil_sen;
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};

#[derive(Clone, Debug, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Point {
    pub timestamp: f64,
    pub rss: u64,
    #[serde(default)]
    pub operations: Option<u64>,
}
#[derive(Clone, Debug, Deserialize)]
#[serde(default, deny_unknown_fields)]
pub struct Thresholds {
    pub minimum_observation_seconds: f64,
    pub warmup_seconds: f64,
    pub window_seconds: f64,
    pub sustained_windows: usize,
    pub minimum_growth_bytes: u64,
    pub minimum_rate_bytes_per_hour: f64,
    pub maximum_sample_gap_seconds: f64,
}
impl Default for Thresholds {
    fn default() -> Self {
        Self {
            minimum_observation_seconds: 900.,
            warmup_seconds: 300.,
            window_seconds: 300.,
            sustained_windows: 3,
            minimum_growth_bytes: 50 * 1024 * 1024,
            minimum_rate_bytes_per_hour: 20. * 1024. * 1024.,
            maximum_sample_gap_seconds: 60.,
        }
    }
}
#[derive(Default, Debug, Deserialize)]
#[serde(default, deny_unknown_fields)]
pub struct Evidence {
    pub domain: String,
    pub known_live_bytes: Option<u64>,
    pub exact_survivors: bool,
    pub lost_events: u64,
    pub capture_gaps: bool,
    pub repeated_operations: u64,
    pub survived_cooldown: bool,
    pub stable_allocation_sites: bool,
    pub gc_count_delta: Option<i64>,
    pub gc_visibility: String,
    pub attribution_quality: String,
    pub cleanup_control: Option<bool>,
    pub process_key: String,
    pub operation: Option<String>,
    pub source_locations: Vec<Value>,
}
#[derive(Default, Debug, Deserialize)]
#[serde(default, deny_unknown_fields)]
pub struct Input {
    pub samples: Vec<Point>,
    pub thresholds: Thresholds,
    pub evidence: Evidence,
}
#[derive(Debug, Serialize)]
pub struct Recommendation {
    pub action: &'static str,
    pub reason: &'static str,
    pub required_capabilities: Vec<&'static str>,
    pub expected_observability: &'static str,
    pub expected_overhead: &'static str,
    pub operational_risk: &'static str,
    pub uncertainty: &'static str,
}
pub fn analyze(input: &Input) -> Result<Value, String> {
    let t = &input.thresholds;
    if input.samples.len() > 4096
        || input.evidence.source_locations.len() > 40
        || !(1..=12).contains(&t.sustained_windows)
        || ![
            t.minimum_observation_seconds,
            t.warmup_seconds,
            t.window_seconds,
            t.minimum_rate_bytes_per_hour,
            t.maximum_sample_gap_seconds,
        ]
        .iter()
        .all(|v| v.is_finite() && *v >= 0.)
        || t.window_seconds < 0.1
        || t.maximum_sample_gap_seconds <= 0.
    {
        return Err("diagnosis input exceeds bounded observation limits".into());
    }
    if input.samples.iter().any(|p| !p.timestamp.is_finite())
        || input
            .samples
            .windows(2)
            .any(|w| w[1].timestamp <= w[0].timestamp)
    {
        return Err("metrics must have finite, strictly increasing timestamps".into());
    }
    let first = input.samples.first().map(|p| p.timestamp).unwrap_or(0.);
    let points: Vec<_> = input
        .samples
        .iter()
        .filter(|p| p.timestamp >= first + t.warmup_seconds)
        .collect();
    let span = points
        .first()
        .zip(points.last())
        .map(|(a, b)| b.timestamp - a.timestamp)
        .unwrap_or(0.);
    let delta = points
        .first()
        .zip(points.last())
        .map(|(a, b)| b.rss as f64 - a.rss as f64);
    let pairs: Vec<_> = points.iter().map(|p| (p.timestamp, p.rss as f64)).collect();
    let rate = theil_sen(&pairs);
    let mut windows = vec![];
    let mut supported = true;
    if let Some(last) = points.last() {
        for i in (0..t.sustained_windows).rev() {
            let end = last.timestamp - i as f64 * t.window_seconds;
            let start = end - t.window_seconds;
            let window: Vec<_> = pairs
                .iter()
                .copied()
                .filter(|(time, _)| *time >= start && *time <= end)
                .collect();
            supported &= window.len() >= 3
                && window
                    .last()
                    .zip(window.first())
                    .is_some_and(|(b, a)| b.0 - a.0 >= t.window_seconds * 0.6);
            windows.push(json!({"start":start,"end":end,"samples":window.len(),"slope_bytes_per_second":theil_sen(&window)}));
        }
    }
    let gaps = points
        .windows(2)
        .any(|w| w[1].timestamp - w[0].timestamp > t.maximum_sample_gap_seconds);
    let enough = points.len() >= 10 && span >= t.minimum_observation_seconds && supported && !gaps;
    let recent = windows
        .last()
        .and_then(|v| v["slope_bytes_per_second"].as_f64())
        .unwrap_or(0.);
    let noise = points
        .first()
        .map(|p| (p.rss as f64 * 0.005).max(4096.))
        .unwrap_or(4096.);
    let peak = points.iter().map(|p| p.rss).max().unwrap_or(0) as f64;
    let edges = points
        .first()
        .zip(points.last())
        .map(|(a, b)| a.rss.max(b.rss))
        .unwrap_or(0) as f64;
    let transient = enough && peak - edges > noise;
    let plateau = enough
        && delta.unwrap_or(0.) > noise
        && recent.abs()
            < rate
                .unwrap_or(0.)
                .abs()
                .max(t.minimum_rate_bytes_per_hour / 3600.)
                * 0.1;
    let sustained = enough
        && !plateau
        && delta.unwrap_or(0.) >= t.minimum_growth_bytes as f64
        && windows.iter().all(|w| {
            w["slope_bytes_per_second"].as_f64().unwrap_or(0.) * 3600.
                >= t.minimum_rate_bytes_per_hour
        });
    let trend = if !enough {
        "insufficient_evidence"
    } else if transient {
        "transient_spike"
    } else if plateau {
        "plateau"
    } else if sustained {
        "sustained_growth"
    } else {
        "no_sustained_growth"
    };
    let normalized = points.first().zip(points.last()).and_then(|(a, b)| {
        Some(
            delta?
                / b.operations?
                    .checked_sub(a.operations?)
                    .filter(|n| *n > 0)? as f64,
        )
    });
    let change_point = windows
        .windows(2)
        .find(|p| {
            p[1]["slope_bytes_per_second"].as_f64().unwrap_or(0.)
                > p[0]["slope_bytes_per_second"]
                    .as_f64()
                    .unwrap_or(0.)
                    .max(t.minimum_rate_bytes_per_hour / 3600.)
                    * 3.
        })
        .map(|p| p[1]["start"].clone());
    let e = &input.evidence;
    let exact = e.exact_survivors && e.lost_events == 0 && !e.capture_gaps;
    let retained = exact.then_some(e.known_live_bytes).flatten();
    let mut support = vec![];
    let mut contradiction = vec![];
    let mut limitations = vec![
        "RSS growth is not proof of an allocation leak.",
        "Memory domains overlap and are not additive.",
        "Temporal operation/function association does not establish reference ownership.",
    ];
    if gaps {
        limitations.push("Metrics contain an observation gap; sustained growth is unqualified.");
    }
    if !exact {
        limitations.push("Exact retained allocation evidence is unavailable or invalidated.");
    }
    if e.capture_gaps {
        limitations.push(
            "Detached windows cannot be combined into a continuous allocation-lifetime trace.",
        );
    }
    if e.gc_visibility == "gc_generation_zero_only" {
        limitations
            .push("Generation-zero GC changes are partial and can reflect generation migration.");
    }
    if sustained {
        support
            .push("Resistant positive growth persists across all configured post-warm-up windows.");
    }
    if retained.is_some_and(|n| n > 0) {
        support.push(
            "A complete capture contains observed surviving allocations in the selected domain.",
        );
    }
    if e.survived_cooldown {
        support.push("Observation includes an explicit completed cooldown interval.");
    }
    if e.repeated_operations >= 3 {
        support.push("At least three completed selected operations were observed.");
    }
    if e.gc_count_delta.is_some_and(|n| n > 0) {
        support.push(
            "Comparable bounded GC snapshots show type-count growth; visibility limitations apply.",
        );
    }
    if e.cleanup_control == Some(true) {
        contradiction.push("The supplied cleanup control did not retain observed allocations.");
    }
    if plateau {
        contradiction.push("Recent memory growth stabilized despite earlier growth.");
    }
    if transient {
        contradiction.push("Memory declined after an intermediate peak.");
    }
    let (classification, score) = if !enough || e.lost_events > 0 || e.capture_gaps {
        ("insufficient_evidence", None)
    } else if transient {
        ("temporary_allocation_spike", Some(5))
    } else if plateau {
        ("likely_bounded_cache_or_warmup", Some(10))
    } else if sustained
        && retained.is_some_and(|n| n > 0)
        && e.survived_cooldown
        && e.repeated_operations >= 3
    {
        (
            if e.domain == "python_block"
                && e.attribution_quality == "allocation_time_python_frames"
            {
                "likely_retained_python_references"
            } else {
                "likely_native_memory_retention"
            },
            Some(
                65 + if e.stable_allocation_sites { 10 } else { 0 }
                    + if e.cleanup_control == Some(true) {
                        10
                    } else {
                        0
                    },
            ),
        )
    } else if sustained {
        ("possible_unbounded_cache", Some(35))
    } else if retained == Some(0) && delta.unwrap_or(0.) > noise {
        ("possible_allocator_fragmentation", Some(20))
    } else {
        ("insufficient_evidence", None)
    };
    let rec = if e.lost_events > 0 || e.capture_gaps {
        Recommendation {
            action: "shorter_capture",
            reason: "Loss or detached intervals invalidate exact end survivors.",
            required_capabilities: vec!["observe"],
            expected_observability: "Independent short windows with explicit loss and gaps",
            expected_overhead: "Lower amortized cost; active native cost remains high",
            operational_risk: "bounded",
            uncertainty: "No cross-gap allocation survival inference",
        }
    } else if e.gc_count_delta.is_some_and(|n| n > 0) {
        Recommendation {
            action: "controlled_python_comparison",
            reason: "GC-visible growth needs controlled allocation and cleanup evidence.",
            required_capabilities: vec!["deep"],
            expected_observability: "Operation boundaries and bounded type deltas; Lab exact lines only if verified",
            expected_overhead: "Workload dependent; Deep and Lab can be expensive",
            operational_risk: "staging_recommended",
            uncertainty: "GC-visible objects are not the whole heap",
        }
    } else if plateau {
        Recommendation {
            action: "observe_cooldown",
            reason: "Growth stabilized; collect longer cooldown and allocator-domain evidence.",
            required_capabilities: vec!["observe"],
            expected_observability: "RSS/PSS plateau, lifecycle and workload context",
            expected_overhead: "Metrics only; no allocator probes",
            operational_risk: "low",
            uncertainty: "RSS retention can be caches, arenas or fragmentation",
        }
    } else {
        Recommendation {
            action: "bounded_native_window",
            reason: "Metrics alone cannot identify the allocation sites causing growth.",
            required_capabilities: vec!["external_allocations"],
            expected_observability: "Selected observed native allocation lifetimes and native stacks",
            expected_overhead: "High while probes are attached; bounded and measured separately",
            operational_risk: "operator_authorization_required",
            uncertainty: "Native visibility is incomplete for Python objects; no ownership proof",
        }
    };
    Ok(
        json!({"trend":{"classification":trend,"anomaly":sustained&&!transient,"sample_count":points.len(),"span_seconds":span,"rss_delta_bytes":delta,"slope_bytes_per_second":rate,"recent_slope_bytes_per_second":recent,"growth_bytes_per_operation":normalized,"change_point":change_point,"windows":windows,"has_sampling_gap":gaps,"warmup_excluded_seconds":t.warmup_seconds},"hypothesis":{"classification":classification,"score":score,"score_kind":"heuristic_ranking_not_probability","supporting_evidence":support,"contradictory_evidence":contradiction,"limitations":limitations,"attribution_quality":e.attribution_quality,"known_retained_bytes":retained,"process_key":e.process_key,"operation":e.operation,"source_locations":e.source_locations,"recommended_validation":rec},"recommendations":[rec]}),
    )
}

#[cfg(test)]
mod tests {
    use super::*;
    fn input(kind: &str) -> Input {
        Input {
            samples: (0..61)
                .map(|i| Point {
                    timestamp: i as f64,
                    rss: 100_000_000
                        + match kind {
                            "leak" => i * 1_000_000,
                            "cache" => i.min(20) * 1_000_000,
                            "spike" => {
                                if (20..40).contains(&i) {
                                    30_000_000
                                } else {
                                    0
                                }
                            }
                            _ => 0,
                        },
                    operations: Some(i),
                })
                .collect(),
            thresholds: Thresholds {
                minimum_observation_seconds: 30.,
                warmup_seconds: 0.,
                window_seconds: 10.,
                minimum_growth_bytes: 10_000_000,
                minimum_rate_bytes_per_hour: 1_000_000.,
                maximum_sample_gap_seconds: 3.,
                ..Default::default()
            },
            ..Default::default()
        }
    }
    #[test]
    fn sustained_growth_needs_multiple_windows_and_richer_evidence() {
        let mut i = input("leak");
        let r = analyze(&i).unwrap();
        assert_eq!(r["trend"]["anomaly"], true);
        assert_eq!(
            r["hypothesis"]["classification"],
            "possible_unbounded_cache"
        );
        i.evidence = Evidence {
            exact_survivors: true,
            known_live_bytes: Some(60_000_000),
            domain: "python_block".into(),
            attribution_quality: "allocation_time_python_frames".into(),
            survived_cooldown: true,
            repeated_operations: 10,
            ..Default::default()
        };
        let r = analyze(&i).unwrap();
        assert_eq!(
            r["hypothesis"]["classification"],
            "likely_retained_python_references"
        );
        assert!(
            !r["hypothesis"]["supporting_evidence"]
                .as_array()
                .unwrap()
                .is_empty()
        );
        i.evidence.capture_gaps = true;
        let r = analyze(&i).unwrap();
        assert!(r["hypothesis"]["score"].is_null());
        assert!(r["hypothesis"]["known_retained_bytes"].is_null());
    }
    #[test]
    fn negative_controls_plateau_spike_cleanup_and_warmup() {
        for (kind, classification) in [
            ("cache", "likely_bounded_cache_or_warmup"),
            ("spike", "temporary_allocation_spike"),
            ("clean", "insufficient_evidence"),
        ] {
            let r = analyze(&input(kind)).unwrap();
            assert_eq!(r["trend"]["anomaly"], false);
            assert_eq!(r["hypothesis"]["classification"], classification);
        }
        let mut i = input("cache");
        i.thresholds.warmup_seconds = 25.;
        assert_eq!(analyze(&i).unwrap()["trend"]["anomaly"], false);
        i.samples[40].timestamp = 1.;
        assert!(analyze(&i).is_err());
    }
    #[test]
    fn loss_and_observation_gaps_suppress_precise_claims() {
        let mut i = input("leak");
        i.evidence.lost_events = 1;
        assert!(analyze(&i).unwrap()["hypothesis"]["score"].is_null());
        i.samples.retain(|p| p.timestamp < 20. || p.timestamp > 45.);
        assert_eq!(analyze(&i).unwrap()["trend"]["anomaly"], false);
    }
}
