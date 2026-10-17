import argparse
import json
import os
import platform
import shutil
import sqlite3
import subprocess
import sys
import time
import re
from pathlib import Path
import httpx
from . import __version__
from .analysis import summarize, compare
from .capture import Reader, integrity, CaptureError
from .config import load_config, credential, private_directory
from .storage import service_lease
from .reports import render


def security_policy():
    try:
        return Path("/proc/self/attr/current").read_text().strip()
    except OSError:
        return "not_observable"


def duration(value):
    multiplier = {"s": 1, "m": 60, "h": 3600}
    try:
        result = int(value[:-1]) * multiplier[value[-1]] if value[-1] in multiplier else int(value)
    except (ValueError, IndexError):
        raise argparse.ArgumentTypeError("Use seconds or a duration such as 5m")
    if not 1 <= result <= 600:
        raise argparse.ArgumentTypeError("Duration must be between 1 and 600 seconds")
    return result


def observation_duration(value):
    try:
        unit = {"s": 1, "m": 60, "h": 3600, "d": 86400}
        result = int(value[:-1]) * unit[value[-1]] if value[-1] in unit else int(value)
        if not 1 <= result <= 2592000:
            raise ValueError()
        return result
    except (ValueError, IndexError):
        raise argparse.ArgumentTypeError("Use a bounded observation duration, up to 30d")


def session_reference(path):
    return bool(re.fullmatch("[a-f0-9]{32}", str(path))) and not path.exists()


def read_capture(path):
    reader = Reader(Path(path))
    samples = []
    recorded_quality = reader.metadata.get("quality", {})
    for chunk in reader.chunks():
        for event in chunk:
            if event.get("kind") == "quality":
                recorded_quality = event["quality"]
            if event.get("kind") == "metric":
                samples.append(event["sample"])
        if len(samples) > 100000:
            # Analysis stays bounded even when the streaming parser supports larger files.
            samples = samples[::2]
    quality = {
        **recorded_quality,
        "incomplete": bool(recorded_quality.get("incomplete"))
        or reader.recovered
        or reader.missing_sequences > 0,
        "lost_samples": max(recorded_quality.get("lost_samples", 0), reader.missing_sequences),
    }
    return samples, quality, reader.metadata


