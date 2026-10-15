use leakscope_analyzer::{Event, Lifecycle};
use serde_json::json;
use std::io::{self, BufRead, Read};
fn main() -> Result<(), Box<dyn std::error::Error>> {
    let mut lifecycle = Lifecycle::default();
    let mut count = 0;
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
        let event: Event = serde_json::from_str(&line)?;
        lifecycle.apply(&event)?;
        count += 1;
    }
    println!(
        "{}",
        json!({"event_count":count,"allocated_bytes":lifecycle.allocated,"freed_bytes":lifecycle.freed,"known_live_by_domain":lifecycle.live_by_domain(),"exact_survivors":!lifecycle.incomplete,"incomplete":lifecycle.incomplete,"unknown_pre_capture_frees":lifecycle.unknown_frees,"lost_events":lifecycle.lost_events,"limitations":["Unknown pre-capture allocations are excluded.","Memory domains are not additive."]})
    );
    Ok(())
}
