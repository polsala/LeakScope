"""Translate bounded cooperative records into the existing capture event model.

Shared by finalization and live analysis. Raw allocation records have the same
shape and lifecycle semantics in both paths; no Python object contents are read.
"""


def expand(items, process_key, created_at):
    for item in items:
        kind = item["kind"]
        if kind in {"lab_stack", "lab_stacks"}:
            payload = item["payload"]
            stacks = payload["stacks"] if kind == "lab_stacks" else [payload]
            for stack in stacks:
                yield {
                    "kind": "stack",
                    "id": f"lab-{payload.get('epoch', 0):x}-{stack['id']}",
                    "frames": stack["frames"],
                    "quality": "verified_lab_allocation_frame",
                    "flags": stack["flags"],
                }
        elif kind == "lab_events":
            payload = item["payload"]
            for row in payload["events"]:
                seq, ptr, old, size, mono, tid, code, pid, stack, interp, flags, started = row
                stamp = item["timestamp"] + (mono - item["monotonic_ns"]) / 1e9
                if stamp < created_at:
                    continue
                yield {
                    "kind": "allocation",
                    "event": {
                        "version": 1,
                        "source": f"cpython27_lab_v2-{payload['epoch']:x}",
                        "pid": pid,
                        "monotonic_ns": mono,
                        "sequence": seq,
                        "process": process_key,
                        "domain": "python_block",
                        "pointer": ptr,
                        "old_pointer": old,
                        "size": size,
                        "thread": tid,
                        "timestamp": stamp,
                        "started_at": stamp + (started - mono) / 1e9 if started else None,
                        "kind": {1: "alloc", 2: "free", 3: "realloc"}.get(code, "invalid"),
                        "stack": f"lab-{payload['epoch']:x}-{stack}" if stack else None,
                        "operation": None,
                    },
                }
        else:
            yield item