def main():
    parser = argparse.ArgumentParser(
        prog="leakscope", description="Local memory investigation with explicit evidence quality"
    )
    parser.add_argument("--version", action="version", version="LeakScope " + __version__)
    parser.add_argument("--url", default=os.getenv("LEAKSCOPE_URL", "http://127.0.0.1:7831"))
    commands = parser.add_subparsers(dest="command", required=True)
    for name in [
        "backup",
        "restore",
        "doctor",
        "hosts",
        "sessions",
        "ps",
        "inspect",
        "capture",
        "stop",
        "serve",
        "analyze",
        "compare",
        "report",
        "export",
        "import",
        "create-token",
        "monitor",
        "watch",
        "investigate",
        "findings",
        "performance",
        "release-readiness",
    ]:
        command = commands.add_parser(name)
        command.add_argument("--json", action="store_true")
        if name in {"inspect", "capture", "monitor", "watch", "investigate"}:
            command.add_argument("--pid", required=True, type=int)
        if name in {"capture", "investigate"}:
            command.add_argument("--mode", choices=["observe", "deep", "lab"], default="observe")
            command.add_argument(
                "--duration", type=duration, default=15 if name == "investigate" else 60
            )
            command.add_argument(
                "--policy",
                choices=["metrics", "native_light", "native_detailed", "python_deep", "lab_full"],
                default="native_light" if name == "investigate" else None,
            )
            command.add_argument("--min-allocation-size", type=int, default=65536)
            command.add_argument(
                "--native-stacks", choices=["none", "caller", "full"], default="full"
            )
            command.add_argument(
                "--native",
                action="store_true",
                help="Request real native allocator probes; fail if unsupported",
            )
            command.add_argument("--output", type=Path)
        if name in {"monitor", "watch"}:
            command.add_argument("--duration", type=observation_duration, default=86400)
            command.add_argument("--interval", type=float, default=5)
            command.add_argument("--growth-mb", type=float, default=50)
            command.add_argument("--window", type=observation_duration, default=900)
            command.add_argument("--auto-policy", choices=["native_light"])
            command.add_argument("--capture-duration", type=duration, default=5)
        if name == "ps":
            command.add_argument("--tree", action="store_true")
        if name in {"backup", "restore"}:
            command.add_argument("path", type=Path)
        if name == "serve":
            command.add_argument(
                "--external-sensor",
                action="store_true",
                help="Require a separately managed sensor; never spawn one",
            )
            command.add_argument("--listen", default="127.0.0.1:7831")
        if name in {"stop", "export", "findings", "performance"}:
            command.add_argument("session_id")
        if name == "stop":
            command.add_argument(
                "--monitor",
                action="store_true",
                help="Stop durable observation instead of a capture",
            )
        if name == "export":
            command.add_argument("--format", choices=["json", "lscap"], default="json")
            command.add_argument("--output", type=Path)
        if name in {"analyze", "report"}:
            command.add_argument(
                "--attribution",
                choices=["native", "python_functions", "python_exact_lines", "operations"],
                default="native",
            )
            command.add_argument("--domain", choices=["native", "python_block"])
        if name in {"analyze", "report", "import"}:
            command.add_argument("path", type=Path)
        if name == "compare":
            command.add_argument("before", type=Path)
            command.add_argument("after", type=Path)
        if name == "report":
            command.add_argument("--output", type=Path, required=True)
        if name == "create-token":
            command.add_argument(
                "--role", required=True, choices=["viewer", "analyst", "operator", "admin"]
            )
            command.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "investigate":
        args.command = "capture"
    cfg = load_config()
    data = Path(cfg.data_path).resolve()
    try:
        if args.command in {"backup", "restore"}:
            from .storage import backup, restore

            database_path = data / "leakscope.sqlite3"
            result = (
                backup(database_path, args.path)
                if args.command == "backup"
                else restore(args.path, database_path)
            )
            print(json.dumps(result, indent=2))
            return
        if args.command == "serve":
            if os.getuid() == 0 or os.geteuid() == 0:
                raise RuntimeError(
                    "The API must run under an unprivileged service UID. Install as administrator, then run serve as the monitored application UID; grant tracing privileges only to the separate sensor."
                )
            import uvicorn
            from .app import create_app

            host, port = args.listen.rsplit(":", 1)
            if host not in {"127.0.0.1", "localhost", "::1"}:
                parser.error(
                    "Standalone server binds to loopback. Use an SSH tunnel for remote access."
                )
            cfg.listen = args.listen
            private_directory(data)
            # Retain exclusion until the server's executor threads have also
            # stopped, beyond ASGI lifespan teardown and capture cancellation.
            with service_lease(data):
                app = create_app(cfg, start_sensor=not args.external_sensor)
                print(
                    f"LeakScope: http://{args.listen}\nRead your local credential from {data / 'admin.token'}",
                    file=sys.stderr,
                )
                uvicorn.run(
                    app, host=host, port=int(port), access_log=False, timeout_graceful_shutdown=3
                )
            return
        if args.command == "create-token":
            import hashlib
            import uuid
            from .app import create_app
            from .models import User

            app = create_app(cfg, start_sensor=False)
            new_token = credential(args.output)
            with app.state.db.begin() as db:
                db.add(
                    User(
                        id=uuid.uuid4().hex,
                        role=args.role,
                        token_hash=hashlib.sha256(new_token.encode()).hexdigest(),
                        enabled=True,
                    )
                )
            print(json.dumps({"role": args.role, "credential_file": str(args.output)}))
            return
        online_compare = (
            args.command == "compare"
            and session_reference(args.before)
            and session_reference(args.after)
        )
        online_report = args.command == "report" and session_reference(args.path)
        if args.command in {"analyze", "compare", "report"} and not (
            online_compare or online_report
        ):
            if args.command == "compare":
                a, aq, _ = read_capture(args.before)
                b, bq, _ = read_capture(args.after)
                result = compare(a, b, aq, bq)
            else:
                samples, quality, metadata = read_capture(args.path)
                result = {
                    "summary": summarize(samples, quality),
                    "quality": quality,
                    "integrity": integrity(args.path),
                }
                if quality.get("coverage") in {"native_observed", "lab_observed"}:
                    from .native import analyze

                    domain = args.domain or (
                        "python_block"
                        if metadata.get("config", {}).get("mode") == "lab"
                        else "native"
                    )
                    result["native"] = analyze(
                        args.path, domain=domain, attribution=args.attribution
                    )
                if args.command == "report":
                    document = {
                        "title": "Memory investigation",
                        "version": __version__,
                        "summary": result["summary"],
                        "quality": quality,
                        "timeline": samples,
                        "integrity": result["integrity"],
                        "mode": metadata.get("config", {}).get("mode"),
                    }
                    if "native" in result:
                        document["native"] = result["native"]
                    args.output.write_text(render(document))
                    result = {"report": str(args.output), **result}
            print(json.dumps(result, indent=2))
            return
        token = os.getenv("LEAKSCOPE_TOKEN")
        if token is None and (data / "admin.token").exists():
            token = (data / "admin.token").read_text().strip()
        headers = {"Authorization": "Bearer " + token} if token else {}
        with httpx.Client(base_url=args.url + "/api/v1", headers=headers, timeout=15) as client:

            def call(method, endpoint, **kw):
                response = client.request(method, endpoint, **kw)
                if response.is_error:
                    raise RuntimeError(response.text)
                return response.json()

            if args.command == "doctor":
                result = {
                    "platform": platform.platform(),
                    "architecture": platform.machine(),
                    "python": sys.version.split()[0],
                    "python27_path": shutil.which("python2.7"),
                    "process_uid": os.getuid(),
                    "pid_namespace": os.readlink("/proc/self/ns/pid"),
                    "security_policy": security_policy(),
                    "release_readiness": __import__(
                        "leakscope_api.readiness", fromlist=["evaluate"]
                    ).evaluate(),
                    "free_storage_bytes": shutil.disk_usage(
                        data if data.exists() else Path.cwd()
                    ).free,
                    "remediation": "Metrics-only Observe requires same UID and readable procfs. Cooperative agent must be initialized by the application; no injection is attempted.",
                }
                if (data / "leakscope.sqlite3").exists():
                    from .storage import check

                    try:
                        result["sqlite"] = check(data / "leakscope.sqlite3")
                    except (sqlite3.Error, RuntimeError) as error:
                        result["sqlite"] = {
                            "status": "unavailable",
                            "reason": type(error).__name__,
                            "remediation": "Stop services, preserve main/WAL/SHM files and restore a verified backup.",
                        }
                binary = shutil.which("leakscope-sensor") or str(
                    Path(__file__).resolve().parents[3] / "target/debug/leakscope-sensor"
                )
                if Path(binary).exists():
                    result["native_sensor"] = json.loads(
                        subprocess.check_output([binary, "--doctor"], timeout=10)
                    )
                try:
                    result["collector"] = call("GET", "/health/ready")
                    result["deployment"] = call("GET", "/deployment/health")
                    result["host"] = call("GET", "/capabilities")
                except (httpx.HTTPError, RuntimeError) as error:
                    result["collector"] = {
                        "status": "unavailable",
                        "reason": str(error),
                        "remediation": "Run leakscope serve and provide the local API token.",
                    }
            elif args.command in {"hosts", "sessions"}:
                result = call("GET", "/" + args.command)
            elif args.command in {"findings", "performance"}:
                result = call("GET", f"/sessions/{args.session_id}/{args.command}")
            elif args.command == "release-readiness":
                result = call("GET", "/release/readiness")
            elif online_compare:
                result = call(
                    "POST",
                    "/comparisons",
                    json={
                        "a": {"session_id": str(args.before)},
                        "b": {"session_id": str(args.after)},
                    },
                )
            elif online_report:
                result = call(
                    "POST",
                    "/reports",
                    json={"session_id": str(args.path), "title": "Memory investigation"},
                )
                download = client.get("/reports/" + result["id"] + "/download")
                download.raise_for_status()
                args.output.write_bytes(download.content)
                result = {"id": result["id"], "output": str(args.output)}
            elif args.command in {"ps", "inspect", "capture", "monitor", "watch"}:
                hosts = call("GET", "/hosts")["items"]
                processes = []
                for host in hosts:
                    if not host.get("imported"):
                        processes.extend(
                            call("GET", f"/hosts/{host['id']}/processes?limit=2000")["items"]
                        )
                if args.command == "ps":
                    result = {"items": processes}
                    if args.tree and not args.json:
                        ids = {p["pid"] for p in processes}

                        def branch(parent, depth=0):
                            for p in processes:
                                if p["ppid"] == parent:
                                    print(
                                        "  " * depth
                                        + f"{p['pid']} {p['name']} RSS={p['sample']['rss']}"
                                    )
                                    branch(p["pid"], depth + 1)

                        for p in processes:
                            if p["ppid"] not in ids:
                                print(f"{p['pid']} {p['name']}")
                                branch(p["pid"], 1)
                        return
                else:
                    process = next((p for p in processes if p["pid"] == args.pid), None)
                    if not process:
                        raise RuntimeError("PID is unavailable under the sensor UID policy")
                    if args.command == "inspect":
                        result = {
                            "process": process,
                            "capabilities": call(
                                "GET", f"/processes/{process['key']}/capabilities"
                            ),
                        }
                    elif args.command in {"monitor", "watch"}:
                        from .config import Detection

                        detection = Detection(
                            minimum_observation_seconds=args.window,
                            window_seconds=max(0.1, args.window / 3),
                            minimum_growth_bytes=int(args.growth_mb * 1024**2),
                        )
                        result = call(
                            "POST",
                            "/monitors",
                            json={
                                "process_key": process["key"],
                                "interval_seconds": args.interval,
                                "duration_seconds": args.duration,
                                "detection": detection.model_dump(),
                                "automatic_policy": args.auto_policy,
                                "capture_seconds": args.capture_duration,
                            },
                        )
                    else:
                        result = call(
                            "POST",
                            "/sessions",
                            json={
                                "process_key": process["key"],
                                "mode": args.mode,
                                "duration_seconds": args.duration,
                                "allocation_domains": ["os_process", "native"]
                                if args.native
                                else ["os_process"],
                                "allow_downgrade": not (
                                    args.native
                                    or args.policy
                                    in {
                                        "native_light",
                                        "native_detailed",
                                        "python_deep",
                                        "lab_full",
                                    }
                                ),
                                "profiling_policy": args.policy,
                                "min_allocation_size": args.min_allocation_size,
                                "native_stacks": args.native_stacks,
                            },
                        )
                        session_id = result["id"]
                        print("Session " + session_id, file=sys.stderr)
                        while result["state"] not in {
                            "ready",
                            "degraded",
                            "failed",
                            "cancelled",
                            "expired",
                        }:
                            time.sleep(0.5)
                            result = call("GET", "/sessions/" + session_id)
                        if result["state"] == "failed":
                            raise RuntimeError(result.get("reason", "Native capture failed"))
                        if args.output:
                            response = client.get(f"/sessions/{session_id}/export")
                            response.raise_for_status()
                            args.output.write_bytes(response.content)
            elif args.command == "stop":
                resource = "monitors" if args.monitor else "sessions"
                result = call("POST", f"/{resource}/{args.session_id}/stop")
            elif args.command == "export":
                response = client.get(
                    f"/sessions/{args.session_id}/export", params={"format": args.format}
                )
                response.raise_for_status()
                if args.output:
                    args.output.write_bytes(response.content)
                    result = {"output": str(args.output)}
                elif args.format == "lscap":
                    sys.stdout.buffer.write(response.content)
                    return
                else:
                    result = response.json()
            elif args.command == "import":
                with args.path.open("rb") as capture:
                    result = call(
                        "POST",
                        "/captures/import",
                        content=capture,
                        headers={"Content-Type": "application/octet-stream"},
                    )
            else:
                raise RuntimeError("Unsupported command")
            print(json.dumps(result, indent=2))
    except (
        OSError,
        RuntimeError,
        sqlite3.Error,
        httpx.HTTPError,
        CaptureError,
        ValueError,
    ) as error:
        print(json.dumps({"error": str(error)}), file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
