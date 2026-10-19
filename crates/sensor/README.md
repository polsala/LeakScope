# leakscope-sensor

Bounded same-UID Linux process monitoring and opt-in native tracing through Aya.
Includes the `leakscope-sensor` executable and its BPF sources. Building
requires Linux x86_64 and Clang with the BPF target. Native tracing permissions
are provisioned separately; metrics do not require BPF privileges.

Part of [LeakScope](https://github.com/polsala/LeakScope), an engineering
preview. Build with Rust 1.94 or newer. See the project documentation for
compatibility and accounting constraints.
