"""Portable format/accounting tests. These do NOT establish kernel coverage."""

import pytest
from leakscope_api.capture import Writer, Reader
from leakscope_api.native import analyze, NativeAnalysisError


def event(n, kind, pointer=0, old=0, size=0, timestamp=None):
    return {
        "sequence": n,
        "kind": "allocation",
        "event": {
            "sequence": n,
            "process": "a" * 64,
            "domain": "native",
            "pointer": pointer,
            "old_pointer": old,
            "kind": kind,
            "size": size,
            "timestamp": timestamp if timestamp is not None else n,
            "stack": "1",
            "operation": None,
            "thread": 7,
        },
    }


def test_streaming_native_capture_quality_filters_and_loss(tmp_path):
    path = tmp_path / "native.lscap"
    writer = Writer(path, {"quality": {"coverage": "native_observed"}})
    writer.chunk(
        [
            {
                "sequence": 1,
                "kind": "stack",
                "id": "1",
                "frames": [
                    {
                        "module": "libfixture.so",
                        "function": "allocation_site",
                        "file": None,
                        "line": None,
                    }
                ],
            }
        ]
    )
    for n, e in enumerate(
        [
            event(1, "alloc", 1, size=40),
            event(2, "alloc", 2, size=60),
            event(3, "free", 2),
            event(4, "realloc", 0, 1, 100),
        ],
        2,
    ):
        e["sequence"] = n
        writer.chunk([e])
    writer.close()
    result = analyze(path)
    assert result["known_live_by_domain"] == {"native": 40}
    assert result["retained_tree"]["value"] == 40
    assert result["allocation_tree"]["value"] == 100
    assert analyze(path, start=2)["retained_tree"]["value"] == 0
    assert analyze(path, thread=8)["allocation_tree"]["value"] == 0
    assert analyze(path, library="other.so")["retained_tree"]["value"] == 0
    writer = Writer.resume(path, {})
    writer.chunk(
        [
            {
                "sequence": 6,
                "kind": "quality",
                "quality": {
                    "coverage": "native_observed",
                    "lost_frees": 1,
                    "lost_events": 1,
                    "incomplete": True,
                },
            }
        ]
    )
    writer.close()
    result = analyze(path)
    assert not result["exact_survivors"]
    assert result["known_live_by_domain"] is None
    assert result["top_sites"][0]["known_live_bytes"] is None
    assert result["lost_events"] == 1


def test_spool_recovery_discards_only_interrupted_tail(tmp_path):
    path = tmp_path / "partial.lscap"
    writer = Writer(path, {})
    writer.chunk([event(1, "alloc", 1, size=9)])
    writer.out.write(b"interrupted")
    writer.out.close()
    reader = Reader(path)
    assert len(list(reader.chunks())) == 1 and reader.recovered
    writer = Writer.resume(path, {})
    assert writer.last == 1
    writer.chunk([event(2, "free", 1)])
    writer.close()
    reader = Reader(path)
    assert len(list(reader.chunks())) == 2 and not reader.recovered
    assert analyze(path)["known_live_by_domain"] == {}


def test_native_reordered_sequence_fails_explicitly(tmp_path):
    path = tmp_path / "reordered.lscap"
    writer = Writer(path, {})
    a, b = event(2, "alloc", 1, size=5), event(1, "free", 1)
    a["sequence"], b["sequence"] = 1, 2
    writer.chunk([a, b])
    writer.close()
    with pytest.raises(NativeAnalysisError, match="reordered"):
        analyze(path)
