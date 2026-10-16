use object::{Object, ObjectSection, ObjectSegment, ObjectSymbol};
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

#[derive(Debug, Clone, serde::Serialize, serde::Deserialize)]
pub struct Mapping {
    pub start: u64,
    pub end: u64,
    pub offset: u64,
    pub path: String,
    pub inode: u64,
    pub build_id: Option<String>,
}
/// Only executable file mappings are relevant to native stack PCs. The file in
/// the target's mount namespace is used, never an assumed host library path.
pub fn mappings(pid: u32) -> io::Result<Vec<Mapping>> {
    let text = fs::read_to_string(format!("/proc/{pid}/maps"))?;
    let mut result = Vec::new();
    for line in text.lines() {
        let fields: Vec<_> = line.split_whitespace().collect();
        if fields.len() < 6 || !fields[1].contains('x') {
            continue;
        }
        let Some(pos) = line.find(" /") else { continue };
        let path = line[pos + 1..].to_owned();
        if path.ends_with(" (deleted)") {
            continue;
        }
        let Some((lo, hi)) = fields[0].split_once('-') else {
            continue;
        };
        let parse = |s: &str| u64::from_str_radix(s, 16).map_err(io::Error::other);
        result.push(Mapping {
            start: parse(lo)?,
            end: parse(hi)?,
            offset: parse(fields[2])?,
            path,
            inode: fields[4].parse().map_err(io::Error::other)?,
            build_id: None,
        });
        if result.len() > 4096 {
            return Err(io::Error::other("module mapping budget exceeded"));
        }
    }
    Ok(result)
}
pub fn target_path(pid: u32, path: &str) -> std::path::PathBuf {
    std::path::PathBuf::from(format!("/proc/{pid}/root{path}"))
}
#[derive(Debug, Clone, serde::Serialize, serde::Deserialize)]
pub struct Frame {
    pub address: String,
    pub module: String,
    pub function: String,
    pub file: Option<String>,
    pub line: Option<u32>,
    pub build_id: Option<String>,
}
struct Module {
    segments: Vec<(u64, u64, u64)>,
    symbols: Vec<(u64, u64, String)>,
    dwarf: Option<addr2line::Context<gimli::EndianArcSlice<gimli::RunTimeEndian>>>,
}
/// Cache ELF tables once per loaded module. No target memory or object contents
/// are read. Unknown PCs remain explicit hexadecimal frames.
pub struct Resolver {
    pid: u32,
    pub mappings: Vec<Mapping>,
    cache: std::collections::HashMap<String, Module>,
}
impl Resolver {
    pub fn new(pid: u32) -> io::Result<Self> {
        Ok(Self {
            pid,
            mappings: mappings(pid)?,
            cache: Default::default(),
        })
    }
    pub fn frame(&mut self, ip: u64) -> Frame {
        let mut f = Frame {
            address: format!("0x{ip:x}"),
            module: "[unknown mapping]".into(),
            function: format!("[0x{ip:x}]"),
            file: None,
            line: None,
            build_id: None,
        };
        let Some(map) = self
            .mappings
            .iter_mut()
            .find(|m| ip >= m.start && ip < m.end)
        else {
            return f;
        };
        f.module = map.path.clone();
        if !self.cache.contains_key(&map.path) {
            let path = target_path(self.pid, &map.path);
            let data = fs::metadata(&path)
                .ok()
                .filter(|m| m.len() <= 64 * 1024 * 1024)
                .and_then(|_| fs::read(path).ok());
            if let Some(data) = data
                && let Ok(elf) = object::File::parse(data.as_slice())
            {
                map.build_id = elf
                    .build_id()
                    .ok()
                    .flatten()
                    .map(|b| b.iter().map(|v| format!("{v:02x}")).collect());
                let segments = elf
                    .segments()
                    .map(|s| {
                        let (o, n) = s.file_range();
                        (o, n, s.address())
                    })
                    .collect();
                let mut symbols: Vec<_> = elf
                    .symbols()
                    .chain(elf.dynamic_symbols())
                    .filter(|s| !s.is_undefined() && s.kind() == object::SymbolKind::Text)
                    .filter_map(|s| Some((s.address(), s.size(), s.name().ok()?.to_owned())))
                    .collect();
                symbols.sort_by_key(|s| s.0);
                self.cache.insert(
                    map.path.clone(),
                    Module {
                        segments,
                        symbols,
                        dwarf: debug_context(&elf).or_else(|| {
                            separate_debug(self.pid, &map.path, map.build_id.as_deref())
                        }),
                    },
                );
            }
            self.cache.entry(map.path.clone()).or_insert(Module {
                segments: vec![],
                symbols: vec![],
                dwarf: None,
            });
        }
        f.build_id = map.build_id.clone();
        let module = &self.cache[&map.path];
        let offset = ip - map.start + map.offset;
        if let Some((off, _, base)) = module
            .segments
            .iter()
            .find(|(o, n, _)| offset >= *o && offset - *o < *n)
        {
            let address = base + offset - off;
            if let Some(ctx) = &module.dwarf {
                if let Ok(Some(location)) = ctx.find_location(address) {
                    f.file = location.file.map(remap_source);
                    f.line = location.line;
                }
                if let Ok(mut frames) = ctx.find_frames(address).skip_all_loads()
                    && let Ok(Some(frame)) = frames.next()
                    && let Some(function) = frame.function
                    && let Ok(name) = function.demangle()
                {
                    f.function = name.into_owned();
                }
            }
            let index = module.symbols.partition_point(|s| s.0 <= address);
            if index > 0 {
                let (start, size, name) = &module.symbols[index - 1];
                if f.function.starts_with("[") && *size > 0 && address - start < *size {
                    f.function = addr2line::demangle_auto(std::borrow::Cow::Borrowed(name), None)
                        .to_string();
                }
            }
        }
        f
    }
}
/// Resolve one complete allocator provider, preferring the actual mapped libc.
/// Interposed allocators are not mixed with libc backing allocations.
pub fn allocator(pid: u32) -> io::Result<(String, ElfInfo)> {
    let mut maps = mappings(pid)?;
    maps.sort_by_key(|m| {
        !std::path::Path::new(&m.path).file_name().is_some_and(|n| {
            n.to_string_lossy().starts_with("libc.so") || n.to_string_lossy().starts_with("libc-")
        })
    });
    for m in maps {
        let path = target_path(pid, &m.path);
        if let Ok(info) = inspect(&path)
            && ["malloc", "calloc", "realloc", "free"].iter().all(|name| {
                info.symbols
                    .iter()
                    .any(|s| s.name == *name && s.file_offset.is_some())
            })
        {
            return Ok((m.path, info));
        }
    }
    Err(io::Error::other(
        "No mapped ELF exports all malloc/calloc/realloc/free symbols; stripped/static/custom allocators require debug symbols or a supported provider",
    ))
}

