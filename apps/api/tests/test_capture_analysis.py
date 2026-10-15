import struct
import pytest
from leakscope_api.capture import Writer, Reader, CaptureError
from leakscope_api.analysis import slope, summarize


@pytest.mark.parametrize("count", [0, 1, 10, 300])
def test_capture_streaming_roundtrip(tmp_path, count):
    path = tmp_path / "capture.lscap"
    writer = Writer(path, {"format": 1})
    for n in range(count):
        writer.chunk([{"sequence": n + 1, "kind": "metric", "sample": {"rss": n}}])
    writer.close()
    reader = Reader(path)
    assert sum(len(b) for b in reader.chunks()) == count
    assert not reader.recovered
    assert reader.missing_sequences == 0


def test_recovery_corruption_and_limits(tmp_path):
    path = tmp_path / "capture.lscap"
    writer = Writer(path, {})
    writer.chunk([{"sequence": 1}])
    writer.chunk([{"sequence": 3}])
    writer.close()
    original = path.read_bytes()
    path.write_bytes(original[:-20])
    reader = Reader(path)
    assert len(list(reader.chunks())) == 2
    assert reader.recovered and reader.missing_sequences == 1
    corrupted = bytearray(original)
    corrupted[46 + 24] ^= 1
    path.write_bytes(corrupted)
    with pytest.raises(CaptureError):
        list(Reader(path).chunks())
    path.write_bytes(b"LSCAP\0\x01\0" + struct.pack(">I", 65537))
    with pytest.raises(CaptureError):
        Reader(path)
    path.write_bytes(b"LSCAP\0\x02\0")
    with pytest.raises(CaptureError):
        Reader(path)


def test_robust_trend_and_honest_scoring():
    # A bounded estimator must sample the whole capture, including its later half.
    assert 0.2 < slope([(i, max(0, i - 255)) for i in range(511)]) < 0.8
    assert slope([(0, 0), (1, 2), (2, 999), (3, 6), (4, 8)]) == 2
    rising = [{"timestamp": i, "rss": 1000000 + i * 100000} for i in range(30)]
    summary = summarize(rising)
    assert summary["classification"] == "sustained_growth"
    assert summary["suspicion_score"] <= 40
    assert summary["known_live_allocations"] is None
    assert summarize(rising, {"lost_samples": 5})["suspicion_score"] < summary["suspicion_score"]
    spike = [{"timestamp": i, "rss": 1000000 + (10000000 if 8 < i < 14 else 0)} for i in range(30)]
    assert summarize(spike)["classification"] == "transient_spike"
    assert summarize([])["classification"] == "insufficient_evidence"


def test_committed_cross_language_golden():
    from pathlib import Path

    path = Path(__file__).resolve().parents[3] / "tests/fixtures/golden/metrics-v1.lscap"
    reader = Reader(path)
    events = list(reader.chunks())
    assert events[0][0]["sample"]["rss"] == 4096
    assert not reader.recovered


def test_loss_inside_a_chunk_is_reported(tmp_path):
    path = tmp_path / "gapped.lscap"
    writer = Writer(path, {})
    writer.chunk([{"sequence": 1}, {"sequence": 4}])
    writer.close()
    reader = Reader(path)
    list(reader.chunks())
    assert reader.missing_sequences == 2
