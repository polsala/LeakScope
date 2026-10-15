use object::{Object, ObjectSegment, ObjectSymbol};
use serde::Serialize;
use std::{fs, io, path::Path};
#[derive(Debug, Serialize)]
pub struct Symbol {
    pub name: String,
    pub address: u64,
    pub file_offset: Option<u64>,
}
#[derive(Debug, Serialize)]
pub struct ElfInfo {
    pub build_id: Option<String>,
    pub symbols: Vec<Symbol>,
}
pub fn inspect(path: &Path) -> io::Result<ElfInfo> {
    if fs::metadata(path)?.len() > 32 * 1024 * 1024 {
        return Err(io::Error::other("ELF exceeds inspection budget"));
    }
    let data = fs::read(path)?;
    let elf = object::File::parse(data.as_slice()).map_err(io::Error::other)?;
    let wanted = [
        "malloc",
        "calloc",
        "realloc",
        "free",
        "PyObject_Malloc",
        "PyObject_Realloc",
        "PyObject_Free",
    ];
    let mut symbols = Vec::new();
    for s in elf.symbols().chain(elf.dynamic_symbols()) {
        if s.is_undefined() {
            continue;
        }
        let Ok(name) = s.name() else { continue };
        if !wanted.contains(&name) {
            continue;
        }
        let address = s.address();
        let file_offset = elf.segments().find_map(|seg| {
            let (off, len) = seg.file_range();
            if address >= seg.address() && address - seg.address() < len {
                Some(off + address - seg.address())
            } else {
                None
            }
        });
        if !symbols.iter().any(|v: &Symbol| v.name == name) {
            symbols.push(Symbol {
                name: name.into(),
                address,
                file_offset,
            });
        }
    }
    let build_id = elf
        .build_id()
        .ok()
        .flatten()
        .map(|b| b.iter().map(|v| format!("{v:02x}")).collect());
    Ok(ElfInfo { build_id, symbols })
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn actual_elf() {
        let p = std::env::current_exe().unwrap();
        assert!(inspect(&p).is_ok());
    }
    #[test]
    fn rejects_non_elf() {
        assert!(inspect(Path::new("/etc/hosts")).is_err());
    }
}
