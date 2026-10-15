# Recovery

Keep the private database and capture manifests. Startup migrates metadata and
reconciles unfinished sessions. A stopped/restarted sensor cannot recreate lost
allocation history; metrics are finalized with incomplete coverage when its
lease is unavailable. Never merge replacement PID state with prior allocations.

The streaming capture reader recovers preceding intact chunks after an interrupted
last write and explicitly marks recovery. Checksum corruption is rejected. Use
`leakscope analyze FILE` on a copy and inspect quality before importing. Finalized
file integrity can be checked with its SHA256 manifest. Unknown format versions
must be read by an explicitly compatible release, not bypassed by editing magic.
