//! Aya owns every map/program/link. Dropping a Trace detaches all probes, including
//! on partial attach failure. No target code, allocator replacement or injection.
use aya::{
    Ebpf, EbpfLoader,
    maps::{Array, MapData, PerCpuArray, RingBuf, StackTraceMap},
    programs::{
        RawTracePoint, UProbe,
        uprobe::{UProbeAttachLocation, UProbeScope},
    },
};
use leakscope_protocol::{AllocationEvent, NativeRecord};
use leakscope_symbolizer::{Resolver, allocator, target_path};
use serde_json::{Value, json};
use std::os::unix::fs::MetadataExt;
use std::{
    collections::HashSet,
    num::NonZeroU32,
    sync::OnceLock,
    time::{Duration, Instant},
};
const OBJECT: &[u8] = aya::include_bytes_aligned!(concat!(env!("OUT_DIR"), "/allocations.bpf.o"));
type Result<T> = std::result::Result<T, Box<dyn std::error::Error + Send + Sync>>;
pub fn capabilities() -> Value {
    static VALUE: OnceLock<Value> = OnceLock::new();
    VALUE.get_or_init(||{
        let mut base=leakscope_procfs::capabilities();
        let result=(||->Result<()> {let mut b=Ebpf::load(OBJECT)?;let p:&mut UProbe=b.program_mut("malloc_enter").ok_or("missing program")?.try_into()?;p.load()?;Ok(())})();
        let available=result.is_ok();
        let reason=result.err().map(|e|format!("{e:?}")).unwrap_or_else(||"BPF program load verified; per-process attachment is checked when starting a session".into());
        base["external_allocations"]=json!(available);
        base["native_loader"]=json!("aya/0.14.0");base["reason"]=json!(reason);
        base["remediation"]=json!("Use a dedicated same-UID sensor with CAP_BPF and CAP_PERFMON (or an isolated trusted kernel runner). Kernel >=5.8, x86_64, uprobes and BPF ring buffers required. Do not disable kernel security controls. Metrics remain available.");
        base
    }).clone()
}
#[derive(Clone)]
pub struct Policy {
    pub name: String,
    pub minimum: u64,
    pub stacks: u64,
    pub diagnostic: String,
}
impl Policy {
    pub fn parse(request: &Value) -> Result<Self> {
        let name = request["profiling_policy"]
            .as_str()
            .unwrap_or("native_detailed");
        if !["native_light", "native_detailed", "python_deep"].contains(&name) {
            return Err("unsupported native profiling policy".into());
        }
        let minimum = if name == "native_light" {
            request["min_allocation_size"].as_u64().unwrap_or(65536)
        } else {
            0
        };
        if name == "native_light" && !(1..=1073741824).contains(&minimum) {
            return Err("Native Light threshold must be 1..1073741824 bytes".into());
        }
        let stacks = match request["native_stacks"].as_str().unwrap_or("full") {
            "none" => 0,
            "caller" => 1,
            "full" => 2,
            _ => return Err("unsupported stack collection policy".into()),
        };
        let diagnostic = std::env::var("LEAKSCOPE_BENCH_COMPONENT").unwrap_or_default();
        if !["", "entry", "paired", "maps", "stack", "ring"].contains(&diagnostic.as_str()) {
            return Err("unknown benchmark component".into());
        }
        Ok(Self {
            name: name.into(),
            minimum,
            stacks,
            diagnostic,
        })
    }
}
fn clock_offset_zero(text: &str) -> Result<bool> {
    if text.len() > 4096 {
        return Err("time namespace metadata exceeds budget".into());
    }
    for line in text.lines() {
        let mut parts = line.split_whitespace();
        if parts.next() == Some("monotonic") {
            let sec = parts
                .next()
                .ok_or("missing clock offset seconds")?
                .parse::<i64>()?;
            let ns = parts
                .next()
                .ok_or("missing clock offset nanoseconds")?
                .parse::<i64>()?;
            return Ok(sec == 0 && ns == 0);
        }
    }
    Err("monotonic time namespace offset unavailable".into())
}
fn monotonic_ns() -> Result<u64> {
    let mut clock = libc::timespec {
        tv_sec: 0,
        tv_nsec: 0,
    };
    // SAFETY: clock is initialized writable storage, owned for this call.
    // CLOCK_MONOTONIC reads no Python state and changes no resource ownership.
    if unsafe { libc::clock_gettime(libc::CLOCK_MONOTONIC, &mut clock) } != 0 {
        return Err(std::io::Error::last_os_error().into());
    }
    Ok(clock.tv_sec as u64 * 1_000_000_000 + clock.tv_nsec as u64)
}
pub struct Trace {
    _bpf: Ebpf,
    ring: RingBuf<MapData>,
    pending: aya::maps::HashMap<MapData, u64, [u64; 8]>,
    stop_ns: Option<u64>,
    in_flight: u64,
    after_disarm: u64,
    uncertain_stop: bool,
    stacks: StackTraceMap<MapData>,
    losses: PerCpuArray<MapData, u64>,
    control: Array<MapData, u64>,
    resolver: Resolver,
    seen: HashSet<(u32, u64)>,
    pub sequence: u64,
    pub lost: [u64; 3],
    pub stack_errors: u64,
    pub warnings: Vec<String>,
    clock_offset: f64,
    mapping_check: Instant,
    pub symbolization_invalidated: bool,
    process_executed: bool,
    policy: Policy,
}
impl Trace {
    pub fn start(pid: u32, policy: Policy) -> Result<Self> {
        match std::fs::read_to_string("/proc/self/timens_offsets") {
            Ok(text) if !clock_offset_zero(&text)? => return Err("Native tracing in an offset time namespace is unsupported; keep metrics or run the sensor in the host monotonic clock domain".into()),
            Err(e) if e.kind()!=std::io::ErrorKind::NotFound => return Err(e.into()),
            _ => {}
        }
        let (path, elf) = allocator(pid)?;
        let resolver = Resolver::new(pid)?;
        let ring_bytes = std::env::var("LEAKSCOPE_BPF_RING_BYTES")
            .unwrap_or_else(|_| "1048576".into())
            .parse::<u32>()?;
        if !(4096..=8 * 1024 * 1024).contains(&ring_bytes) || !ring_bytes.is_power_of_two() {
            return Err("BPF ring size must be a power of two between 4096 and 8388608".into());
        }
        let mut bpf = EbpfLoader::new()
            .map_max_entries("events", ring_bytes)
            .load(OBJECT)?;
        let mut control = Array::try_from(bpf.take_map("config").ok_or("missing config")?)?;
        control.set(0, u64::from(pid), 0)?;
        // Discovered PIDs are relative to this procfs view, NOT necessarily to
        // the target's innermost namespace. Child namespaces still have an ID
        // in the sensor namespace. A foreign procfs mount is explicitly rejected.
        let status = std::fs::read_to_string("/proc/self/status")?;
        if status
            .lines()
            .find_map(|l| l.strip_prefix("NSpid:"))
            .is_some_and(|l| l.split_whitespace().count() > 1)
        {
            return Err("Foreign procfs PID namespace view is unsupported; run the sensor in the namespace owning this procfs mount".into());
        }
        let namespace = std::fs::metadata("/proc/self/ns/pid")?;
        control.set(2, namespace.dev(), 0)?;
        control.set(3, namespace.ino(), 0)?;
        control.set(4, policy.minimum, 0)?;
        control.set(
            5,
            if ["maps", "ring"].contains(&policy.diagnostic.as_str()) {
                0
            } else {
                policy.stacks
            },
            0,
        )?;
        control.set(
            6,
            u64::from(["maps", "stack"].contains(&policy.diagnostic.as_str())),
            0,
        )?;
        let warnings=vec!["Native-only frame-pointer stacks; Python frames and lines are not inferred. Only the selected provider's outermost allocator calls are covered; custom/interposed allocators can be missed.".into()];
        let mut loaded = HashSet::new();
        for (symbol, program) in [
            ("malloc", "malloc_enter"),
            ("malloc", "malloc_leave"),
            ("calloc", "calloc_enter"),
            ("calloc", "calloc_leave"),
            ("realloc", "realloc_enter"),
            ("realloc", "realloc_leave"),
            ("free", "free_enter"),
        ] {
            let offset = elf
                .symbols
                .iter()
                .find(|s| s.name == symbol)
                .and_then(|s| s.file_offset)
                .ok_or("missing symbol file offset")?;
            if policy.diagnostic == "entry" && program.ends_with("leave") {
                continue;
            }
            let program = if policy.diagnostic == "entry" || policy.diagnostic == "paired" {
                if program.ends_with("leave") {
                    "benchmark_return"
                } else {
                    "benchmark_entry"
                }
            } else {
                program
            };
            let p: &mut UProbe = bpf
                .program_mut(program)
                .ok_or("missing allocator program")?
                .try_into()?;
            if loaded.insert(program) {
                p.load()?;
            }
            p.attach(
                UProbeAttachLocation::AbsoluteOffset(offset),
                target_path(pid, &path),
                UProbeScope::OneProcess(NonZeroU32::new(pid).ok_or("invalid PID")?),
            )?;
        }
        for (program, name) in [
            ("thread_exit", "sched_process_exit"),
            ("process_exec", "sched_process_exec"),
        ] {
            let p: &mut RawTracePoint = bpf
                .program_mut(program)
                .ok_or("missing lifecycle program")?
                .try_into()?;
            p.load()?;
            p.attach(name)?;
        }
        let pending =
            aya::maps::HashMap::try_from(bpf.take_map("calls").ok_or("missing pending map")?)?;
        let ring = RingBuf::try_from(bpf.take_map("events").ok_or("missing ring")?)?;
        let stacks = StackTraceMap::try_from(bpf.take_map("stacks").ok_or("missing stacks")?)?;
        let losses = PerCpuArray::try_from(bpf.take_map("losses").ok_or("missing losses")?)?;
        control.set(1, 1, 0)?; // Attach barrier: never emit half-attached allocator pairs.
        let monotonic = monotonic_ns()? as f64 / 1e9;
        Ok(Self {
            _bpf: bpf,
            ring,
            pending,
            stop_ns: None,
            in_flight: 0,
            after_disarm: 0,
            uncertain_stop: false,
            stacks,
            losses,
            control,
            resolver,
            seen: HashSet::new(),
            sequence: 0,
            lost: [0; 3],
            stack_errors: 0,
            warnings,
            clock_offset: leakscope_common::now() - monotonic,
            mapping_check: Instant::now(),
            symbolization_invalidated: false,
            process_executed: false,
            policy,
        })
    }
    pub fn modules(&self) -> Vec<Value> {
        self.resolver
            .mappings
            .chunks(32)
            .map(|m| json!({"kind":"modules","mappings":m,"attribution":"native_only"}))
            .collect()
    }
    pub fn stop(&mut self) {
        self.stop_ns = monotonic_ns().ok();
        self.uncertain_stop |= self.stop_ns.is_none();
        if self.control.set(1, 0, 0).is_err() {
            self.warnings
                .push("Probe disarm failed; detach will close all links".into());
            self.uncertain_stop = true;
        }
        for key in self.pending.keys() {
            match key {
                Ok(_) => self.in_flight += 1,
                Err(_) => self.uncertain_stop = true,
            }
        }
    }
    pub fn drain(&mut self, process: &str) -> Result<Vec<Value>> {
        let mut result = Vec::new();
        for _ in 0..2048 {
            let Some(item) = self.ring.next() else { break };
            let record = NativeRecord::decode(&item)?;
            self.process_executed |= record.kind == 4;
            if self.stop_ns.is_some_and(|stop| record.time >= stop) {
                self.after_disarm += 1;
            }
            drop(item);
            let stack = if record.stack < 0 && record.caller > 0 {
                if self.policy.stacks == 2 {
                    self.stack_errors += 1;
                }
                let id = format!("caller-{:x}", record.caller);
                if self.seen.len() < 8192 && self.seen.insert((u32::MAX, record.caller)) {
                    result.push(json!({"kind":"stack","id":id,"frames":[self.resolver.frame(record.caller-1)],"quality":"native_caller_only"}));
                }
                Some(id)
            } else if record.stack >= 0 && self.seen.len() < 8192 {
                let id = record.stack as u32;
                if self.seen.insert((id, record.caller)) {
                    match self.stacks.get(&id, 0) {
                        Ok(s) => {
                            let mut frames: Vec<_> = s
                                .frames()
                                .iter()
                                .take(32)
                                .map(|f| self.resolver.frame(f.ip))
                                .collect();
                            if record.caller > 0 {
                                frames.insert(
                                    frames.len().min(1),
                                    self.resolver.frame(record.caller - 1),
                                );
                                frames.truncate(32);
                            }
                            result.push(json!({"kind":"stack","id":format!("{id}-{:x}",record.caller),"frames":frames,"quality":"native_frame_pointer"}));
                        }
                        Err(_) => self.stack_errors += 1,
                    }
                }
                Some(format!("{id}-{:x}", record.caller))
            } else {
                if record.kind != 2 && self.policy.stacks == 2 {
                    self.stack_errors += 1;
                }
                None
            };
            self.sequence += 1;
            let event = AllocationEvent {
                version: 1,
                source: "linux_uprobe".into(),
                pid: (record.thread >> 32) as u32,
                monotonic_ns: Some(record.time),
                started_at: (record.started != 0)
                    .then_some(self.clock_offset + record.started as f64 / 1e9),
                sequence: self.sequence,
                process: process.into(),
                domain: "native".into(),
                pointer: record.pointer,
                kind: match record.kind {
                    1 => "alloc",
                    2 => "free",
                    3 => "realloc",
                    _ => "exit",
                }
                .into(),
                size: record.size,
                old_pointer: Some(record.old_pointer),
                timestamp: self.clock_offset + record.time as f64 / 1e9,
                stack,
                operation: None,
                thread: record.thread as u32 as u64,
            };
            result.push(json!({"kind":"allocation","event":event}));
        }
        if !self.process_executed && self.mapping_check.elapsed() >= Duration::from_secs(1) {
            self.mapping_check = Instant::now();
            if let Ok(current) = leakscope_symbolizer::mappings(self.resolver.pid()) {
                self.symbolization_invalidated |= current.len() != self.resolver.mappings.len()
                    || current.iter().zip(&self.resolver.mappings).any(|(a, b)| {
                        (a.start, a.end, a.offset, &a.path, a.inode)
                            != (b.start, b.end, b.offset, &b.path, b.inode)
                    });
            }
        }
        if self.symbolization_invalidated {
            return Err("Executable mappings changed; native tracing stopped and native symbols invalidated. Start a new session after libraries stabilize".into());
        }
        for i in 0..3 {
            self.lost[i] = self.losses.get(&(i as u32), 0)?.iter().copied().sum();
        }
        Ok(result)
    }
    pub fn quality(&self) -> Value {
        json!({"coverage":"native_observed","symbolization_invalidated":self.symbolization_invalidated,"mapping_history":"attach_snapshot_with_one_second_invalidation; transient_remaps_unverified","lost_allocations":self.lost[0],"lost_frees":self.lost[1],"lost_correlations":self.lost[2],"lost_events":self.lost.iter().sum::<u64>(),"allocation_events":self.sequence,"stack_errors":self.stack_errors,"stack_quality":"native_only_frame_pointer","warnings":self.warnings,"profiling_policy":self.policy.name,"minimum_allocation_size":self.policy.minimum,
        "tracked_pointer_capacity":32768,"pointer_evictions":0,
        "sampling":if self.policy.minimum>0 {"threshold_selected_lifetimes"} else {"all_outermost_calls"},
        "selection_semantics":"Selected at allocation or threshold-crossing realloc; selected blocks remain tracked through shrink, realloc and free. Pre-attach and smaller unselected blocks are outside coverage.",
        "in_flight_calls_at_stop":self.in_flight,"events_after_disarm":self.after_disarm,"stop_boundary_uncertain":self.uncertain_stop,"stack_collection":self.policy.stacks,"diagnostic_component":self.policy.diagnostic,"pre_attach_allocations":"unknown","exact_allocations":self.lost==[0;3]&&self.policy.diagnostic.is_empty()&&!self.symbolization_invalidated&&self.in_flight==0&&self.after_disarm==0&&!self.uncertain_stop,"incomplete":self.lost!=[0;3]||!self.policy.diagnostic.is_empty()||self.symbolization_invalidated||self.in_flight>0||self.after_disarm>0||self.uncertain_stop})
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn clock_namespace_offsets_are_not_assumed_compatible() {
        assert!(clock_offset_zero("monotonic 0 0\nboottime 0 0").unwrap());
        assert!(!clock_offset_zero("monotonic -5 0").unwrap());
        assert!(clock_offset_zero("monotonic invalid").is_err());
    }
    #[test]
    fn light_threshold_and_stack_policy_are_explicit() {
        let p=Policy::parse(&json!({"profiling_policy":"native_light","min_allocation_size":4096,"native_stacks":"caller"})).unwrap();
        assert_eq!(p.minimum, 4096);
        assert_eq!(p.stacks, 1);
        assert!(
            Policy::parse(&json!({"profiling_policy":"native_light","min_allocation_size":0}))
                .is_err()
        );
        assert!(Policy::parse(&json!({"native_stacks":"invented"})).is_err());
        assert_eq!(
            Policy::parse(
                &json!({"profiling_policy":"native_detailed","min_allocation_size":4096})
            )
            .unwrap()
            .minimum,
            0
        );
    }
}