// Compressed DWARF and split .dwo files are deliberately not expanded here.
// Keep symbolization memory bounded and avoid implicit unbounded decompression.
fn debug_context(
    elf: &object::File<'_>,
) -> Option<addr2line::Context<gimli::EndianArcSlice<gimli::RunTimeEndian>>> {
    elf.section_by_name(".debug_info")?;
    let endian = if elf.is_little_endian() {
        gimli::RunTimeEndian::Little
    } else {
        gimli::RunTimeEndian::Big
    };
    let mut total = 0usize;
    let dwarf = gimli::Dwarf::load(|id| -> io::Result<_> {
        let data = elf
            .section_by_name(id.name())
            .and_then(|s| s.data().ok())
            .unwrap_or(&[]);
        total = total.saturating_add(data.len());
        if total > 16 * 1024 * 1024 {
            return Err(io::Error::other("DWARF section budget exceeded"));
        }
        Ok(gimli::EndianArcSlice::new(
            std::sync::Arc::from(data),
            endian,
        ))
    })
    .ok()?;
    addr2line::Context::from_dwarf(dwarf).ok()
}
fn separate_debug(
    pid: u32,
    path: &str,
    build_id: Option<&str>,
) -> Option<addr2line::Context<gimli::EndianArcSlice<gimli::RunTimeEndian>>> {
    let id = build_id?;
    if id.len() < 3 {
        return None;
    }
    let paths = [
        format!("/usr/lib/debug/.build-id/{}/{}.debug", &id[..2], &id[2..]),
        format!("/usr/lib/debug{path}.debug"),
    ];
    for p in paths {
        let p = target_path(pid, &p);
        if fs::metadata(&p)
            .ok()
            .is_some_and(|m| m.len() <= 64 * 1024 * 1024)
            && let Ok(data) = fs::read(p)
            && let Ok(elf) = object::File::parse(data.as_slice())
        {
            let actual: String = elf
                .build_id()
                .ok()
                .flatten()?
                .iter()
                .map(|b| format!("{b:02x}"))
                .collect();
            if actual == id
                && let Some(ctx) = debug_context(&elf)
            {
                return Some(ctx);
            }
        }
    }
    None
}
fn remap_source(path: &str) -> String {
    if let Ok(value) = std::env::var("LEAKSCOPE_SOURCE_PATH_MAP")
        && value.len() <= 4096
        && let Ok(map) = serde_json::from_str::<std::collections::BTreeMap<String, String>>(&value)
    {
        for (prefix, replacement) in map.iter().take(16) {
            if let Some(tail) = path.strip_prefix(prefix) {
                return format!("{replacement}{tail}");
            }
        }
    }
    path.to_owned()
}
