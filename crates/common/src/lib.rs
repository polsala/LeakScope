use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use std::time::{SystemTime, UNIX_EPOCH};

pub fn digest(bytes: &[u8]) -> String {
    format!("{:x}", Sha256::digest(bytes))
}
pub fn now() -> f64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_secs_f64()
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq, Hash)]
pub struct ProcessIdentity {
    pub host: String,
    pub boot: String,
    pub namespace: String,
    pub pid: u32,
    pub start_ticks: u64,
}
impl ProcessIdentity {
    pub fn key(&self) -> String {
        digest(
            format!(
                "{}|{}|{}|{}|{}",
                self.host, self.boot, self.namespace, self.pid, self.start_ticks
            )
            .as_bytes(),
        )
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn pid_reuse_changes_identity() {
        let a = ProcessIdentity {
            host: "host".into(),
            boot: "boot".into(),
            namespace: "ns".into(),
            pid: 1,
            start_ticks: 2,
        };
        let mut b = a.clone();
        b.start_ticks += 1;
        assert_ne!(a.key(), b.key());
        b = a.clone();
        b.boot = "next".into();
        assert_ne!(a.key(), b.key());
    }
}
