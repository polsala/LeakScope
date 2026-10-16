//! LSCAP v1 streaming chunks. Decompression is bounded before interpreting data.
use sha2::{Digest, Sha256};
use std::io::{self, Read, Write};
pub const MAGIC: &[u8; 8] = b"LSCAP\0\x01\0";
pub const MAX_METADATA: usize = 65536;
pub const MAX_CHUNK: usize = 4 * 1024 * 1024;
fn invalid(s: &str) -> io::Error {
    io::Error::new(io::ErrorKind::InvalidData, s)
}
pub struct Writer<W: Write> {
    out: W,
    last: u64,
    pub bytes: u64,
}
impl<W: Write> Writer<W> {
    pub fn new(mut out: W, metadata: &serde_json::Value) -> io::Result<Self> {
        let b = serde_json::to_vec(metadata)?;
        if b.len() > MAX_METADATA {
            return Err(invalid("oversized metadata"));
        }
        out.write_all(MAGIC)?;
        out.write_all(&(b.len() as u32).to_be_bytes())?;
        out.write_all(&b)?;
        out.write_all(&Sha256::digest(&b))?;
        Ok(Self {
            out,
            last: 0,
            bytes: 44 + b.len() as u64,
        })
    }
    pub fn chunk(&mut self, first: u64, last: u64, data: &[u8]) -> io::Result<()> {
        if data.is_empty() || data.len() > MAX_CHUNK || first <= self.last || last < first {
            return Err(invalid("invalid chunk size or sequence"));
        }
        let compressed = zstd::stream::encode_all(data, 3)?;
        self.out.write_all(&(data.len() as u32).to_be_bytes())?;
        self.out
            .write_all(&(compressed.len() as u32).to_be_bytes())?;
        self.out.write_all(&first.to_be_bytes())?;
        self.out.write_all(&last.to_be_bytes())?;
        self.out.write_all(&Sha256::digest(data))?;
        self.out.write_all(&compressed)?;
        self.last = last;
        self.bytes += 56 + compressed.len() as u64;
        self.out.flush()
    }
    pub fn finish(mut self) -> io::Result<W> {
        self.out.write_all(&[0; 56])?;
        self.out.flush()?;
        Ok(self.out)
    }
}
pub struct Reader<R: Read> {
    input: R,
    pub metadata: serde_json::Value,
    pub recovered: bool,
    pub last_range: Option<(u64, u64)>,
    pub missing_sequences: u64,
    last: u64,
    ended: bool,
}
impl<R: Read> Reader<R> {
    pub fn new(mut input: R) -> io::Result<Self> {
        let mut magic = [0; 8];
        input.read_exact(&mut magic)?;
        if &magic != MAGIC {
            return Err(invalid("unsupported capture version"));
        }
        let mut n = [0; 4];
        input.read_exact(&mut n)?;
        let n = u32::from_be_bytes(n) as usize;
        if n > MAX_METADATA {
            return Err(invalid("oversized metadata"));
        }
        let mut b = vec![0; n];
        input.read_exact(&mut b)?;
        let mut sha = [0; 32];
        input.read_exact(&mut sha)?;
        if Sha256::digest(&b)[..] != sha {
            return Err(invalid("metadata checksum mismatch"));
        }
        let metadata = serde_json::from_slice(&b)?;
        Ok(Self {
            input,
            metadata,
            recovered: false,
            last_range: None,
            missing_sequences: 0,
            last: 0,
            ended: false,
        })
    }
    pub fn next_chunk(&mut self) -> io::Result<Option<Vec<u8>>> {
        if self.ended {
            return Ok(None);
        }
        let mut h = [0; 56];
        match self.input.read_exact(&mut h) {
            Ok(()) => {}
            Err(e) if e.kind() == io::ErrorKind::UnexpectedEof => {
                self.recovered = true;
                self.ended = true;
                return Ok(None);
            }
            Err(e) => return Err(e),
        }
        if h == [0; 56] {
            self.ended = true;
            let mut extra = [0; 1];
            if self.input.read(&mut extra)? != 0 {
                return Err(invalid("trailing capture bytes"));
            }
            return Ok(None);
        }
        let raw = u32::from_be_bytes(h[..4].try_into().unwrap()) as usize;
        let comp = u32::from_be_bytes(h[4..8].try_into().unwrap()) as usize;
        let first = u64::from_be_bytes(h[8..16].try_into().unwrap());
        let last = u64::from_be_bytes(h[16..24].try_into().unwrap());
        if raw == 0
            || raw > MAX_CHUNK
            || comp == 0
            || comp > MAX_CHUNK + 65536
            || first <= self.last
            || last < first
        {
            return Err(invalid("invalid chunk limits or sequence"));
        }
        let mut compressed = vec![0; comp];
        if let Err(e) = self.input.read_exact(&mut compressed) {
            if e.kind() == io::ErrorKind::UnexpectedEof {
                self.recovered = true;
                self.ended = true;
                return Ok(None);
            }
            return Err(e);
        }
        let mut decoder = zstd::stream::read::Decoder::new(compressed.as_slice())?;
        decoder.window_log_max(23)?;
        let mut data = Vec::new();
        decoder.take((raw + 1) as u64).read_to_end(&mut data)?;
        if data.len() != raw || Sha256::digest(&data)[..] != h[24..56] {
            return Err(invalid("chunk checksum or size mismatch"));
        }
        self.missing_sequences += first - self.last - 1;
        self.last = last;
        self.last_range = Some((first, last));
        Ok(Some(data))
    }
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn roundtrip_and_truncated_footer() {
        let mut w = Writer::new(Vec::new(), &serde_json::json!({"mode":"observe"})).unwrap();
        w.chunk(1, 1, b"[]").unwrap();
        w.chunk(3, 3, b"[]").unwrap();
        let b = w.finish().unwrap();
        let mut r = Reader::new(b.as_slice()).unwrap();
        assert_eq!(r.next_chunk().unwrap().unwrap(), b"[]");
        assert!(r.next_chunk().unwrap().is_some());
        assert!(r.next_chunk().unwrap().is_none());
        assert_eq!(r.missing_sequences, 1);
        let mut r = Reader::new(&b[..b.len() - 20]).unwrap();
        while r.next_chunk().unwrap().is_some() {}
        assert!(r.recovered);
    }
    #[test]
    fn corruption_and_limits() {
        let mut w = Writer::new(Vec::new(), &serde_json::json!({})).unwrap();
        assert!(w.chunk(0, 1, b"a").is_err());
        w.chunk(1, 1, b"hello").unwrap();
        let mut b = w.finish().unwrap();
        b[46 + 24] ^= 1;
        let mut r = Reader::new(b.as_slice()).unwrap();
        assert!(r.next_chunk().is_err());
    }
    #[test]
    fn empty() {
        let b = Writer::new(Vec::new(), &serde_json::json!({}))
            .unwrap()
            .finish()
            .unwrap();
        assert!(
            Reader::new(b.as_slice())
                .unwrap()
                .next_chunk()
                .unwrap()
                .is_none()
        );
    }
}
