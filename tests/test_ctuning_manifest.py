"""Curated ctuning manifest loads (no network)."""

from pathlib import Path

from trace_synthesizer.benchmarks.ctuning_curated import load_manifest


def test_manifest_loads() -> None:
    root = Path(__file__).resolve().parents[1]
    m = load_manifest(root)
    ids = {e.id for e in m}
    assert len(m) >= 5
    assert "shared-matmul-c" in ids
    assert "shared-matmul-c2" in ids
    assert "cbench-automotive-bitcount" in ids
    assert "cbench-telecom-crc32" in ids
    assert "cbench-security-sha" in ids
    sha = next(e for e in m if e.id == "cbench-security-sha")
    assert sha.rollout_func == "sha_stream"
    assert sha.resolved_rollout_max_steps(5000) == 0
    mm = next(e for e in m if e.id == "shared-matmul-c")
    assert mm.rollout_func == "main"
    bc = next(e for e in m if e.id == "cbench-automotive-bitcount")
    assert bc.rollout_func == "bit_count"
