mod controller;
mod native;
use leakscope_common::now;
use leakscope_procfs::{discover, read_process};
use leakscope_protocol::{Envelope, VERSION, read_frame, write_frame};
use native::capabilities;
use serde_json::{Value, json};
use std::os::unix::fs::{MetadataExt, PermissionsExt};
use std::{
    collections::{HashMap, VecDeque},
    fs, io,
    path::PathBuf,
    sync::Arc,
    time::{Duration, Instant},
};
use tokio::{net::UnixListener, sync::Mutex};

struct Lease {
    controller: controller::Controller,
    created: Instant,
    controller_check: Instant,
    previous_cpu: Option<(Instant, u64)>,
    target_cpu: Option<f64>,
    collector_lag_ms: Option<f64>,
    feedback_at: Instant,
    external_latency_increase: Option<f64>,
    pid: u32,
    key: String,
    deadline: Instant,
    interval: f64,
    next: Instant,
    sequence: u64,
    queue: VecDeque<Value>,
    lost: u64,
    stopped: bool,
    reason: String,
    samples: u64,
    bytes: u64,
    max_bytes: u64,
    max_rss: u64,
    trace: Option<native::Trace>,
    native_quality: Value,
    lost_native: u64,
    queue_bytes: usize,
    max_event_rate: u64,
    native_window: Instant,
    native_count: u64,
}
struct State {
    leases: HashMap<String, Lease>,
    uid: u32,
    token: String,
    started: f64,
}
fn err(s: &str) -> Value {
    json!({"error":s})
}
fn clock_ticks() -> Option<u64> {
    // SAFETY: sysconf reads a process-independent scalar; no pointers or ownership.
    let ticks = unsafe { libc::sysconf(libc::_SC_CLK_TCK) };
    (ticks > 0).then_some(ticks as u64)
}
fn kernel_probe_fds() -> usize {
    fs::read_dir("/proc/self/fd")
        .into_iter()
        .flatten()
        .flatten()
        .filter(|e| {
            fs::read_link(e.path()).is_ok_and(|p| {
                let p = p.to_string_lossy();
                p.contains("perf_event")
                    || p.contains("bpf-link")
                    || p.contains("bpf_link")
                    || p.contains("bpf_raw_tracepoint")
            })
        })
        .count()
}
async fn handle(req: Value, state: &Arc<Mutex<State>>) -> Value {
    let action = req["action"].as_str().unwrap_or("");
    let uid = state.lock().await.uid;
    match action {
        "doctor" => {
            json!({"capabilities":capabilities(),"host_id":leakscope_procfs::host_id(),"uid":uid,"kernel":fs::read_to_string("/proc/sys/kernel/osrelease").unwrap_or_default().trim(),"architecture":std::env::consts::ARCH,"clock_ticks_per_second":clock_ticks(),"started":state.lock().await.started})
        }
        "discover" => json!({"processes":discover(uid)}),
        "health" => {
            let own = read_process(std::process::id(), uid, false).ok();
            let s = state.lock().await;
            let utilization = s
                .leases
                .values()
                .map(|l| {
                    let capacity = if l.native_quality["coverage"] == "native_observed" {
                        16384.
                    } else {
                        256.
                    };
                    (l.queue.len() as f64 / capacity)
                        .max(l.queue_bytes as f64 / (4. * 1024. * 1024.))
                })
                .fold(0f64, f64::max);
            json!({"sample":own.map(|p|p.sample),"ringbuffer_utilization":utilization,"ringbuffer_source":"sensor_ack_queue","kernel_ringbuffer_utilization":null,"kernel_probe_fds":kernel_probe_fds(),"native_traces":s.leases.values().filter(|l|l.trace.is_some()).count(),"active_leases":s.leases.values().filter(|l|!l.stopped).count()})
        }
        "sample" => {
            let pid = req["pid"].as_u64().unwrap_or(0) as u32;
            match read_process(pid, uid, req["expensive"].as_bool().unwrap_or(true)) {
                Ok(p) => json!(p),
                Err(e) => err(&e.to_string()),
            }
        }
        "symbols" => {
            let pid = req["pid"].as_u64().unwrap_or(0) as u32;
            match read_process(pid, uid, false) {
                Ok(p) => match leakscope_symbolizer::inspect(std::path::Path::new(&p.executable)) {
                    Ok(v) => json!(v),
                    Err(e) => err(&e.to_string()),
                },
                Err(e) => err(&e.to_string()),
            }
        }
        "native_capabilities" => {
            let pid = req["pid"].as_u64().unwrap_or(0) as u32;
            if let Err(e) = read_process(pid, uid, false) {
                return err(&e.to_string());
            }
            let mut c = capabilities();
            match leakscope_symbolizer::allocator(pid) {
                Ok((path, info)) => {
                    c["provider"] = json!(path);
                    c["symbols"] = json!(info);
                }
                Err(e) => {
                    c["external_allocations"] = json!(false);
                    c["reason"] = json!(e.to_string());
                }
            }
            json!({"capabilities":c})
        }
        "start" => {
            let id = req["session"].as_str().unwrap_or("").to_owned();
            if id.is_empty() || id.len() > 64 {
                return err("invalid session identity");
            }
            let pid = req["pid"].as_u64().unwrap_or(0) as u32;
            let p = match read_process(pid, uid, true) {
                Ok(p) => p,
                Err(e) => return err(&e.to_string()),
            };
            if Some(p.key.as_str()) != req["process_key"].as_str() {
                return err("process identity changed");
            }
            let duration = req["duration"].as_f64().unwrap_or(60.);
            let interval = req["interval"].as_f64().unwrap_or(1.);
            let max_bytes = req["max_bytes"]
                .as_u64()
                .unwrap_or(50 * 1024 * 1024)
                .clamp(1024, 500 * 1024 * 1024);
            if !(1.0..=600.0).contains(&duration) || !(0.1..=60.0).contains(&interval) {
                return err("session budget outside allowed bounds");
            }
            let mut s = state.lock().await;
            if let Some(l) = s.leases.get(&id) {
                return json!({"confirmed":true,"stopped":l.stopped,"session":id});
            }
            if s.leases.values().filter(|l| !l.stopped).count() >= 2 {
                return err("concurrent session limit reached");
            }
            if s.leases.len() >= 128 {
                return err("unacknowledged session budget reached; reconcile finished sessions");
            }
            if req["native"].as_bool().unwrap_or(false)
                && s.leases
                    .values()
                    .any(|l| !l.stopped && l.pid == pid && l.trace.is_some())
            {
                return err("native probes already attached to this process");
            }
            let mut trace = None;
            let budget: controller::Budget = match serde_json::from_value(
                req["overhead_budget"]
                    .as_object()
                    .map(|_| req["overhead_budget"].clone())
                    .unwrap_or(json!({})),
            ) {
                Ok(v) => v,
                Err(_) => return err("invalid overhead budget"),
            };
            if !budget.valid() {
                return err("overhead budget outside allowed bounds");
            }
            let mut native_quality = json!({});
            if req["native"].as_bool().unwrap_or(false) {
                let policy = match native::Policy::parse(&req) {
                    Ok(p) => p,
                    Err(e) => return err(&e.to_string()),
                };
                match native::Trace::start(pid, policy) {
                    Ok(t) => {
                        native_quality = t.quality();
                        trace = Some(t);
                    }
                    Err(e) => {
                        if !req["allow_downgrade"].as_bool().unwrap_or(true) {
                            return err(&format!("native attach failed: {e:?}"));
                        }
                        native_quality = json!({"coverage":"metrics_only","downgraded":true,"native_failure":format!("{e:?}")});
                    }
                }
            }
            if let Ok(current) = read_process(pid, uid, false) {
                if current.key != p.key {
                    return err("target identity changed during probe attachment");
                }
            } else {
                return err("target exited during probe attachment");
            }
            let coverage = native_quality.clone();
            s.leases.insert(
                id.clone(),
                Lease {
                    controller: controller::Controller::new(
                        budget,
                        req["prior_metrics_cpu_percent"].as_f64(),
                    ),
                    created: Instant::now(),
                    controller_check: Instant::now(),
                    previous_cpu: None,
                    target_cpu: None,
                    collector_lag_ms: None,
                    feedback_at: Instant::now(),
                    external_latency_increase: None,
                    trace,
                    native_quality,
                    lost_native: 0,
                    queue_bytes: 0,
                    max_event_rate: req["event_rate_limit"]
                        .as_u64()
                        .unwrap_or(100_000)
                        .clamp(100, 1_000_000),
                    native_window: Instant::now(),
                    native_count: 0,
                    pid,
                    key: p.key,
                    deadline: Instant::now() + Duration::from_secs_f64(duration),
                    interval,
                    next: Instant::now(),
                    sequence: 0,
                    queue: VecDeque::with_capacity(256),
                    lost: 0,
                    stopped: false,
                    reason: String::new(),
                    samples: 0,
                    bytes: 0,
                    max_bytes,
                    max_rss: req["max_sensor_rss_mb"]
                        .as_u64()
                        .unwrap_or(128)
                        .clamp(32, 128)
                        * 1024
                        * 1024,
                },
            );
            if let Some(l) = s.leases.get_mut(&id)
                && let Some(t) = &l.trace
            {
                let window = t.window();
                enqueue(
                    l,
                    json!({"kind":"capture_window","phase":"armed","window":window}),
                );
                let t = l.trace.as_ref().unwrap();
                for m in t.modules() {
                    enqueue(l, m);
                }
            }
            json!({"confirmed":true,"session":id,"mode":"observe","quality":coverage})
        }
        "poll" | "stop" => {
            let id = req["session"].as_str().unwrap_or("");
            let mut s = state.lock().await;
            let Some(l) = s.leases.get_mut(id) else {
                return err("unknown session; sensor may have restarted");
            };
            let ack = req["ack"].as_u64().unwrap_or(0);
            l.feedback_at = Instant::now();
            l.collector_lag_ms = req["collector_lag_ms"]
                .as_f64()
                .filter(|n| n.is_finite() && *n >= 0.);
            l.external_latency_increase = req["external_latency_increase_percent"]
                .as_f64()
                .filter(|n| n.is_finite());
            while l
                .queue
                .front()
                .is_some_and(|v| v["sequence"].as_u64().unwrap_or(0) <= ack)
            {
                if let Some(old) = l.queue.pop_front() {
                    l.queue_bytes = l.queue_bytes.saturating_sub(old.to_string().len());
                }
            }
            if action == "stop" {
                finish_trace(l);
                l.stopped = true;
                l.reason = "requested".into();
            }
            let mut size = 0;
            let events: Vec<_> = l
                .queue
                .iter()
                .take_while(|v| {
                    size += v.to_string().len();
                    size < 600_000
                })
                .collect();
            json!({"events":events,"pending_events":l.queue.len(),"queue_utilization":(l.queue_bytes as f64/(4.*1024.*1024.)).max(l.queue.len() as f64/16384.),"quality":l.native_quality,"lost_native":l.lost_native,"lost_samples":l.lost,"stopped":l.stopped && events.len()==l.queue.len(),"reason":l.reason,"last_sequence":l.sequence,"samples":l.samples})
        }
        "release" => {
            let id = req["session"].as_str().unwrap_or("");
            let mut s = state.lock().await;
            if s.leases.get(id).is_some_and(|l| l.stopped) {
                s.leases.remove(id);
            }
            json!({"released":true})
        }
        _ => err("unsupported sensor action"),
    }
}
#[tokio::main]
async fn main() -> io::Result<()> {
    let args: Vec<_> = std::env::args().collect();
    if args.iter().any(|s| s == "--version") {
        println!("leakscope-sensor 0.1.0");
        return Ok(());
    }
    let uid = fs::metadata("/proc/self")?.uid();
    if args.iter().any(|s| s == "--doctor") {
        println!(
            "{}",
            json!({"capabilities":capabilities(),"processes":discover(uid).len()})
        );
        return Ok(());
    }
    let socket = PathBuf::from(
        std::env::var("LEAKSCOPE_SENSOR_SOCKET").unwrap_or_else(|_| ".data/sensor.sock".into()),
    );
    let token_path = PathBuf::from(
        std::env::var("LEAKSCOPE_SENSOR_TOKEN_FILE")
            .unwrap_or_else(|_| ".data/sensor.token".into()),
    );
    let token = fs::read_to_string(token_path)?.trim().to_owned();
    if token.len() < 32 {
        return Err(io::Error::other("sensor token must have 32+ characters"));
    }
    if let Some(parent) = socket.parent() {
        fs::create_dir_all(parent)?;
        if fs::metadata(parent)?.uid() != uid {
            return Err(io::Error::other(
                "socket directory must be owned by sensor UID",
            ));
        }
        fs::set_permissions(parent, fs::Permissions::from_mode(0o700))?;
    }
    if socket.exists() {
        if tokio::net::UnixStream::connect(&socket).await.is_ok() {
            return Err(io::Error::other("sensor already running"));
        }
        fs::remove_file(&socket)?;
    }
    let listener = UnixListener::bind(&socket)?;
    fs::set_permissions(&socket, fs::Permissions::from_mode(0o600))?;
    let state = Arc::new(Mutex::new(State {
        leases: HashMap::new(),
        uid,
        token,
        started: now(),
    }));
    let sample_state = state.clone();
    let sampler = tokio::spawn(async move {
        let mut timer = tokio::time::interval(Duration::from_millis(50));
        let mut own_check = Instant::now() - Duration::from_secs(2);
        let mut own_cpu: Option<(Instant, u64)> = None;
        let mut sensor_cpu = None;
        let mut sensor_rss = 0;
        loop {
            timer.tick().await;
            let mut s = sample_state.lock().await;
            let uid = s.uid;
            if own_check.elapsed() >= Duration::from_secs(1) {
                own_check = Instant::now();
                if let Ok(p) = read_process(std::process::id(), uid, false) {
                    sensor_rss = p.sample.rss;
                    if let Some((at, ticks)) = own_cpu {
                        sensor_cpu = clock_ticks().map(|hz| {
                            100. * p.sample.cpu_ticks.saturating_sub(ticks) as f64
                                / hz as f64
                                / at.elapsed().as_secs_f64()
                        });
                    }
                    own_cpu = Some((Instant::now(), p.sample.cpu_ticks));
                }
            }
            for l in s.leases.values_mut() {
                if l.stopped {
                    finish_trace(l);
                    continue;
                }
                if let Some(trace) = &mut l.trace {
                    match trace.drain(&l.key) {
                        Ok(events) => {
                            l.native_quality = preserve_quality(&l.native_quality, trace.quality());
                            let executed = events.iter().any(|e| e["event"]["kind"] == "exit");
                            let overloaded = trace.lost.iter().sum::<u64>() > 0;
                            let produced = trace.sequence + trace.lost.iter().sum::<u64>();
                            let elapsed = l.native_window.elapsed().as_secs_f64();
                            let rate_guard = produced.saturating_sub(l.native_count) as f64
                                > l.max_event_rate as f64 * elapsed + 2048.;
                            l.native_count = produced;
                            l.native_window = Instant::now();
                            for e in events {
                                enqueue(l, e);
                            }
                            if executed {
                                finish_trace(l);
                                l.stopped = true;
                                l.reason = "process_executed".into();
                            }
                            if overloaded || rate_guard || l.lost_native > 0 {
                                finish_trace(l);
                                l.native_quality["detailed_tracing_stopped"] =
                                    json!(if overloaded {
                                        "kernel_event_loss_guard"
                                    } else if l.lost_native > 0 {
                                        "collector_backpressure_guard"
                                    } else {
                                        "event_rate_guard"
                                    });
                                l.native_quality["incomplete"] = json!(true);
                                let reason = l.native_quality["detailed_tracing_stopped"]
                                    .as_str()
                                    .unwrap_or("native_guard")
                                    .to_owned();
                                policy_transition(l, "metrics", &reason);
                            }
                        }
                        Err(e) => {
                            finish_trace(l);
                            l.native_quality["native_failure"] = json!(format!("{e:?}"));
                            l.native_quality["unknown_loss"] = json!(true);
                            policy_transition(l, "metrics", &format!("{e:?}"));
                            l.native_quality["incomplete"] = json!(true);
                        }
                    }
                }
                let t = Instant::now();
                if sensor_rss > l.max_rss {
                    finish_trace(l);
                    l.stopped = true;
                    l.reason = "sensor_rss_budget".into();
                    continue;
                }
                if t >= l.deadline {
                    finish_trace(l);
                    l.stopped = true;
                    l.reason = "duration_limit".into();
                    continue;
                }
                let metric_due = t >= l.next;
                let safety_due =
                    l.trace.is_some() && l.controller_check.elapsed() >= Duration::from_secs(1);
                if !metric_due && !safety_due {
                    continue;
                }
                if metric_due {
                    l.next = t + Duration::from_secs_f64(l.interval);
                }
                let p = match read_process(l.pid, uid, metric_due && l.samples % 10 == 0) {
                    Ok(p) if p.key == l.key => p,
                    _ => {
                        finish_trace(l);
                        l.stopped = true;
                        l.reason = "process_exited_or_replaced".into();
                        if l.native_quality["coverage"] == "native_observed" {
                            let sequence =
                                l.native_quality["allocation_events"].as_u64().unwrap_or(0) + 1;
                            let e = leakscope_protocol::AllocationEvent {
                                version: 1,
                                source: "sensor_process_exit".into(),
                                pid: l.pid,
                                monotonic_ns: None,
                                started_at: None,
                                sequence,
                                process: l.key.clone(),
                                domain: "native".into(),
                                pointer: 0,
                                kind: "exit".into(),
                                size: 0,
                                old_pointer: None,
                                timestamp: now(),
                                stack: None,
                                operation: None,
                                thread: 0,
                            };
                            enqueue(l, json!({"kind":"allocation","event":e}));
                        }
                        continue;
                    }
                };
                if let Some((at, ticks)) = l.previous_cpu {
                    l.target_cpu = clock_ticks().map(|hz| {
                        100. * p.sample.cpu_ticks.saturating_sub(ticks) as f64
                            / hz as f64
                            / at.elapsed().as_secs_f64()
                    });
                }
                l.previous_cpu = Some((Instant::now(), p.sample.cpu_ticks));
                if l.trace.is_some() && l.controller_check.elapsed() >= Duration::from_secs(1) {
                    l.controller_check = Instant::now();
                    let feedback_age = l.feedback_at.elapsed().as_secs_f64();
                    let telemetry = controller::Telemetry {
                        target_cpu_percent: l.target_cpu,
                        sensor_cpu_percent: sensor_cpu,
                        collector_lag_ms: if feedback_age > 2. {
                            Some(feedback_age * 1000.)
                        } else {
                            l.collector_lag_ms
                        },
                        queue_utilization: (l.queue_bytes as f64 / (4. * 1024. * 1024.))
                            .max(l.queue.len() as f64 / 16384.),
                        kernel_lost: l.native_quality["lost_events"].as_u64().unwrap_or(0),
                        collector_lost: l.lost_native,
                        external_latency_increase_percent: l.external_latency_increase,
                    };
                    let action = l
                        .controller
                        .evaluate(l.created.elapsed().as_secs_f64(), &telemetry);
                    l.native_quality["controller"] = l.controller.snapshot.clone();
                    match action {
                        controller::Action::None => {}
                        controller::Action::ReduceStacks(reason) => {
                            let reduced = l
                                .trace
                                .as_mut()
                                .and_then(|trace| trace.reduce_stacks().ok().flatten());
                            if let Some(policy) = reduced {
                                policy_transition(l, policy, reason);
                            } else {
                                finish_trace(l);
                                policy_transition(l, "metrics", reason);
                            }
                        }
                        controller::Action::Detach(reason) => {
                            finish_trace(l);
                            l.native_quality["detailed_tracing_stopped"] = json!(reason);
                            policy_transition(l, "metrics", reason);
                        }
                    }
                }
                if metric_due {
                    let event = json!({"process_key":l.key,"kind":"metric","sample":p.sample});
                    l.samples += 1;
                    enqueue(l, event);
                }
            }
        }
    });
    eprintln!(
        "{}",
        json!({"level":"info","event":"sensor_ready","socket":socket})
    );
    let mut terminate = tokio::signal::unix::signal(tokio::signal::unix::SignalKind::terminate())?;
    let permits = Arc::new(tokio::sync::Semaphore::new(16));
    loop {
        tokio::select! {
            _=tokio::signal::ctrl_c()=>break,
            _=terminate.recv()=>break,
            result=listener.accept()=>{let (mut conn,_)=result?;if conn.peer_cred()?.uid()!=uid{continue}
                let Ok(permit)=permits.clone().try_acquire_owned()else{continue};let state=state.clone();tokio::spawn(async move{let _permit=permit;
                    let result=tokio::time::timeout(Duration::from_secs(5),read_frame(&mut conn)).await;
                    if let Ok(Ok(msg))=result{
                        let valid=msg.token==state.lock().await.token;if !valid{return}
                        let payload=match serde_json::from_slice(&msg.payload){Ok(r)=>handle(r,&state).await,Err(_)=>err("invalid request")};
                        let _=write_frame(&mut conn,Envelope{version:VERSION,token:String::new(),sequence:msg.sequence,payload:serde_json::to_vec(&payload).unwrap_or_default()}).await;
                    }
                });
            }
        }
    }
    sampler.abort();
    for l in state.lock().await.leases.values_mut() {
        finish_trace(l);
    }
    fs::remove_file(socket)?;
    Ok(())
}

