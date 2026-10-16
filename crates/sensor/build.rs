use std::{env, path::PathBuf, process::Command};
fn main() {
    println!("cargo:rerun-if-changed=../../bpf/probes/allocations.bpf.c");
    println!("cargo:rerun-if-changed=../../bpf/include/leakscope.h");
    println!("cargo:rerun-if-env-changed=BPF_CLANG");
    let output = PathBuf::from(env::var_os("OUT_DIR").unwrap()).join("allocations.bpf.o");
    let status = Command::new(env::var("BPF_CLANG").unwrap_or_else(|_| "clang".into()))
        .args([
            "-target",
            "bpf",
            "-O2",
            "-g",
            "-Wall",
            "-Werror",
            "-I../../bpf/include",
            "-c",
            "../../bpf/probes/allocations.bpf.c",
            "-o",
        ])
        .arg(output)
        .status()
        .expect("clang with BPF target is required to build the sensor");
    assert!(status.success(), "BPF compilation failed");
}
