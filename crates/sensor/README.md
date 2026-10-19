# leakscope-sensor

Bounded Linux process sensor with opt-in native allocation tracing.

Part of [LeakScope](https://github.com/polsala/LeakScope). Engineering preview.
Memory domains overlap and must not be added. Incomplete traces do not establish exact survivors.

Build with Rust 1.94 or newer. The sensor additionally requires Linux x86_64 and Clang with the BPF target. Metrics do not require tracing privileges; native probes require explicit authorization.
