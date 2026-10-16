use prost::Message;
use std::io;
use tokio::io::{AsyncRead, AsyncReadExt, AsyncWrite, AsyncWriteExt};

pub const VERSION: u32 = 1;
pub const MAX_FRAME: usize = 1024 * 1024;
#[derive(Clone, PartialEq, Message)]
pub struct Envelope {
    #[prost(uint32, tag = "1")]
    pub version: u32,
    #[prost(string, tag = "2")]
    pub token: String,
    #[prost(uint64, tag = "3")]
    pub sequence: u64,
    #[prost(bytes = "vec", tag = "4")]
    pub payload: Vec<u8>,
}
pub async fn read_frame<R: AsyncRead + Unpin>(r: &mut R) -> io::Result<Envelope> {
    let n = r.read_u32().await? as usize;
    if n == 0 || n > MAX_FRAME {
        return Err(io::Error::other("invalid frame size"));
    }
    let mut bytes = vec![0; n];
    r.read_exact(&mut bytes).await?;
    let msg = Envelope::decode(bytes.as_slice()).map_err(io::Error::other)?;
    if msg.version != VERSION {
        return Err(io::Error::other("unsupported protocol version"));
    }
    Ok(msg)
}
pub async fn write_frame<W: AsyncWrite + Unpin>(w: &mut W, msg: Envelope) -> io::Result<()> {
    let bytes = msg.encode_to_vec();
    if bytes.len() > MAX_FRAME {
        return Err(io::Error::other("frame exceeds limit"));
    }
    w.write_u32(bytes.len() as u32).await?;
    w.write_all(&bytes).await
}
#[cfg(test)]
mod tests {
    use super::*;
    #[tokio::test]
    async fn validates_and_roundtrips() {
        let (mut a, mut b) = tokio::io::duplex(1024);
        let msg = Envelope {
            version: VERSION,
            token: "secret".into(),
            sequence: 4,
            payload: b"{}".to_vec(),
        };
        write_frame(&mut a, msg.clone()).await.unwrap();
        assert_eq!(read_frame(&mut b).await.unwrap(), msg);
        a.write_u32((MAX_FRAME + 1) as u32).await.unwrap();
        assert!(read_frame(&mut b).await.is_err());
    }
}

/// Allocation model shared by sensor, captures and analyzer. Sequence belongs to
/// the allocation stream (table/metric records use the capture envelope sequence).
#[derive(Debug, Clone, serde::Serialize, serde::Deserialize)]
pub struct AllocationEvent {
    #[serde(default = "event_version")]
    pub version: u32,
    #[serde(default = "unknown_source")]
    pub source: String,
    #[serde(default)]
    pub pid: u32,
    #[serde(default)]
    pub monotonic_ns: Option<u64>,
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

fn event_version() -> u32 {
    1
}
fn unknown_source() -> String {
    "unknown".into()
}

/// Decode aligned little-endian kernel wire v1 without unsafe memory casts.
#[derive(Debug)]
pub struct NativeRecord {
    pub thread: u64,
    pub time: u64,
    pub pointer: u64,
    pub old_pointer: u64,
    pub size: u64,
    pub stack: i64,
    pub kind: u64,
    pub caller: u64,
}
impl NativeRecord {
    pub fn decode(data: &[u8]) -> std::io::Result<Self> {
        if data.len() != 72 {
            return Err(std::io::Error::other("native record size mismatch"));
        }
        let mut words = [0u64; 9];
        for (i, bytes) in data.chunks_exact(8).enumerate() {
            words[i] = u64::from_le_bytes(bytes.try_into().unwrap());
        }
        if words[0] != 1 || !(1..=4).contains(&words[7]) {
            return Err(std::io::Error::other(
                "unsupported native event version or kind",
            ));
        }
        Ok(Self {
            thread: words[1],
            time: words[2],
            pointer: words[3],
            old_pointer: words[4],
            size: words[5],
            stack: words[6] as i64,
            kind: words[7],
            caller: words[8],
        })
    }
}
#[cfg(test)]
mod native_tests {
    use super::*;
    #[test]
    fn wire_size_version_and_kind() {
        assert!(NativeRecord::decode(&[0; 71]).is_err());
        let mut data = [0u8; 72];
        data[0] = 1;
        data[56] = 1;
        assert!(NativeRecord::decode(&data).is_ok());
        data[0] = 2;
        assert!(NativeRecord::decode(&data).is_err());
        data[0] = 1;
        data[56] = 5;
        assert!(NativeRecord::decode(&data).is_err());
    }
}
