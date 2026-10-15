//! Read-only procfs access. No ptrace, target code execution, or cmdline arguments.
use leakscope_common::{ProcessIdentity, digest, now};
use serde::{Deserialize, Serialize};
use std::os::unix::fs::MetadataExt;
use std::{fs, io, path::Path};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Sample {
    pub timestamp: f64,
    pub rss: u64,
    pub pss: Option<u64>,
    pub private_bytes: Option<u64>,
    pub anonymous: u64,
    pub virtual_bytes: u64,
    pub swap: u64,
    pub threads: u64,
    pub cpu_ticks: u64,
    pub minor_faults: u64,
    pub major_faults: u64,
}
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Process {
    pub key: String,
    pub identity: ProcessIdentity,
    pub pid: u32,
    pub ppid: u32,
    pub uid: u32,
    pub executable: String,
    pub name: String,
    pub python_version: Option<String>,
    pub worker_type: String,
    pub sample: Sample,
}
#[derive(Debug)]
pub struct Stat {
    pub pid: u32,
    pub ppid: u32,
    pub start: u64,
    pub cpu: u64,
    pub minor: u64,
    pub major: u64,
}
pub fn parse_stat(s: &str) -> io::Result<Stat> {
    let end = s
        .rfind(')')
        .ok_or_else(|| io::Error::other("stat comm delimiter"))?;
    let fields: Vec<_> = s[end + 1..].split_whitespace().collect();
    let n = |i: usize| -> io::Result<u64> {
        fields
            .get(i)
            .ok_or_else(|| io::Error::other("short stat"))?
            .parse()
            .map_err(io::Error::other)
    };
    Ok(Stat {
        pid: s
            .split_whitespace()
            .next()
            .unwrap_or("")
            .parse()
            .map_err(io::Error::other)?,
        ppid: n(1)? as u32,
        start: n(19)?,
        cpu: n(11)? + n(12)?,
        minor: n(7)?,
        major: n(9)?,
    })
}
pub fn kb(s: &str, key: &str) -> Option<u64> {
    s.lines().find_map(|l| {
        let (k, v) = l.split_once(':')?;
        if k == key {
            v.split_whitespace()
                .next()?
                .parse::<u64>()
                .ok()?
                .checked_mul(1024)
        } else {
            None
        }
    })
}
pub fn host_id() -> String {
    digest(
        fs::read("/etc/machine-id")
            .unwrap_or_else(|_| b"unknown-host".to_vec())
            .as_slice(),
    )
}
pub fn identity(pid: u32) -> io::Result<ProcessIdentity> {
    Ok(ProcessIdentity {
        host: host_id(),
        boot: fs::read_to_string("/proc/sys/kernel/random/boot_id")?
            .trim()
            .into(),
        namespace: fs::read_link(format!("/proc/{pid}/ns/pid"))?
            .to_string_lossy()
            .into(),
        pid,
        start_ticks: parse_stat(&fs::read_to_string(format!("/proc/{pid}/stat"))?)?.start,
    })
}
pub fn read_process(pid: u32, allowed_uid: u32, expensive: bool) -> io::Result<Process> {
    let base = format!("/proc/{pid}");
    let uid = fs::metadata(&base)?.uid();
    if uid != allowed_uid {
        return Err(io::Error::new(
            io::ErrorKind::PermissionDenied,
            "target UID not allowed",
        ));
    }
    let id = identity(pid)?;
    let stat = parse_stat(&fs::read_to_string(format!("{base}/stat"))?)?;
    let status = fs::read_to_string(format!("{base}/status"))?;
    let name = status
        .lines()
        .find_map(|s| s.strip_prefix("Name:"))
        .unwrap_or("unknown")
        .trim()
        .to_owned();
    let executable = fs::read_link(format!("{base}/exe"))?
        .to_string_lossy()
        .into_owned();
    let rollup = if expensive {
        fs::read_to_string(format!("{base}/smaps_rollup")).ok()
    } else {
        None
    };
    let pss = rollup.as_deref().and_then(|s| kb(s, "Pss"));
    let private_bytes = rollup
        .as_deref()
        .and_then(|s| Some(kb(s, "Private_Clean")? + kb(s, "Private_Dirty")?));
    let python_version = if executable.contains("python2.7") {
        Some("2.7 (path evidence; ABI unknown)".into())
    } else if executable.contains("python3") {
        Some("3.x (path evidence; ABI unknown)".into())
    } else {
        None
    };
    let worker_type = if name.contains("uwsgi") {
        "uwsgi"
    } else if name.contains("rq") {
        "rq"
    } else if python_version.is_some() {
        "python"
    } else {
        "native"
    }
    .into();
    let sample = Sample {
        timestamp: now(),
        rss: kb(&status, "VmRSS").unwrap_or(0),
        pss,
        private_bytes,
        anonymous: kb(&status, "RssAnon").unwrap_or(0),
        virtual_bytes: kb(&status, "VmSize").unwrap_or(0),
        swap: kb(&status, "VmSwap").unwrap_or(0),
        threads: status
            .lines()
            .find_map(|l| l.strip_prefix("Threads:"))
            .and_then(|s| s.trim().parse().ok())
            .unwrap_or(0),
        cpu_ticks: stat.cpu,
        minor_faults: stat.minor,
        major_faults: stat.major,
    };
    // Revalidate identity after multiple procfs reads: never attribute a replacement to a prior worker.
    if identity(pid)? != id {
        return Err(io::Error::other("process identity changed during sample"));
    }
    Ok(Process {
        key: id.key(),
        identity: id,
        pid,
        ppid: stat.ppid,
        uid,
        executable,
        name,
        python_version,
        worker_type,
        sample,
    })
}
pub fn discover(uid: u32) -> Vec<Process> {
    let Ok(entries) = fs::read_dir("/proc") else {
        return Vec::new();
    };
    let mut out: Vec<_> = entries
        .flatten()
        .filter_map(|e| e.file_name().to_str()?.parse().ok())
        .filter_map(|pid| read_process(pid, uid, false).ok())
        .collect();
    out.sort_by_key(|p| p.pid);
    out
}
pub fn capabilities() -> serde_json::Value {
    serde_json::json!({"observe":true,"deep":false,"lab":false,"external_allocations":false,"metrics_only":true,"bpf_btf":Path::new("/sys/kernel/btf/vmlinux").exists(),"perf_event_paranoid":fs::read_to_string("/proc/sys/kernel/perf_event_paranoid").unwrap_or_default().trim(),"reason":"This build has no enabled external probe attachment engine. ELF symbol discovery is available; metrics require no kernel tracing privileges.","remediation":"Use Observe for trends, or initialize the cooperative Python 2 agent for bounded GC evidence. Do not change kernel security settings."})
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn parses_comm_with_spaces_and_parentheses() {
        let s = "4 (a ) b) S 3 0 0 0 0 0 7 0 9 0 11 12 0 0 0 0 1 0 42 0 0";
        let p = parse_stat(s).unwrap();
        assert_eq!(
            (p.pid, p.ppid, p.start, p.cpu, p.minor, p.major),
            (4, 3, 42, 23, 7, 9)
        );
    }
    #[test]
    fn malformed_stat_rejected() {
        assert!(parse_stat("1 (a) R").is_err());
        assert_eq!(kb("VmRSS: 42 kB\nVmSize: 3 kB", "VmRSS"), Some(43008));
    }
    #[test]
    fn actual_process_and_privacy() {
        let pid = std::process::id();
        let uid = fs::metadata("/proc/self").unwrap().uid();
        let p = read_process(pid, uid, true).unwrap();
        assert_eq!(p.pid, pid);
        assert!(p.sample.rss > 0);
        assert!(read_process(pid, uid + 1, false).is_err());
    }
}
