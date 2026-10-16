//! Memory domains never sum: arena backing and object blocks overlap.
pub mod diagnosis;
pub use leakscope_protocol::AllocationEvent as Event;
use serde::Serialize;
use std::collections::HashMap;
#[derive(Debug, Clone, Serialize)]
pub struct Allocation {
    pub size: u64,
    pub generation: u64,
    pub timestamp: f64,
    pub monotonic_ns: Option<u64>,
    pub stack: Option<String>,
    pub operation: Option<String>,
    pub thread: u64,
}
type Key = (String, String, u64);
#[derive(Default)]
pub struct Lifecycle {
    pub live: HashMap<Key, Allocation>,
    generation: u64,
    last: HashMap<(String, String, String), u64>,
    pub allocated: u64,
    pub freed: u64,
    pub allocations: u64,
    pub frees: u64,
    pub unknown_frees: u64,
    pub incomplete: bool,
    pub lost_events: u64,
}
impl Lifecycle {
    pub fn apply(&mut self, e: &Event) -> Result<(), String> {
        if e.version != 1
            || e.source.len() > 64
            || !e.timestamp.is_finite()
            || e.started_at
                .is_some_and(|t| !t.is_finite() || t > e.timestamp)
            || e.process.len() > 128
            || e.domain.len() > 64
            || e.stack.as_ref().is_some_and(|s| s.len() > 64)
            || e.operation.as_ref().is_some_and(|s| s.len() > 128)
        {
            return Err("invalid event metadata".into());
        }
        if e.pointer != 0
            && (e.kind == "alloc" || e.kind == "realloc")
            && (self.allocated.checked_add(e.size).is_none() || self.live.len() >= 250_000)
        {
            self.incomplete = true;
            return Err("allocation accounting or live pointer budget exceeded".into());
        }
        if self.last.len() >= 1024
            && !self
                .last
                .contains_key(&(e.process.clone(), e.domain.clone(), e.source.clone()))
        {
            return Err("allocation stream budget exceeded".into());
        }
        let last = self
            .last
            .entry((e.process.clone(), e.domain.clone(), e.source.clone()))
            .or_default();
        if e.sequence <= *last {
            return Err("reordered or duplicate event".into());
        }
        let gap = e.sequence - *last - 1;
        if gap > 0 {
            self.incomplete = true;
            self.lost_events = self.lost_events.saturating_add(gap);
        }
        *last = e.sequence;
        if e.kind == "lost" {
            self.incomplete = true;
            self.lost_events = self.lost_events.saturating_add(e.size.saturating_sub(gap));
            return Ok(());
        }
        if e.kind == "exit" {
            self.live.retain(|(p, _, _), _| p != &e.process);
            return Ok(());
        }
        if e.kind == "fork" {
            return Ok(());
        } // No inherited allocations without an explicit complete fork snapshot.
        let key = (e.process.clone(), e.domain.clone(), e.pointer);
        match e.kind.as_str() {
            "alloc" => {
                if e.pointer != 0 {
                    self.allocate(key, e);
                }
            }
            "free" => {
                if e.pointer != 0 {
                    self.release(&key);
                }
            }
            "realloc" => {
                if e.pointer == 0 {
                    if e.size == 0 {
                        self.incomplete = true;
                    }
                    return Ok(());
                } // Failure retains the old block; realloc(p,0) is implementation dependent.
                if let Some(old) = e.old_pointer.filter(|p| *p != 0) {
                    let old_key = (e.process.clone(), e.domain.clone(), old);
                    if e.started_at.is_some_and(|start| {
                        self.live
                            .get(&old_key)
                            .is_some_and(|allocation| allocation.timestamp > start)
                    }) {
                        // Another thread reused the old address before realloc
                        // returned. Never free that new allocation generation.
                        self.incomplete = true;
                    } else {
                        if old != e.pointer && e.started_at.is_none() {
                            self.incomplete = true;
                        }
                        self.release(&old_key);
                    }
                }
                self.allocate(key, e);
            }
            _ => return Err("unknown event kind".into()),
        }
        Ok(())
    }
    fn release(&mut self, key: &Key) {
        if let Some(a) = self.live.remove(key) {
            self.freed += a.size;
            self.frees += 1;
        } else {
            self.unknown_frees += 1;
        }
    }
    fn allocate(&mut self, key: Key, e: &Event) {
        if self.live.contains_key(&key) {
            self.incomplete = true;
            self.live.remove(&key);
        }
        self.generation += 1;
        let generation = self.generation;
        self.live.insert(
            key,
            Allocation {
                size: e.size,
                generation,
                timestamp: e.timestamp,
                monotonic_ns: e.monotonic_ns,
                stack: e.stack.clone(),
                operation: e.operation.clone(),
                thread: e.thread,
            },
        );
        self.allocated += e.size;
        self.allocations += 1;
    }
    pub fn live_by_domain(&self) -> HashMap<String, u64> {
        let mut out = HashMap::new();
        for ((_, d, _), a) in &self.live {
            *out.entry(d.clone()).or_default() += a.size;
        }
        out
    }
    pub fn cohorts(&self, width: f64) -> HashMap<(String, i64), (u64, u64)> {
        let mut out = HashMap::new();
        if width <= 0.0 {
            return out;
        }
        for ((_, d, _), a) in &self.live {
            let c = out
                .entry((d.clone(), (a.timestamp / width).floor() as i64))
                .or_default();
            c.0 += a.size;
            c.1 += 1;
        }
        out
    }
}
pub fn theil_sen(points: &[(f64, f64)]) -> Option<f64> {
    // Bound quadratic work to 256 evenly spaced points; no synthetic measurements.
    let count = points.len().min(256);
    let p: Vec<_> = (0..count)
        .map(|i| &points[i * points.len().saturating_sub(1) / count.saturating_sub(1).max(1)])
        .filter(|(t, v)| t.is_finite() && v.is_finite())
        .collect();
    let mut slopes = Vec::new();
    for (i, a) in p.iter().enumerate() {
        for b in p.iter().skip(i + 1) {
            if b.0 > a.0 {
                slopes.push((b.1 - a.1) / (b.0 - a.0));
            }
        }
    }
    if slopes.is_empty() {
        return None;
    }
    slopes.sort_by(f64::total_cmp);
    let n = slopes.len();
    Some(if n % 2 == 0 {
        (slopes[n / 2 - 1] + slopes[n / 2]) / 2.0
    } else {
        slopes[n / 2]
    })
}
#[cfg(test)]
mod tests {
    use super::*;
    fn e(n: u64, p: u64, k: &str, s: u64) -> Event {
        Event {
            version: 1,
            source: "unit_test".into(),
            pid: 1,
            monotonic_ns: None,
            started_at: None,
            sequence: n,
            process: "one".into(),
            domain: "native".into(),
            pointer: p,
            kind: k.into(),
            size: s,
            old_pointer: None,
            timestamp: n as f64,
            stack: None,
            operation: None,
            thread: 1,
        }
    }
    #[test]
    fn reuse_failed_realloc_and_domains() {
        let mut l = Lifecycle::default();
        l.apply(&e(1, 2, "alloc", 10)).unwrap();
        let mut r = e(2, 0, "realloc", 20);
        r.old_pointer = Some(2);
        l.apply(&r).unwrap();
        assert_eq!(l.live_by_domain()["native"], 10);
        l.apply(&e(3, 2, "free", 0)).unwrap();
        l.apply(&e(4, 2, "alloc", 30)).unwrap();
        assert_eq!(l.live.values().next().unwrap().generation, 2);
        r = e(5, 3, "realloc", 40);
        r.old_pointer = Some(2);
        l.apply(&r).unwrap();
        assert_eq!(l.live_by_domain()["native"], 40);
        let mut other = e(6, 3, "alloc", 5);
        other.domain = "python_block".into();
        l.apply(&other).unwrap();
        assert_eq!(l.live_by_domain().len(), 2);
    }
    #[test]
    fn lost_and_unknown_free() {
        let mut l = Lifecycle::default();
        l.apply(&e(1, 0, "free", 0)).unwrap();
        l.apply(&e(3, 42, "free", 0)).unwrap();
        assert!(l.incomplete);
        assert_eq!(l.lost_events, 1);
        assert_eq!(l.unknown_frees, 1);
        assert!(l.apply(&e(3, 1, "alloc", 1)).is_err());
    }
    #[test]
    fn resistant_trend() {
        let full: Vec<_> = (0..511)
            .map(|i| (i as f64, (i as f64 - 255.0).max(0.0)))
            .collect();
        let rate = theil_sen(&full).unwrap();
        assert!(rate > 0.2 && rate < 0.8);
        assert_eq!(
            theil_sen(&[(0., 0.), (1., 2.), (2., 999.), (3., 6.), (4., 8.)]),
            Some(2.)
        );
    }
}

