# Independent native capture windows

A monitor stores process metrics in SQLite. Each manual or explicitly authorized
automatic native window creates an ordinary session through the existing
collector, Aya loader, LSCAP writer and analyzer. It owns fresh maps and links;
there is no permanently attached inactive allocation probe between windows.

Metadata records activation epoch, attachment duration, monotonic arm/stop
bounds, physical link-close time and detachment duration. Userspace bounds are
not infinitely precise kernel timestamps. Half-attached allocator pairs are
suppressed. In-flight calls at stop invalidate exact survivor accounting.

On completion, `Trace` is drained with a bounded effort and dropped, closing all
owned links. Kernel tests check the sensor's actual perf/BPF link descriptors
reach zero. Monitoring persists after a window; process replacement stops the
monitor rather than transferring pointer state to a new worker.

Every window reconstructs only observed lifetimes in its own process/domain.
Pre-attach blocks are unknown. An allocation retained at the end of window A may
have been freed before B. The UI labels windows independent and the API always
returns `cross_window_exact_survivors: false`. Gap records inside imported or
interrupted captures also invalidate whole-capture precision. Native and Python
allocator blocks are never added together.

Default automatic capture is disabled. An operator must both enable host policy
and request `automatic_policy: native_light` on the monitor. Automatic windows
default to at most 15 seconds, are separated by a cooldown and stop after a
configured window-count budget. Native Detailed remains a deliberate manual
choice. Reducing duty cycle reduces exposure; it does not make active uprobes
cheap or give continuous allocation coverage.

