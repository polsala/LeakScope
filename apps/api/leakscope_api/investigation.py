"""Evidence-backed findings and explicit repeated-operation experiments.

Phases record operator boundaries; they never invoke application code. Allocation
ownership and causality are never inferred from operation timing or RSS deltas.
"""

import math
import statistics
import time
import uuid
from typing import Literal
from fastapi import Depends, HTTPException
from pydantic import Field
from sqlalchemy import select
from . import models as m
from .config import Strict
from .context_capture import expand
from .native import diagnose, NativeAnalysisError
from .contracts import NativeFrameView


class RecommendationView(Strict):
    action: str
    reason: str
    required_capabilities: list[str]
    expected_observability: str
    expected_overhead: str
    operational_risk: str
    uncertainty: str


class HypothesisView(Strict):
    classification: str
    score: int | None
    score_kind: str
    supporting_evidence: list[str]
    contradictory_evidence: list[str]
    limitations: list[str]
    attribution_quality: str
    known_retained_bytes: int | None
    process_key: str
    operation: str | None
    source_locations: list[NativeFrameView]
    recommended_validation: RecommendationView


class OperationGroupView(Strict):
    operation: str
    thread: int
    execution_count: int
    completed: int
    failed: int
    incomplete: int
    total_duration_ms: float
    p50_duration_ms: float | None
    p95_duration_ms: float | None
    rss_delta_bytes: int | None
    rss_aggregation: str
    known_retained_bytes_per_iteration: float | None
    allocation_association: str | None = None


class OperationAggregateView(Strict):
    groups: list[OperationGroupView]
    intervals: list[dict]
    ownership_established: bool


class RetainedSiteView(Strict):
    classification: str
    known_retained_bytes: int
    allocation_count: int
    domain: str
    attribution_quality: str
    frames: list[NativeFrameView]
    stack_id: str
    session_id: str
    ownership_established: bool
    validation: str


class FindingsView(Strict):
    trend: dict
    hypothesis: HypothesisView
    recommendations: list[RecommendationView]
    session_id: str
    sites: list[RetainedSiteView]
    operations: OperationAggregateView
    gc_type_deltas: list[dict]
    quality: dict
    allocation_analysis_unavailable: str | None
    phases: list[dict]
    experiment_id: str | None


class ExperimentCreate(Strict):
    operation: str = Field(pattern=r"^[A-Za-z_][A-Za-z0-9_.: -]{0,79}$")


class PhaseCreate(Strict):
    phase: Literal["warmup", "baseline", "repetitions", "cooldown", "comparison"]


class ExternalPerformance(Strict):
    baseline_latency_ms: float = Field(gt=0, le=86400000, allow_inf_nan=False)
    observed_latency_ms: float = Field(ge=0, le=86400000, allow_inf_nan=False)
    sample_count: int = Field(ge=10, le=10000000)
    measured_interval_seconds: float = Field(ge=1, le=86400, allow_inf_nan=False)


def aggregate_operations(records, samples, operation=None, start=None, end=None):
    intervals = {}
    for record in records:
        if record["kind"] != "operation":
            continue
        op = record["payload"]
        if operation and op["operation"] != operation:
            continue
        if record.get("monotonic_ns") is None:
            continue
        item = {
            **op,
            "started_at": record["timestamp"] + (op["start_ns"] - record["monotonic_ns"]) / 1e9,
        }
        if start is not None and item["started_at"] < start:
            continue
        if op.get("end_ns") is not None:
            item["ended_at"] = record["timestamp"] + (op["end_ns"] - record["monotonic_ns"]) / 1e9
            if end is not None and item["ended_at"] > end:
                continue
            item["duration_ms"] = (op["end_ns"] - op["start_ns"]) / 1e6
            if samples:
                a = min(samples, key=lambda s: abs(s["timestamp"] - item["started_at"]))
                b = min(samples, key=lambda s: abs(s["timestamp"] - item["ended_at"]))
                item["rss_delta_bytes"] = b["rss"] - a["rss"]
                item["rss_sampling_distance_seconds"] = max(
                    abs(a["timestamp"] - item["started_at"]), abs(b["timestamp"] - item["ended_at"])
                )
                item["rss_evidence"] = "nearest_process_samples; temporal_association_not_ownership"
        intervals[op["id"]] = item
    groups: dict[tuple[str, int], list[dict]] = {}
    for op in intervals.values():
        key = (op["operation"], op["thread"])
        groups.setdefault(key, []).append(op)
    summaries = []
    for (name, thread), ops in groups.items():
        durations = sorted(o["duration_ms"] for o in ops if "duration_ms" in o)
        completed = sum(o["status"] == "completed" for o in ops)
        summaries.append(
            {
                "operation": name,
                "thread": thread,
                "execution_count": len(durations),
                "completed": completed,
                "failed": sum(o["status"] in {"error", "cancelled"} for o in ops),
                "incomplete": sum("duration_ms" not in o for o in ops),
                "total_duration_ms": sum(durations),
                "p50_duration_ms": statistics.median(durations) if durations else None,
                "p95_duration_ms": durations[math.ceil(0.95 * len(durations)) - 1]
                if durations
                else None,
                "rss_delta_bytes": sum(o.get("rss_delta_bytes", 0) for o in ops)
                if samples
                else None,
                "rss_aggregation": "nearest_samples; overlapping_operations_can_overlap_memory; not_additive",
                "known_retained_bytes_per_iteration": None,
            }
        )
    return {
        "groups": summaries,
        "intervals": list(intervals.values()),
        "ownership_established": False,
    }


