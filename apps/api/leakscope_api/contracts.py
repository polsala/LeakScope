from typing import Literal
from pydantic import Field, model_validator
from .config import Strict

SessionState = Literal[
    "created",
    "preflight",
    "starting",
    "recording",
    "stopping",
    "processing",
    "ready",
    "degraded",
    "failed",
    "cancelled",
    "expired",
]
TRANSITIONS = {
    "created": {"preflight", "cancelled", "failed"},
    "preflight": {"starting", "failed", "cancelled"},
    "starting": {"recording", "failed", "degraded", "stopping"},
    "recording": {"stopping", "degraded", "failed"},
    "stopping": {"processing", "failed"},
    "processing": {"ready", "degraded", "failed", "expired"},
    "degraded": {"stopping", "processing", "failed"},
    "ready": set(),
    "failed": set(),
    "cancelled": set(),
    "expired": set(),
}


def transition(session, state: str) -> None:
    if session.state == state:
        return
    if state not in TRANSITIONS.get(session.state, set()):
        raise ValueError(f"Invalid session transition {session.state} -> {state}")
    session.state = state


class SessionCreate(Strict):
    process_key: str = Field(pattern=r"^[0-9a-f]{64}$")
    mode: Literal["observe", "deep", "lab"] = "observe"
    duration_seconds: int = Field(60, ge=1, le=600)
    sample_interval_ms: int = Field(1000, ge=100, le=60000)
    max_capture_mb: int = Field(50, ge=1, le=500)
    event_rate_limit: int = Field(100000, ge=100, le=1000000)
    cpu_overhead_target: float = Field(1, ge=0.1, le=10)
    max_sensor_rss_mb: int = Field(128, ge=32, le=128)
    allocation_domains: list[
        Literal["os_process", "native", "python_block", "python_arena", "gc_objects"]
    ] = ["os_process"]
    allow_downgrade: bool = True
    purpose: str = Field("growth", pattern=r"^[a-z_]{1,40}$")


class MarkerCreate(Strict):
    name: str = Field(min_length=1, max_length=80, pattern=r"^[\w .:-]+$")
    operation: str | None = Field(None, pattern=r"^[A-Za-z_][A-Za-z0-9_.:]{0,79}$")


class InvestigationCreate(Strict):
    title: str = Field(min_length=1, max_length=160)
    session_id: str = Field(pattern=r"^[a-f0-9]{32}$")
    notes: str = Field("", max_length=10000)


class InvestigationPatch(Strict):
    title: str | None = Field(None, min_length=1, max_length=160)
    notes: str | None = Field(None, max_length=10000)


class Interval(Strict):
    session_id: str = Field(pattern=r"^[a-f0-9]{32}$")
    start: float | None = Field(None, ge=0, allow_inf_nan=False)
    end: float | None = Field(None, ge=0, allow_inf_nan=False)

    @model_validator(mode="after")
    def ordered(self):
        if self.start is not None and self.end is not None and self.end <= self.start:
            raise ValueError("Interval end must follow start")
        return self


class ComparisonCreate(Strict):
    a: Interval
    b: Interval


class ReportCreate(Strict):
    session_id: str = Field(pattern=r"^[a-f0-9]{32}$")
    title: str = Field("Memory investigation", min_length=1, max_length=160)
    reproduction_steps: str = Field("", max_length=10000)
    redact: bool = True


class SessionView(Strict):
    id: str
    process_key: str
    state: SessionState
    created_at: float
    ended_at: float | None
    config: dict
    quality: dict
    reason: str
    last_sequence: int


class SampleView(Strict):
    timestamp: float
    rss: int
    pss: int | None = None
    private_bytes: int | None = None
    anonymous: int
    virtual_bytes: int
    swap: int
    threads: int
    cpu_ticks: int
    minor_faults: int
    major_faults: int


class IdentityView(Strict):
    host: str
    boot: str
    namespace: str
    pid: int
    start_ticks: int


class ProcessView(Strict):
    key: str
    identity: IdentityView
    pid: int
    ppid: int
    uid: int
    executable: str
    name: str
    python_version: str | None
    worker_type: str
    sample: SampleView


class ProcessPage(Strict):
    items: list[ProcessView]
    next_cursor: int | None


class NativeFrameView(Strict):
    address: str | None = None
    module: str
    function: str
    file: str | None = None
    line: int | None = None
    build_id: str | None = None


class NativeTreeView(Strict):
    name: str
    value: int
    count: int
    children: dict[str, "NativeTreeView"]


class NativeSiteView(Strict):
    stack_id: str
    allocated_bytes: int
    allocation_count: int
    observed_live_bytes: int
    known_live_bytes: int | None
    active_count: int
    frames: list[NativeFrameView] | None


class NativeAnalysisView(Strict):
    allocated_bytes: int
    freed_bytes: int
    allocation_count: int
    free_count: int
    selected_allocated_bytes: int
    selected_allocation_count: int
    known_live_by_domain: dict[str, int] | None
    observed_live_by_domain: dict[str, int]
    exact_survivors: bool
    incomplete: bool
    unknown_pre_capture_frees: int
    lost_events: int
    quality: dict
    allocation_tree: NativeTreeView
    retained_tree: NativeTreeView
    top_sites: list[NativeSiteView]
    cohorts: list[dict]
    limitations: list[str]
