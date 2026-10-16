//! Bounded cooperative evidence. Temporal association never establishes ownership.
use serde_json::{Value, json};
use std::collections::{BTreeMap, HashMap};
type Interval = (u64, u64, Vec<Value>);
#[derive(Default)]
struct OperationIndex {
    ids: Vec<String>,
    ends: Vec<u64>,
    base: usize,
}
impl OperationIndex {
    fn build(mut ids: Vec<String>, operations: &BTreeMap<String, Value>) -> Self {
        ids.sort_by_key(|id| operations[id]["start_ns"].as_u64().unwrap_or(0));
        let base = ids.len().max(1).next_power_of_two();
        let mut ends = vec![0; base * 2];
        for (i, id) in ids.iter().enumerate() {
            ends[base + i] = operations[id]["end_ns"].as_u64().unwrap_or(0);
        }
        for i in (1..base).rev() {
            ends[i] = ends[i * 2].max(ends[i * 2 + 1]);
        }
        Self { ids, ends, base }
    }
    fn visit<'a>(
        &'a self,
        node: usize,
        lo: usize,
        hi: usize,
        time: u64,
        operations: &'a BTreeMap<String, Value>,
        out: &mut Vec<&'a Value>,
    ) {
        if lo >= self.ids.len()
            || self.ends[node] <= time
            || operations[&self.ids[lo]]["start_ns"].as_u64().unwrap_or(0) > time
        {
            return;
        }
        if hi - lo == 1 {
            out.push(&operations[&self.ids[lo]]);
            return;
        }
        let middle = (lo + hi) / 2;
        self.visit(node * 2, lo, middle, time, operations, out);
        self.visit(node * 2 + 1, middle, hi, time, operations, out);
    }
}
#[derive(Default)]
pub struct Context {
    pub operations: BTreeMap<String, Value>,
    codes: HashMap<(String, u64, u64), Value>,
    operation_index: HashMap<(String, u64), OperationIndex>,
    events: HashMap<(String, u64), Vec<(u64, Value)>>,
    intervals: HashMap<(String, u64), Vec<Interval>>,
    pub incomplete: bool,
    bytes: usize,
}
impl Context {
    pub fn ingest(&mut self, item: &Value) -> Result<(), String> {
        let kind = item["kind"].as_str().unwrap_or("");
        if kind == "quality" {
            self.incomplete |= item["quality"]["context_incomplete"]
                .as_bool()
                .unwrap_or(false);
            return Ok(());
        }
        if !["operation", "python_codes", "python_profile"].contains(&kind) {
            return Ok(());
        }
        self.bytes += item.to_string().len();
        if self.bytes > 16 * 1024 * 1024 {
            return Err("Python context byte budget exceeded".into());
        }
        let payload = &item["payload"];
        match kind {
            "operation" => {
                let id = payload["id"].as_str().ok_or("operation without identity")?;
                if id.len() > 100 || self.operations.len() >= 4096 {
                    return Err("operation table budget exceeded".into());
                }
                let mut value = payload.clone();
                value["process_key"] = item["process_key"].clone();
                if let Some(old) = self.operations.get(id)
                    && (old["start_ns"] != value["start_ns"]
                        || old["thread"] != value["thread"]
                        || old["process_key"] != value["process_key"])
                {
                    return Err("operation identity changed".into());
                }
                self.operations.insert(id.into(), value);
            }
            "python_codes" => {
                let epoch = payload["epoch"].as_u64().ok_or("invalid profile epoch")?;
                for code in payload["codes"]
                    .as_array()
                    .ok_or("invalid Python code table")?
                {
                    if self.codes.len() >= 4096 || code.to_string().len() > 1024 {
                        return Err("Python code budget exceeded".into());
                    }
                    self.codes.insert(
                        (
                            item["process_key"]
                                .as_str()
                                .ok_or("code without process")?
                                .into(),
                            epoch,
                            code["id"].as_u64().ok_or("invalid Python code ID")?,
                        ),
                        code.clone(),
                    );
                }
            }
            _ => {
                self.incomplete |= payload["lost"].as_u64().unwrap_or(0) > 0;
                let process = item["process_key"]
                    .as_str()
                    .ok_or("profile without process")?
                    .to_string();
                let epoch = payload["epoch"].as_u64().ok_or("invalid profile epoch")?;
                for event in payload["events"]
                    .as_array()
                    .ok_or("invalid profile events")?
                {
                    let thread = event["thread"].as_u64().ok_or("invalid profile thread")?;
                    let events = self.events.entry((process.clone(), thread)).or_default();
                    if events.len() >= 65536 || self.events.len() > 256 {
                        return Err("Python boundary budget exceeded".into());
                    }
                    self.events
                        .get_mut(&(process.clone(), thread))
                        .unwrap()
                        .push((epoch, event.clone()));
                }
            }
        }
        Ok(())
    }
    pub fn finish(&mut self) {
        let mut groups: HashMap<(String, u64), Vec<String>> = HashMap::new();
        for (id, op) in &self.operations {
            groups
                .entry((
                    op["process_key"].as_str().unwrap_or("").into(),
                    op["thread"].as_u64().unwrap_or(0),
                ))
                .or_default()
                .push(id.clone());
        }
        for (key, ids) in groups {
            self.operation_index
                .insert(key, OperationIndex::build(ids, &self.operations));
        }
        for (key, events) in &mut self.events {
            events.sort_by_key(|(_, e)| e["monotonic_ns"].as_u64().unwrap_or(0));
            let intervals = self.intervals.entry(key.clone()).or_default();
            for pair in events.windows(2) {
                let (epoch, event) = &pair[0];
                let (_, next) = &pair[1];
                if epoch != &pair[1].0 || event["activation"] != next["activation"] {
                    continue;
                }
                if event["event"] == 7 {
                    continue;
                } // Explicit profiler safe-point gap.
                let start = event["monotonic_ns"].as_u64().unwrap_or(0);
                let end = next["monotonic_ns"].as_u64().unwrap_or(0);
                let mut frames = Vec::new();
                if let Some(ids) = event["frames"].as_array() {
                    for (i, id) in ids.iter().enumerate().take(16) {
                        // After a Python return, only the caller remains active.
                        if i == 0 && event["event"] == 3 {
                            continue;
                        }
                        if let Some(code) =
                            self.codes
                                .get(&(key.0.clone(), *epoch, id[0].as_u64().unwrap_or(0)))
                        {
                            frames.push(json!({"file":code["file"],"function":code["function"],
                                "first_line":code["first_line"],"boundary_line":id[1],"line":null,
                                "module":code["file"],"evidence":"temporally_correlated_python_context"}));
                        } else {
                            self.incomplete = true;
                        }
                    }
                }
                if end > start && !frames.is_empty() {
                    intervals.push((start, end, frames));
                }
            }
        }
    }
    pub fn operation(&self, process: &str, thread: u64, time: u64) -> Option<&Value> {
        let index = self.operation_index.get(&(process.into(), thread))?;
        let mut matching = Vec::new();
        index.visit(1, 0, index.base, time, &self.operations, &mut matching);
        matching.sort_by_key(|o| o["depth"].as_u64().unwrap_or(0));
        let last = matching.pop()?;
        // Sibling overlaps have no unique most-specific operation.
        if matching
            .last()
            .is_some_and(|other| other["depth"] == last["depth"])
        {
            return None;
        }
        Some(last)
    }
    pub fn frames(
        &self,
        process: &str,
        thread: u64,
        time: u64,
        attribution: &str,
    ) -> Option<Vec<Value>> {
        if attribution == "operations" {
            let mut op = self.operation(process, thread, time)?;
            let mut frames = Vec::new();
            for _ in 0..32 {
                frames.push(
                    json!({"module":op["module"].as_str().unwrap_or("operation"),
                    "function":op["operation"],"line":null,"file":null,
                    "evidence":"temporally_correlated_operation","operation_id":op["id"]}),
                );
                let Some(parent) = op["parent"].as_str().and_then(|id| self.operations.get(id))
                else {
                    break;
                };
                op = parent;
            }
            return Some(frames);
        }
        if self.incomplete {
            return None;
        }
        let intervals = self.intervals.get(&(process.into(), thread))?;
        let index = intervals
            .partition_point(|(start, _, _)| *start <= time)
            .checked_sub(1)?;
        let (start, end, frames) = &intervals[index];
        (*start <= time && time < *end).then(|| frames.clone())
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    fn operation(id: &str, parent: Option<&str>, depth: u64, start: u64, end: u64) -> Value {
        json!({"kind":"operation","process_key":"p","payload":{"id":id,"parent":parent,"depth":depth,"start_ns":start,"end_ns":end,"thread":7,"operation":id}})
    }
    #[test]
    fn nested_intervals_ambiguity_and_thread_isolation() {
        let mut c = Context::default();
        c.ingest(&operation("outer", None, 0, 100, 1000)).unwrap();
        c.ingest(&operation("inner", Some("outer"), 1, 150, 200))
            .unwrap();
        c.finish();
        assert_eq!(c.operation("p", 7, 170).unwrap()["id"], "inner");
        assert_eq!(c.operation("p", 7, 900).unwrap()["id"], "outer");
        assert!(c.operation("p", 8, 170).is_none());
        assert!(c.operation("replaced", 7, 170).is_none());
        c.ingest(&operation("ambiguous", Some("outer"), 1, 160, 190))
            .unwrap();
        c.finish();
        assert!(c.operation("p", 7, 170).is_none());
    }
    #[test]
    fn gaps_and_activation_changes_never_reuse_stale_frames() {
        let mut c = Context::default();
        c.ingest(&json!({"kind":"python_codes","process_key":"p","payload":{"epoch":1,"codes":[{"id":1,"file":"fixture.py","function":"allocate","first_line":10}]}})).unwrap();
        let events:Vec<_>=[(100,4,1),(150,7,1),(300,8,1),(350,6,1),(400,8,2),(450,6,2)].into_iter().enumerate().map(|(i,(time,event,activation))|json!({"sequence":i+1,"monotonic_ns":time,"thread":7,"event":event,"activation":activation,"frames":[[1,11]]})).collect();
        c.ingest(&json!({"kind":"python_profile","process_key":"p","payload":{"epoch":1,"lost":0,"events":events}})).unwrap();
        c.finish();
        let frame = c.frames("p", 7, 125, "python_functions").unwrap();
        assert_eq!(frame[0]["function"], "allocate");
        assert!(frame[0]["line"].is_null());
        assert!(c.frames("p", 7, 200, "python_functions").is_none());
        assert!(c.frames("p", 7, 375, "python_functions").is_none());
        assert!(c.frames("p", 8, 125, "python_functions").is_none());
        c.ingest(&json!({"kind":"quality","quality":{"context_incomplete":true}}))
            .unwrap();
        assert!(c.frames("p", 7, 125, "python_functions").is_none());
    }
}
