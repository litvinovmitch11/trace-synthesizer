"""Overlap of most frequent block n-grams between reference and candidate corpora."""

from __future__ import annotations

from collections import Counter

from trace_synthesizer.metrics.types import MetricContext, MetricResult, TracePath

Ngram = tuple[int, ...]


def _ngrams_for_path(bbs: list[int], n: int) -> Counter[Ngram]:
    c: Counter[Ngram] = Counter()
    if len(bbs) < n:
        return c
    for i in range(len(bbs) - n + 1):
        c[tuple(bbs[i : i + n])] += 1
    return c


def _pool_ngrams(paths: list[TracePath], func: str, n: int) -> Counter[Ngram]:
    total: Counter[Ngram] = Counter()
    for path in paths:
        bbs = [bb for f, bb in path if f == func]
        total.update(_ngrams_for_path(bbs, n))
    return total


def compute_hot_path_overlap(
    reference_paths: list[TracePath],
    candidate_paths: list[TracePath],
    ctx: MetricContext,
) -> MetricResult:
    """
    For each n in [ngram_min, ngram_max]:
      - rank n-grams by frequency in reference (pooled)
      - take top_k by count
      - recall@k = fraction of those that appear ≥1 time in candidate (pooled)
      - jaccard = |T_ref ∩ T_cand| / |T_ref ∪ T_cand| where T_* are top_k sets
    Aggregated summary value = mean recall over n; details keep per-n tables.
    """
    per_n: dict[str, object] = {}
    recalls: list[float] = []
    for n in range(ctx.ngram_min, ctx.ngram_max + 1):
        ref_c = _pool_ngrams(reference_paths, ctx.function_name, n)
        cand_c = _pool_ngrams(candidate_paths, ctx.function_name, n)
        if not ref_c:
            per_n[str(n)] = {
                "recall_at_k": None,
                "jaccard_topk": None,
                "reason": "no_reference_ngrams",
            }
            continue
        top_ref = {g for g, _ in ref_c.most_common(ctx.top_k)}
        top_cand = {g for g, _ in cand_c.most_common(ctx.top_k)}
        hit = sum(1 for g in top_ref if cand_c[g] > 0)
        recall = hit / max(1, len(top_ref))
        inter = len(top_ref & top_cand)
        union = len(top_ref | top_cand)
        jacc = inter / union if union else 0.0
        recalls.append(recall)
        per_n[str(n)] = {
            "recall_at_k": recall,
            "jaccard_topk": jacc,
            "k_ref": len(top_ref),
            "k_cand": len(top_cand),
        }
    if not recalls:
        return MetricResult(
            name="hot_path_ngram_overlap",
            value=None,
            details={"per_n": per_n, "reason": "no_valid_n"},
        )
    mean_recall = sum(recalls) / len(recalls)
    return MetricResult(
        name="hot_path_ngram_overlap",
        value=float(mean_recall),
        details={"per_n": per_n, "mean_recall_at_k": mean_recall},
    )
