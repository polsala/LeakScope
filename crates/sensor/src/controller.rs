//! Safety decisions use measured usage, not a counterfactual CPU-overhead claim.
//! State moves only toward less work during a lease. Rearming requires a new
//! separately authorized session after the backend cooldown.
use serde::Deserialize;
use serde_json::{Value, json};

#[derive(Clone, Debug, Deserialize)]
#[serde(default)]
pub struct Budget {
    pub target_cpu_increase_percent: f64,
    pub maximum_sensor_cpu_percent: f64,
    pub maximum_collector_lag_ms: f64,
    pub minimum_observation_seconds: f64,
    pub consecutive_violations: u32,
    pub maximum_target_latency_increase_percent: f64,
}
impl Default for Budget {
    fn default() -> Self {
        Self {
            target_cpu_increase_percent: 5.,
            maximum_sensor_cpu_percent: 50.,
            maximum_collector_lag_ms: 500.,
            minimum_observation_seconds: 10.,
            consecutive_violations: 2,
            maximum_target_latency_increase_percent: 20.,
        }
    }
}
impl Budget {
    pub fn valid(&self) -> bool {
        [
            self.target_cpu_increase_percent,
            self.maximum_sensor_cpu_percent,
            self.maximum_collector_lag_ms,
            self.minimum_observation_seconds,
            self.maximum_target_latency_increase_percent,
        ]
        .iter()
        .all(|x| x.is_finite() && *x > 0.)
            && (1..=10).contains(&self.consecutive_violations)
            && self.minimum_observation_seconds <= 600.
    }
}
#[derive(Default)]
pub struct Telemetry {
    pub target_cpu_percent: Option<f64>,
    pub sensor_cpu_percent: Option<f64>,
    pub collector_lag_ms: Option<f64>,
    pub queue_utilization: f64,
    pub kernel_lost: u64,
    pub collector_lost: u64,
    pub external_latency_increase_percent: Option<f64>,
}
#[derive(Debug, PartialEq)]
pub enum Action {
    None,
    ReduceStacks(&'static str),
    Detach(&'static str),
}
pub struct Controller {
    pub budget: Budget,
    pub baseline: Option<f64>,
    violations: u32,
    reduced: bool,
    detached: bool,
    pub snapshot: Value,
}
impl Controller {
    pub fn new(budget: Budget, baseline: Option<f64>) -> Self {
        Self {
            budget,
            baseline: baseline.filter(|n| n.is_finite() && *n >= 0.),
            violations: 0,
            reduced: false,
            detached: false,
            snapshot: json!({}),
        }
    }
    pub fn evaluate(&mut self, elapsed: f64, t: &Telemetry) -> Action {
        let change = self
            .baseline
            .zip(t.target_cpu_percent)
            .map(|(base, current)| current - base);
        let relative = self
            .baseline
            .filter(|b| *b >= 1.)
            .zip(t.target_cpu_percent)
            .map(|(b, c)| 100. * (c / b - 1.));
        self.snapshot = json!({"target_cpu_percent":t.target_cpu_percent,"sensor_cpu_percent":t.sensor_cpu_percent,"prior_metrics_cpu_percent":self.baseline,"target_usage_change_percentage_points":change,"target_usage_change_percent":relative,"collector_lag_ms":t.collector_lag_ms,"ack_queue_utilization":t.queue_utilization,"kernel_ringbuffer_utilization":null,"kernel_utilization_status":"unavailable; ring loss is measured","agent_buffer_utilization":null,"agent_utilization_status":"unavailable unless reported cooperatively","baseline_kind":"prior_observation_not_counterfactual; workload changes can explain CPU differences","elapsed_seconds":elapsed,"state":if self.detached{"detached"}else if self.reduced{"optional_work_reduced"}else{"observing"}});
        if self.detached {
            return Action::None;
        }
        let hard = if t.kernel_lost > 0 {
            Some("kernel_event_loss")
        } else if t.collector_lost > 0 {
            Some("collector_event_loss")
        } else if t.queue_utilization >= 0.95 {
            Some("collector_queue_pressure")
        } else {
            None
        };
        if let Some(reason) = hard {
            self.detached = true;
            self.snapshot["state"] = json!("detached");
            self.snapshot["last_reason"] = json!(reason);
            return Action::Detach(reason);
        }
        if elapsed < self.budget.minimum_observation_seconds {
            return Action::None;
        }
        let violation = if t
            .collector_lag_ms
            .is_some_and(|n| n > self.budget.maximum_collector_lag_ms)
        {
            Some("collector_lag_target")
        } else if t
            .sensor_cpu_percent
            .is_some_and(|n| n > self.budget.maximum_sensor_cpu_percent)
        {
            Some("sensor_cpu_target")
        } else if relative.is_some_and(|n| n > self.budget.target_cpu_increase_percent)
            && change.is_some_and(|n| n > 1.)
        {
            Some("target_cpu_usage_change; causal_overhead_unknown")
        } else if t
            .external_latency_increase_percent
            .is_some_and(|n| n > self.budget.maximum_target_latency_increase_percent)
        {
            Some("externally_supplied_latency_target")
        } else {
            None
        };
        if let Some(reason) = violation {
            self.violations += 1;
            if self.violations >= self.budget.consecutive_violations {
                self.violations = 0;
                if !self.reduced {
                    self.reduced = true;
                    self.snapshot["state"] = json!("optional_work_reduced");
                    self.snapshot["last_reason"] = json!(reason);
                    return Action::ReduceStacks(reason);
                }
                self.detached = true;
                self.snapshot["state"] = json!("detached");
                self.snapshot["last_reason"] = json!(reason);
                return Action::Detach(reason);
            }
        } else {
            self.violations = self.violations.saturating_sub(1); // hysteresis
        }
        Action::None
    }
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn baseline_unknown_and_hysteresis_never_claim_causal_overhead() {
        let mut c = Controller::new(Budget::default(), None);
        assert_eq!(
            c.evaluate(
                30.,
                &Telemetry {
                    target_cpu_percent: Some(900.),
                    ..Default::default()
                }
            ),
            Action::None
        );
        let high = Telemetry {
            collector_lag_ms: Some(2000.),
            ..Default::default()
        };
        assert_eq!(c.evaluate(1., &high), Action::None);
        assert_eq!(c.evaluate(20., &high), Action::None);
        assert!(matches!(c.evaluate(21., &high), Action::ReduceStacks(_)));
        assert_eq!(c.evaluate(22., &Telemetry::default()), Action::None);
        assert_eq!(c.evaluate(23., &high), Action::None);
        assert!(matches!(c.evaluate(24., &high), Action::Detach(_)));
        assert_eq!(c.evaluate(100., &high), Action::None);
    }
    #[test]
    fn loss_detaches_immediately_and_cpu_uses_explicit_prior_observation() {
        let mut c = Controller::new(Budget::default(), Some(10.));
        let high = Telemetry {
            target_cpu_percent: Some(80.),
            ..Default::default()
        };
        c.evaluate(20., &high);
        assert!(matches!(c.evaluate(21., &high), Action::ReduceStacks(_)));
        assert_eq!(
            c.evaluate(
                22.,
                &Telemetry {
                    kernel_lost: 1,
                    ..Default::default()
                }
            ),
            Action::Detach("kernel_event_loss")
        );
        assert!(
            c.snapshot["baseline_kind"]
                .as_str()
                .unwrap()
                .contains("not_counterfactual")
        );
    }
}
