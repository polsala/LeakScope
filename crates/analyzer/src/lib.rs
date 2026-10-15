//! Memory domains never sum: arena backing and object blocks overlap.
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Event {
    pub sequence: u64,
    pub process: String,
    pub domain: String,
    pub pointer: u64,
    pub kind: String,
    pub size: u64,
    pub old_pointer: Option<u64>,
    pub timestamp: f64,
    pub stack: Option<String>,
    pub operation: Option<String>,
    pub thread: u64,
}
#[derive(Debug, Clone, Serialize)]
pub struct Allocation {
    pub size: u64,
    pub generation: u64,
    pub timestamp: f64,
    pub stack: Option<String>,
    pub operation: Option<String>,
    pub thread: u64,
}
type Key = (String, String, u64);
#[derive(Default)]
pub struct Lifecycle {
    pub live: HashMap<Key, Allocation>,
    generations: HashMap<Key, u64>,
    last: u64,
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
        if !e.timestamp.is_finite()
            || e.process.len() > 128
            || e.domain.len() > 64
            || e.stack.as_ref().is_some_and(|s| s.len() > 4096)
            || e.operation.as_ref().is_some_and(|s| s.len() > 128)
        {
            return Err("invalid event metadata".into());
        }
        if e.pointer != 0
            && (e.kind == "alloc" || e.kind == "realloc")
            && (self.allocated.checked_add(e.size).is_none() || self.generations.len() >= 1_000_000)
        {
            self.incomplete = true;
            return Err("allocation accounting or pointer-history budget exceeded".into());
        }
        if e.sequence <= self.last {
            return Err("reordered or duplicate event".into());
        }
        if self.last > 0 && e.sequence != self.last + 1 {
            self.incomplete = true;
            self.lost_events = self.lost_events.saturating_add(e.sequence - self.last - 1);
        }
        self.last = e.sequence;
        if e.kind == "lost" {
            self.incomplete = true;
            self.lost_events = self.lost_events.saturating_add(e.size);
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
                    self.release(&(e.process.clone(), e.domain.clone(), old));
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
        let generation = self.generations.entry(key.clone()).or_default();
        *generation += 1;
        self.live.insert(
            key,
            Allocation {
                size: e.size,
                generation: *generation,
                timestamp: e.timestamp,
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
    let step = (points.len() / 256).max(1);
    let p: Vec<_> = points
        .iter()
        .step_by(step)
        .take(256)
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
        assert_eq!(
            theil_sen(&[(0., 0.), (1., 2.), (2., 999.), (3., 6.), (4., 8.)]),
            Some(2.)
        );
    }
}
