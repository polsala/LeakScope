//! Streaming native analysis. Raw events stay in LSCAP; RAM is bounded by live
//! pointers (250k), stack tables (8192) and tree nodes (32768), not event history.
mod context;
use leakscope_analyzer::{Event, Lifecycle};
use serde::Serialize;
use serde_json::{Value, json};
use std::{
    collections::{BTreeMap, HashMap},
    fs::File,
    io::{self, BufRead, Read},
};
#[derive(Default, Serialize)]
struct Node {
    name: String,
    value: u64,
    count: u64,
    children: BTreeMap<String, Node>,
}
impl Node {
    fn add(&mut self, frames: &[String], size: u64, budget: &mut usize) {
        self.value = self.value.saturating_add(size);
        self.count += 1;
        if let Some((head, tail)) = frames.split_first() {
            if !self.children.contains_key(head) {
                if *budget == 0 {
                    return;
                }
                *budget -= 1;
            }
            self.children
                .entry(head.clone())
                .or_insert_with(|| Node {
                    name: head.clone(),
                    ..Default::default()
                })
                .add(tail, size, budget);
        }
    }
}
fn context_records(
    path: &str,
    mut visit: impl FnMut(Value) -> Result<(), Box<dyn std::error::Error>>,
) -> Result<(), Box<dyn std::error::Error>> {
    let file = File::open(path)?;
    if file.metadata()?.len() > 64 * 1024 * 1024 {
        return Err("live context exceeds 64 MiB".into());
    }
    let mut reader = io::BufReader::new(file);
    let mut line = String::new();
    loop {
        line.clear();
        let n = reader.by_ref().take(1048577).read_line(&mut line)?;
        if n == 0 {
            break;
        }
        if n > 1048576 {
            return Err("context record exceeds 1 MiB".into());
        }
        visit(serde_json::from_str(&line)?)?;
    }
    Ok(())
}
fn main() -> Result<(), Box<dyn std::error::Error>> {
    let args: Vec<_> = std::env::args().collect();
    let option = |name: &str| {
        args.iter()
            .position(|a| a == name)
            .and_then(|i| args.get(i + 1))
            .cloned()
    };
    let start = option("--start")
        .map(|s| s.parse::<f64>())
        .transpose()?
        .unwrap_or(0.);
    let end = option("--end")
        .map(|s| s.parse::<f64>())
        .transpose()?
        .unwrap_or(f64::MAX);
    if !start.is_finite() || !end.is_finite() || end < start {
        return Err("invalid time range".into());
    }
    let thread = option("--thread").map(|s| s.parse::<u64>()).transpose()?;
    let symbol = option("--symbol").unwrap_or_default();
    let library = option("--library").unwrap_or_default();
    let domain = option("--domain").unwrap_or_else(|| "native".into());
    let minimum = option("--min-size")
        .map(|s| s.parse::<u64>())
        .transpose()?
        .unwrap_or(0);
    let maximum = option("--max-size")
        .map(|s| s.parse::<u64>())
        .transpose()?
        .unwrap_or(u64::MAX);
    let attribution = option("--attribution").unwrap_or_else(|| "native".into());
    if ![
        "native",
        "python_functions",
        "python_exact_lines",
        "operations",
    ]
    .contains(&attribution.as_str())
    {
        return Err(
            "unsupported attribution; exact Python lines require verified Lab allocation records"
                .into(),
        );
    }
    if attribution == "python_exact_lines" && domain != "python_block" {
        return Err("Exact Python lines require verified Lab object-block records".into());
    }
    let mut context = context::Context::default();
    let mut native_symbols_invalid = false;
    if let Some(path) = option("--capture") {
        let mut reader = leakscope_capture::Reader::new(File::open(path)?)?;
        native_symbols_invalid = reader.metadata["quality"]["symbolization_invalidated"]
            .as_bool()
            .unwrap_or(false);
        context.incomplete = reader.metadata["quality"]["context_incomplete"]
            .as_bool()
            .unwrap_or(false);
        while let Some(raw) = reader.next_chunk()? {
            for item in serde_json::from_slice::<Vec<Value>>(&raw)? {
                if item["kind"] == "quality" {
                    native_symbols_invalid |= item["quality"]["symbolization_invalidated"]
                        .as_bool()
                        .unwrap_or(false);
                }
                context.ingest(&item)?;
            }
        }
    }
    if let Some(path) = option("--context") {
        context_records(&path, |item| {
            context.ingest(&item)?;
            Ok(())
        })?;
    }
    context.finish();
    let mut operation_bytes: HashMap<String, (u64, u64)> = HashMap::new();
    let mut lifecycle = Lifecycle::default();
    let mut stacks: HashMap<String, Value> = HashMap::new();
    let mut stack_bytes = 0usize;
    let mut node_budget = 32768usize;
    let mut total = Node {
        name: if domain == "python_block" {
            "Observed Python object blocks".into()
        } else {
            "Native allocations".into()
        },
        ..Default::default()
    };
    let mut retained = Node {
        name: "Known surviving allocations".into(),
        ..Default::default()
    };
    let mut quality = json!({});
    let mut created_cohorts: BTreeMap<i64, (u64, u64)> = BTreeMap::new();
    let mut domain_totals = (0u64, 0u64, 0u64, 0u64, 0u64);
    let mut selected_count = 0u64;
    let mut selected_bytes = 0u64;
    let mut sites: BTreeMap<String, (u64, u64, u64, u64)> = BTreeMap::new();
    let frame_labels = |id: &Option<String>, stacks: &HashMap<String, Value>| -> Vec<String> {
        let mut labels: Vec<_> = id
            .as_ref()
            .and_then(|id| stacks.get(id))
            .and_then(|v| v.as_array())
            .map(|frames| {
                frames
                    .iter()
                    .rev()
                    .map(|f| {
                        if attribution == "python_exact_lines" {
                            return format!(
                                "{}:{} · {}",
                                f["file"].as_str().unwrap_or("[unknown]"),
                                f["line"]
                                    .as_u64()
                                    .map(|l| l.to_string())
                                    .unwrap_or_else(|| "?".into()),
                                f["function"].as_str().unwrap_or("[unknown frame]")
                            );
                        }
                        format!(
                            "{} · {}",
                            f["module"].as_str().unwrap_or("[unknown]"),
                            f["function"].as_str().unwrap_or("[unknown frame]")
                        )
                    })
                    .collect()
            })
            .unwrap_or_else(|| vec!["[allocation context unavailable]".into()]);
        labels.truncate(32);
        labels
    };
    let accepts = |t: f64, tid: u64, size: u64, d: &str, labels: &[String]| {
        t >= start
            && t <= end
            && thread.is_none_or(|x| x == tid)
            && d == domain
            && size >= minimum
            && size <= maximum
            && (symbol.is_empty() || labels.iter().any(|s| s.contains(&symbol)))
            && (library.is_empty() || labels.iter().any(|s| s.contains(&library)))
    };
    let mut consume = |item: Value| -> Result<(), Box<dyn std::error::Error>> {
        match item["kind"].as_str().unwrap_or("") {
            "stack" => {
                if stacks.len() >= 8192 {
                    return Err("stack table budget exceeded".into());
                }
                stack_bytes += item.to_string().len();
                if stack_bytes > 16 * 1024 * 1024 {
                    return Err("stack table byte budget exceeded".into());
                }
                let id = item["id"].as_str().ok_or("invalid stack ID")?;
                let frames = item["frames"].as_array().ok_or("invalid stack frames")?;
                if id.len() > 32
                    || frames.len() > 32
                    || frames.iter().any(|f| f.to_string().len() > 4096)
                {
                    return Err("stack metadata exceeds budget".into());
                }
                stacks.insert(id.into(), if native_symbols_invalid && item["quality"]!="verified_lab_allocation_frame" {
                    json!([{"module":"[unresolved]","function":"[executable mappings changed]","file":null,"line":null}])
                } else {json!(frames)});
            }
            "quality" => quality = item["quality"].clone(),
            "allocation" => {
                let mut event: Event = serde_json::from_value(item["event"].clone())?;
                if let Some(time) = event.monotonic_ns {
                    if attribution == "operations"
                        || (attribution == "python_functions" && event.domain != "python_block")
                    {
                        if let Some(frames) =
                            context.frames(&event.process, event.thread, time, &attribution)
                        {
                            use std::hash::{Hash, Hasher};
                            let mut hash = std::collections::hash_map::DefaultHasher::new();
                            for f in &frames {
                                f["module"].to_string().hash(&mut hash);
                                f["function"].to_string().hash(&mut hash);
                                f["first_line"].to_string().hash(&mut hash);
                            }
                            let id = format!("py-{:x}", hash.finish());
                            if stacks.len() >= 8192 && !stacks.contains_key(&id) {
                                return Err("attribution stack budget exceeded".into());
                            }
                            stacks.entry(id.clone()).or_insert(json!(frames));
                            event.stack = Some(id);
                        } else {
                            event.stack = None;
                        }
                    }
                } else if attribution != "native"
                    && attribution != "python_exact_lines"
                    && event.domain != "python_block"
                {
                    event.stack = None;
                }
                if event.timestamp > end {
                    return Ok(());
                }
                let labels = frame_labels(&event.stack, &stacks);
                let before = (
                    lifecycle.allocated,
                    lifecycle.freed,
                    lifecycle.allocations,
                    lifecycle.frees,
                    lifecycle.unknown_frees,
                );
                lifecycle.apply(&event)?;
                if event.domain == domain {
                    domain_totals.0 += lifecycle.allocated - before.0;
                    domain_totals.1 += lifecycle.freed - before.1;
                    domain_totals.2 += lifecycle.allocations - before.2;
                    domain_totals.3 += lifecycle.frees - before.3;
                    domain_totals.4 += lifecycle.unknown_frees - before.4;
                }
                if event.pointer != 0
                    && (event.kind == "alloc" || event.kind == "realloc")
                    && accepts(
                        event.timestamp,
                        event.thread,
                        event.size,
                        &event.domain,
                        &labels,
                    )
                {
                    if let Some(op) = event
                        .monotonic_ns
                        .and_then(|t| context.operation(&event.process, event.thread, t))
                    {
                        operation_bytes
                            .entry(op["id"].as_str().unwrap_or_default().to_string())
                            .or_default()
                            .0 += event.size;
                    }
                    let bucket = (event.timestamp / 10.).floor() as i64;
                    if created_cohorts.len() >= 4096 && !created_cohorts.contains_key(&bucket) {
                        return Err("cohort budget exceeded".into());
                    }
                    let cohort = created_cohorts.entry(bucket).or_default();
                    cohort.0 = cohort.0.saturating_add(event.size);
                    cohort.1 += 1;
                    selected_count += 1;
                    selected_bytes = selected_bytes
                        .checked_add(event.size)
                        .ok_or("selected byte overflow")?;
                    if sites.len() >= 8192
                        && !sites.contains_key(&event.stack.clone().unwrap_or_default())
                    {
                        return Err("site budget exceeded".into());
                    }
                    let s = sites
                        .entry(event.stack.clone().unwrap_or_default())
                        .or_default();
                    s.0 += event.size;
                    s.1 += 1;
                    total.add(&labels, event.size, &mut node_budget);
                }
            }
            _ => {}
        }
        Ok(())
    };
    let mut recovered = false;
    if let Some(path) = option("--capture") {
        let mut reader = leakscope_capture::Reader::new(File::open(path)?)?;
        consume(json!({"kind":"quality","quality":reader.metadata["quality"]}))?;
        let mut capture_sequence = 0u64;
        let mut capture_gaps = false;
        while let Some(raw) = reader.next_chunk()? {
            let events: Vec<Value> = serde_json::from_slice(&raw)?;
            if events.len() > 10000 {
                return Err("chunk event budget exceeded".into());
            }
            if events.is_empty()
                || events.first().and_then(|v| v["sequence"].as_u64())
                    != reader.last_range.map(|r| r.0)
                || events.last().and_then(|v| v["sequence"].as_u64())
                    != reader.last_range.map(|r| r.1)
            {
                return Err("event range differs from chunk header".into());
            }
            for item in events {
                let seq = item["sequence"]
                    .as_u64()
                    .ok_or("missing capture sequence")?;
                if seq <= capture_sequence {
                    return Err("reordered capture event".into());
                }
                capture_gaps |= seq != capture_sequence + 1;
                capture_sequence = seq;
                consume(item)?;
            }
        }
        recovered = reader.recovered || reader.missing_sequences > 0 || capture_gaps;
    } else {
        let stdin = io::stdin();
        let mut input = stdin.lock();
        let mut line = String::new();
        loop {
            line.clear();
            let n = input.by_ref().take(1048577).read_line(&mut line)?;
            if n == 0 {
                break;
            }
            if n > 1048576 {
                return Err("event exceeds 1 MiB".into());
            }
            let value: Value = serde_json::from_str(&line)?;
            let wrapped = if value.get("event").is_some()
                || value["kind"] == "stack"
                || value["kind"] == "quality"
            {
                value
            } else {
                json!({"kind":"allocation","event":value})
            };
            consume(wrapped)?;
        }
    }
    if let Some(path) = option("--context") {
        context_records(&path, &mut consume)?;
    }
    let mut cohorts: BTreeMap<i64, (u64, u64)> = BTreeMap::new();
    for ((process, d, _), a) in &lifecycle.live {
        let labels = frame_labels(&a.stack, &stacks);
        if accepts(a.timestamp, a.thread, a.size, d, &labels) {
            if let Some(op) = a
                .monotonic_ns
                .and_then(|t| context.operation(process, a.thread, t))
            {
                operation_bytes
                    .entry(op["id"].as_str().unwrap_or_default().to_string())
                    .or_default()
                    .1 += a.size;
            }
            retained.add(&labels, a.size, &mut node_budget);
            let s = sites
                .entry(a.stack.clone().unwrap_or_default())
                .or_default();
            s.2 += a.size;
            s.3 += 1;
            let cohort = cohorts
                .entry((a.timestamp / 10.).floor() as i64)
                .or_default();
            cohort.0 += a.size;
            cohort.1 += 1;
        }
    }
    let lost =
        quality["lost_events"].as_u64().unwrap_or(0) + quality["lost_native"].as_u64().unwrap_or(0);
    let exact = !lifecycle.incomplete
        && !recovered
        && !quality["incomplete"].as_bool().unwrap_or(false)
        && lost == 0;
    quality["context_overlay"] = json!(option("--context").is_some());
    quality["tree_nodes_truncated"] = json!(node_budget == 0);
    quality["incomplete"] = json!(!exact);
    quality["exact_survivors"] = json!(exact);
    quality["lost_events"] = json!(lost.max(lifecycle.lost_events));
    quality["attribution"] = json!(if domain == "python_block" && attribution != "operations" {
        "allocation_time_python_frames"
    } else if attribution == "native" {
        "native_only"
    } else {
        "temporal_python_context"
    });
    quality["context_incomplete"] =
        json!(context.incomplete || quality["context_incomplete"].as_bool().unwrap_or(false));
    quality["python_exact_allocation_lines"] = json!(
        domain == "python_block"
            && stacks
                .values()
                .any(|frames| frames.as_array().is_some_and(|fs| fs
                    .iter()
                    .any(|f| f["evidence"] == "verified_lab_allocation_frame")))
    );
    let operations: Vec<_> = context
        .operations
        .values()
        .map(|o| {
            let mut o = o.clone();
            let (allocated, live) = operation_bytes
                .get(o["id"].as_str().unwrap_or_default())
                .copied()
                .unwrap_or_default();
            o["occurred_allocated_bytes"] = json!(allocated);
            o["observed_live_bytes"] = json!(live);
            o["known_live_bytes"] = json!(if exact { Some(live) } else { None });
            o["association"] =
                json!("allocation_occurred_during_operation; ownership_not_established");
            o
        })
        .collect();
    let mut top:Vec<_>=sites.into_iter().map(|(id,(bytes,count,live,active))|json!({"stack_id":id,"allocated_bytes":bytes,"allocation_count":count,"observed_live_bytes":live,"known_live_bytes":if exact{Some(live)}else{None},"active_count":active,"frames":stacks.get(&id)})).collect();
    top.sort_by_key(|v| std::cmp::Reverse(v["observed_live_bytes"].as_u64().unwrap_or(0)));
    let cohorts: Vec<_> = created_cohorts.into_iter().map(|(bucket,(created,count))| {
        let (live,active)=cohorts.get(&bucket).copied().unwrap_or_default();
        json!({"start":bucket as f64*10.,"created_bytes":created,"created_count":count,"observed_surviving_bytes":live,"count":active,"survivor_fraction":if exact&&created>0{Some(live as f64/created as f64)}else{None},"exact":exact})
    }).collect();
    println!(
        "{}",
        json!({"allocated_bytes":domain_totals.0,"freed_bytes":domain_totals.1,"allocation_count":domain_totals.2,"free_count":domain_totals.3,"selected_allocated_bytes":selected_bytes,"selected_allocation_count":selected_count,"known_live_by_domain":if exact{Some(lifecycle.live_by_domain())}else{None},"observed_live_by_domain":lifecycle.live_by_domain(),"exact_survivors":exact,"incomplete":!exact,"unknown_pre_capture_frees":domain_totals.4,"lost_events":lost.max(lifecycle.lost_events),"quality":quality,"allocation_tree":total,"retained_tree":retained,"top_sites":top,"cohorts":cohorts,"operations":operations,"attribution":attribution,"domain":domain,"limitations":["Only observed allocations are reconstructed; pre-attach allocations are unknown.","Native memory domains are not additive with Python arenas or blocks.","Missing events, ambiguous realloc(p,0) or pointer collisions suppress exact survivor claims.","Native stacks are native-only. Cooperative function boundaries support temporal correlation, not exact allocation lines. Lab frames are allocation-time observations when the GIL check succeeds."]})
    );
    Ok(())
}