class Findings:
    def __init__(self, collector, native_result):
        self.collector, self.native_result = collector, native_result

    def get(self, sid, experiment=None):
        with self.collector.db() as db:
            session = db.get(m.Session, sid)
            if session is None:
                raise HTTPException(404, "Session not found")
            records = [
                r.data
                for r in db.scalars(
                    select(m.AgentRecord)
                    .where(m.AgentRecord.session_id == sid)
                    .order_by(m.AgentRecord.agent_sequence)
                    .limit(2048)
                )
            ]
            snapshots = list(
                db.scalars(
                    select(m.GCTypeSnapshot)
                    .where(m.GCTypeSnapshot.session_id == sid)
                    .order_by(m.GCTypeSnapshot.timestamp)
                    .limit(100)
                )
            )
        phases = {p["phase"]: p["timestamp"] for p in experiment.phases} if experiment else {}
        baseline = phases.get("baseline")
        end = phases.get("comparison")
        samples = self.collector.samples(sid, baseline, end, limit=4096)
        operations = aggregate_operations(
            records, samples, experiment.operation if experiment else None, baseline, end
        )
        evidence = {
            "domain": "os_process",
            "process_key": session.process_key,
            "exact_survivors": False,
            "lost_events": session.quality.get("lost_events", 0)
            + session.quality.get("lost_native", 0),
            "attribution_quality": "metrics_only",
            "capture_gaps": bool(session.quality.get("capture_gaps")),
            "repeated_operations": sum(g["completed"] for g in operations["groups"]),
            # A manual boundary is not evidence of continued allocation coverage.
            # Enable this only after checking the actual trace end below.
            "survived_cooldown": False,
            "operation": experiment.operation if experiment else None,
        }
        sites = []
        analysis = None
        unavailable = None
        if session.quality.get("coverage") in {"native_observed", "lab_observed"}:
            domain = "python_block" if session.config.get("mode") == "lab" else "native"
            attribution = (
                "python_exact_lines"
                if domain == "python_block"
                else (
                    "python_functions"
                    if session.quality.get("python_context")
                    and not session.quality.get("context_incomplete")
                    else "native"
                )
            )
            try:
                analysis = self.native_result(
                    sid, domain=domain, attribution=attribution, start=baseline, end=end
                )
                if analysis["exact_survivors"]:
                    evidence["known_live_bytes"] = analysis["retained_tree"]["value"]
                evidence.update(
                    domain=domain,
                    exact_survivors=analysis["exact_survivors"],
                    attribution_quality=analysis["quality"].get("attribution", "unknown"),
                    lost_events=analysis["lost_events"],
                    capture_gaps=analysis["quality"].get("capture_gaps", False),
                )
                if (
                    end
                    and phases.get("cooldown")
                    and end - phases["cooldown"] >= 60
                    and session.state in {"ready", "degraded"}
                    and analysis["exact_survivors"]
                ):
                    observed_end = (
                        session.quality.get("capture_window", {}).get("detached_at", 0) or 0
                    )
                    if domain == "python_block":
                        observed_end = max(
                            (
                                r["event"]["timestamp"]
                                for r in expand(records, session.process_key, session.created_at)
                                if r.get("kind") == "allocation"
                            ),
                            default=0,
                        )
                    evidence["survived_cooldown"] = observed_end >= end
                for site in sorted(
                    analysis["top_sites"],
                    key=lambda s: s.get("known_live_bytes") or 0,
                    reverse=True,
                )[:20]:
                    if not site.get("known_live_bytes"):
                        continue
                    frames = site.get("frames") or []
                    sites.append(
                        {
                            "classification": "observed_retained_site",
                            "known_retained_bytes": site["known_live_bytes"],
                            "allocation_count": site["allocation_count"],
                            "domain": domain,
                            "attribution_quality": evidence["attribution_quality"],
                            "frames": frames,
                            "stack_id": site["stack_id"],
                            "session_id": sid,
                            "ownership_established": False,
                            "validation": "Repeat with a matched cleanup/control and an observed cooldown. A surviving allocation alone is not proof of a leak.",
                        }
                    )
                evidence["source_locations"] = [f for site in sites[:5] for f in site["frames"][:4]]
            except (HTTPException, NativeAnalysisError) as error:
                unavailable = str(error)[:500]
        snapshots = [
            s
            for s in snapshots
            if (baseline is None or s.timestamp >= baseline) and (end is None or s.timestamp <= end)
        ]
        gc_deltas = []
        if len(snapshots) >= 2:
            a, b = snapshots[0].snapshot, snapshots[-1].snapshot
            for name in sorted(set(a["types"]) | set(b["types"])):
                av, bv = a["types"].get(name, {}), b["types"].get(name, {})
                gc_deltas.append(
                    {
                        "type": name,
                        "count_delta": bv.get("count", 0) - av.get("count", 0),
                        "shallow_bytes_delta": bv.get("shallow_bytes_estimate", 0)
                        - av.get("shallow_bytes_estimate", 0),
                        "partial": a["partial"] or b["partial"],
                        "visibility": a["visibility"],
                    }
                )
            evidence["gc_count_delta"] = sum(row["count_delta"] for row in gc_deltas)
            evidence["gc_visibility"] = a["visibility"]
        thresholds = self.collector.config.detection.model_dump(exclude={"enabled"})
        try:
            result = diagnose(
                [{k: s[k] for k in ("timestamp", "rss")} for s in samples], thresholds, evidence
            )
        except NativeAnalysisError as error:
            raise HTTPException(409, str(error)) from error
        result.update(
            session_id=sid,
            sites=sites,
            operations=operations,
            gc_type_deltas=gc_deltas,
            quality=session.quality,
            allocation_analysis_unavailable=unavailable,
            phases=experiment.phases if experiment else [],
            experiment_id=experiment.id if experiment else None,
        )
        if analysis and analysis["exact_survivors"]:
            by_id = {o["id"]: o for o in analysis["operations"]}
            for group in operations["groups"]:
                matches = [
                    o
                    for o in operations["intervals"]
                    if o["operation"] == group["operation"] and o["thread"] == group["thread"]
                ]
                observed = [
                    by_id[o["id"]].get("known_live_bytes") for o in matches if o["id"] in by_id
                ]
                if (
                    len(observed) == len(matches)
                    and observed
                    and all(v is not None for v in observed)
                ):
                    group["known_retained_bytes_per_iteration"] = sum(observed) / len(observed)
                    group["allocation_association"] = (
                        "deepest_completed_interval_only; temporal_not_ownership"
                    )
        return result