// The unacknowledged queue is bounded in bytes and records. Drop oldest records;
// report allocation losses separately from metric losses. Never block the target.
fn enqueue(l: &mut Lease, mut event: Value) {
    let size = event.to_string().len() as u64;
    if size > 256 * 1024 {
        l.lost_native += 1;
        return;
    }
    if l.bytes + size > l.max_bytes {
        l.stopped = true;
        l.reason = "capture_size_limit".into();
        l.lost_native += u64::from(event["kind"] != "metric");
        return;
    }
    l.bytes += size;
    l.sequence += 1;
    event["sequence"] = json!(l.sequence);
    while l.queue.len()
        >= if l.native_quality["coverage"] == "native_observed" {
            16384
        } else {
            256
        }
        || l.queue_bytes + size as usize > 4 * 1024 * 1024
    {
        if let Some(old) = l.queue.pop_front() {
            l.queue_bytes = l.queue_bytes.saturating_sub(old.to_string().len());
            if old["kind"] == "metric" {
                l.lost += 1;
            } else {
                l.lost_native += 1;
            }
        } else {
            break;
        }
    }
    l.queue_bytes += event.to_string().len();
    l.queue.push_back(event);
}
fn finish_trace(l: &mut Lease) {
    if let Some(mut trace) = l.trace.take() {
        let detach_clock = Instant::now();
        trace.stop();
        // Bounded final drain. Further/in-flight events invalidate completeness.
        for _ in 0..16 {
            match trace.drain(&l.key) {
                Ok(events) => {
                    let empty = events.is_empty();
                    for e in events {
                        enqueue(l, e);
                    }
                    if empty {
                        break;
                    }
                }
                Err(_) => {
                    l.lost_native += 1;
                    break;
                }
            }
        }
        l.native_quality = preserve_quality(&l.native_quality, trace.quality());
        l.native_quality["attach_boundary"] =
            json!("Calls already in progress at attach/detach are not covered");
        drop(trace); // Actual link FD closure, not merely a BPF inactive flag.
        l.native_quality["capture_window"]["detached_at"] = json!(now());
        l.native_quality["capture_window"]["detach_seconds"] =
            json!(detach_clock.elapsed().as_secs_f64());
        l.native_quality["capture_window"]["physically_detached"] = json!(true);
        let window = l.native_quality["capture_window"].clone();
        enqueue(
            l,
            json!({"kind":"capture_window","phase":"detached","window":window}),
        );
    }
}
fn preserve_quality(old: &Value, mut new: Value) -> Value {
    for key in [
        "controller",
        "policy_transitions",
        "policy_transitions_lost",
        "effective_policy",
    ] {
        if !old[key].is_null() {
            new[key] = old[key].clone();
        }
    }
    if old["policy_transitions_lost"].as_u64().unwrap_or(0) > 0 {
        new["incomplete"] = json!(true);
    }
    new
}
fn policy_transition(l: &mut Lease, to: &str, reason: &str) {
    append_policy_transition(&mut l.native_quality, to, reason);
    if to == "metrics" {
        l.native_quality["coverage_gap_after_native"] = json!(true);
        l.native_quality["incomplete"] = json!(true);
        let window = l.native_quality["capture_window"].clone();
        enqueue(
            l,
            json!({"kind":"capture_window","phase":"gap","window":window}),
        );
    }
    enqueue(
        l,
        json!({"kind":"policy_transition","timestamp":now(),"to":to,"reason":reason}),
    );
}
fn append_policy_transition(quality: &mut Value, to: &str, reason: &str) {
    let from = quality
        .get("effective_policy")
        .filter(|p| p.is_string())
        .unwrap_or(&quality["profiling_policy"])
        .clone();
    let mut transitions = quality["policy_transitions"]
        .as_array()
        .cloned()
        .unwrap_or_default();
    if transitions.len() < 16 {
        transitions.push(json!({"from":from,"to":to,"timestamp":now(),"reason":reason}));
    } else {
        quality["policy_transitions_lost"] =
            json!(quality["policy_transitions_lost"].as_u64().unwrap_or(0) + 1);
        quality["incomplete"] = json!(true);
    }
    quality["policy_transitions"] = json!(transitions);
    quality["effective_policy"] = json!(to);
}
#[cfg(test)]
mod transition_tests {
    use super::*;
    #[test]
    fn hard_guard_preserves_prior_reduction_and_actual_from_policy() {
        let mut q =
            json!({"profiling_policy":"native_detailed","effective_policy":"native_detailed"});
        append_policy_transition(&mut q, "native_stacks_caller", "collector_lag_target");
        append_policy_transition(&mut q, "metrics", "kernel_event_loss_guard");
        assert_eq!(q["policy_transitions"].as_array().unwrap().len(), 2);
        assert_eq!(q["policy_transitions"][0]["reason"], "collector_lag_target");
        assert_eq!(q["policy_transitions"][1]["from"], "native_stacks_caller");
        for _ in 0..20 {
            append_policy_transition(&mut q, "metrics", "test");
        }
        assert_eq!(q["policy_transitions"].as_array().unwrap().len(), 16);
        assert_eq!(q["policy_transitions_lost"], 6);
        assert_eq!(q["incomplete"], true);
        let refreshed = preserve_quality(&q, json!({"incomplete":false}));
        assert_eq!(refreshed["policy_transitions_lost"], 6);
        assert_eq!(refreshed["incomplete"], true);
    }
}