#[cfg(test)]
mod edge_cases {
    use super::*;
    fn e(n: u64, kind: &str, pointer: u64, old: u64, size: u64) -> Event {
        Event {
            version: 1,
            source: "unit_test".into(),
            pid: 1,
            monotonic_ns: None,
            started_at: None,
            sequence: n,
            process: "worker".into(),
            domain: "native".into(),
            pointer,
            kind: kind.into(),
            size,
            old_pointer: Some(old),
            timestamp: n as f64,
            stack: None,
            operation: None,
            thread: 1,
        }
    }
    #[test]
    fn realloc_in_place_null_zero_and_failure() {
        let mut l = Lifecycle::default();
        l.apply(&e(1, "realloc", 5, 0, 100)).unwrap();
        l.apply(&e(2, "realloc", 5, 5, 200)).unwrap();
        assert_eq!(l.live_by_domain()["native"], 200);
        assert_eq!((l.allocated, l.freed), (300, 100));
        l.apply(&e(3, "realloc", 0, 5, 4096)).unwrap();
        assert_eq!(l.live_by_domain()["native"], 200);
        assert!(!l.incomplete);
        l.apply(&e(4, "realloc", 0, 5, 0)).unwrap();
        assert!(l.incomplete); // Do not assume glibc behavior for every capture.
    }
    #[test]
    fn initial_loss_explicit_loss_and_pointer_collision() {
        let mut l = Lifecycle::default();
        l.apply(&e(3, "lost", 0, 0, 2)).unwrap();
        assert_eq!(l.lost_events, 2);
        l.apply(&e(4, "alloc", 10, 0, 42)).unwrap();
        l.apply(&e(5, "alloc", 10, 0, 50)).unwrap();
        assert!(l.incomplete);
        assert_eq!(l.live_by_domain()["native"], 50);
    }
    #[test]
    fn worker_exit_and_fork_are_separate() {
        let mut l = Lifecycle::default();
        l.apply(&e(1, "alloc", 1, 0, 40)).unwrap();
        let mut child = e(2, "fork", 0, 0, 0);
        child.process = "child".into();
        l.apply(&child).unwrap();
        assert_eq!(l.live.len(), 1);
        l.apply(&e(3, "exit", 0, 0, 0)).unwrap();
        assert!(l.live.is_empty());
    }
    #[test]
    fn streaming_reuse_has_no_pointer_history_growth() {
        let mut l = Lifecycle::default();
        for i in 0..100_000 {
            l.apply(&e(i * 2 + 1, "alloc", i + 1, 0, 8)).unwrap();
            l.apply(&e(i * 2 + 2, "free", i + 1, 0, 0)).unwrap();
        }
        assert!(l.live.is_empty());
        assert!(!l.incomplete);
    }
}

#[cfg(test)]
mod concurrent_realloc {
    use super::*;
    #[test]
    fn reused_old_pointer_before_realloc_return_is_not_freed() {
        let mut l = Lifecycle::default();
        let base = Event {
            version: 1,
            source: "unit_test".into(),
            pid: 1,
            monotonic_ns: None,
            started_at: None,
            sequence: 1,
            process: "worker".into(),
            domain: "native".into(),
            pointer: 10,
            old_pointer: None,
            kind: "alloc".into(),
            size: 70,
            timestamp: 2.,
            stack: None,
            operation: None,
            thread: 2,
        };
        // Old allocation predates capture. Thread 2 reuses its address after
        // thread 1's realloc entry, but before thread 1's return event arrives.
        l.apply(&base).unwrap();
        let moved = Event {
            sequence: 2,
            pointer: 20,
            old_pointer: Some(10),
            kind: "realloc".into(),
            size: 90,
            timestamp: 3.,
            started_at: Some(1.),
            thread: 1,
            ..base.clone()
        };
        l.apply(&moved).unwrap();
        assert_eq!(l.live_by_domain()["native"], 160);
        assert_eq!(l.live.len(), 2);
        assert!(l.incomplete);
    }
}