def install_routes(app, findings, read, analyst, operator):
    collector = findings.collector

    def experiment(identifier):
        with collector.db() as db:
            row = db.get(m.Experiment, identifier)
            if row is None:
                raise HTTPException(404, "Experiment not found")
            return row

    @app.get(
        "/api/v1/sessions/{sid}/findings", dependencies=[Depends(read)], response_model=FindingsView
    )
    def get(sid: str):
        return findings.get(sid)

    @app.get("/api/v1/sessions/{sid}/performance", dependencies=[Depends(read)])
    def performance(sid: str):
        with collector.db() as db:
            row = db.get(m.Session, sid)
            if row is None:
                raise HTTPException(404, "Session not found")
        q = row.quality
        return {
            "session_id": sid,
            "controller": q.get("controller", {}),
            "capture_window": q.get("capture_window"),
            "policy_transitions": q.get("policy_transitions", []),
            "measured_causal_target_overhead_percent": None,
            "uncertainty": "Prior CPU observations and externally supplied latency are not a counterfactual baseline. Controlled A/B/A benchmarks are required.",
            "lost_events": q.get("lost_events", 0) + q.get("lost_native", 0),
            "effective_policy": q.get("effective_policy", "metrics"),
            "external_measurement": q.get("external_performance"),
            "budgets": {
                **collector.config.overhead.model_dump(),
                "target_cpu_increase_percent": row.config["cpu_overhead_target"],
            },
            "capture_limits": {
                "max_capture_mb": row.config["max_capture_mb"],
                "max_sensor_rss_mb": row.config["max_sensor_rss_mb"],
            },
        }

    @app.post("/api/v1/sessions/{sid}/performance")
    def supplied(sid: str, body: ExternalPerformance, role=Depends(operator)):
        with collector.db.begin() as db:
            row = db.get(m.Session, sid)
            if row is None:
                raise HTTPException(404, "Session not found")
            if row.state != "recording":
                raise HTTPException(409, "External performance input requires a recording session")
            row.quality = {
                **row.quality,
                "external_performance": {
                    **body.model_dump(),
                    "received_at": time.time(),
                    "source": "operator_supplied_not_independently_verified",
                },
                "external_latency_increase_percent": 100
                * (body.observed_latency_ms / body.baseline_latency_ms - 1),
            }
        collector.audit(role, "performance.supply", sid)
        return {"accepted": True, "source": "operator_supplied_not_independently_verified"}

    @app.post("/api/v1/sessions/{sid}/experiments", status_code=201)
    def create(sid: str, body: ExperimentCreate, role=Depends(analyst)):
        with collector.db.begin() as db:
            session = db.get(m.Session, sid)
            if session is None:
                raise HTTPException(404, "Session not found")
            existing = list(
                db.scalars(select(m.Experiment).where(m.Experiment.session_id == sid).limit(11))
            )
            if len(existing) >= 10:
                raise HTTPException(409, "Experiment limit reached")
            row = m.Experiment(
                id=uuid.uuid4().hex,
                session_id=sid,
                operation=body.operation,
                created_at=time.time(),
                phases=[],
            )
            db.add(row)
        collector.audit(role, "experiment.create", row.id)
        return {"id": row.id, "session_id": sid, "operation": body.operation, "phases": []}

    @app.get("/api/v1/sessions/{sid}/experiments", dependencies=[Depends(read)])
    def experiments(sid: str):
        with collector.db() as db:
            if db.get(m.Session, sid) is None:
                raise HTTPException(404, "Session not found")
            return {
                "items": [
                    {"id": r.id, "session_id": sid, "operation": r.operation, "phases": r.phases}
                    for r in db.scalars(
                        select(m.Experiment)
                        .where(m.Experiment.session_id == sid)
                        .order_by(m.Experiment.created_at)
                        .limit(10)
                    )
                ]
            }

    @app.post("/api/v1/experiments/{identifier}/phases")
    def phase(identifier: str, body: PhaseCreate, role=Depends(analyst)):
        row = experiment(identifier)
        with collector.db() as db:
            if db.get(m.Session, row.session_id).state != "recording":
                raise HTTPException(
                    409,
                    "Record experiment boundaries while the session is recording; an ended trace cannot establish later survival",
                )
        order = ["warmup", "baseline", "repetitions", "cooldown", "comparison"]
        if row.phases and order.index(body.phase) <= order.index(row.phases[-1]["phase"]):
            if body.phase == row.phases[-1]["phase"]:
                return {"phases": row.phases}
            raise HTTPException(409, "Experiment phases must advance in order")
        recorded = {p["phase"] for p in row.phases}
        if body.phase in {"repetitions", "cooldown", "comparison"} and "baseline" not in recorded:
            raise HTTPException(409, "Record baseline before repetitions or comparison")
        if body.phase == "comparison" and "cooldown" not in recorded:
            raise HTTPException(409, "Record the cooldown boundary before comparison")
        with collector.db.begin() as db:
            current = db.get(m.Experiment, identifier)
            current.phases = row.phases + [{"phase": body.phase, "timestamp": time.time()}]
        collector.audit(role, "experiment.phase." + body.phase, identifier)
        return {"phases": current.phases, "execution": "manual_application_workflow_only"}

    @app.get(
        "/api/v1/experiments/{identifier}",
        dependencies=[Depends(read)],
        response_model=FindingsView,
    )
    def results(identifier: str):
        row = experiment(identifier)
        return findings.get(row.session_id, row)
