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
