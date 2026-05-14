"""Minimal policy checkpoint: weights ``.pt`` + hyperparameters ``.json``."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import torch
import torch.nn as nn

from trace_synthesizer.agents.feature_window_lstm_policy import FeatureWindowLstmPolicy
from trace_synthesizer.agents.ppo_policies import FlatActorCritic, HierarchicalActorCritic

CHECKPOINT_SCHEMA_VERSION = 1
POLICY_TYPE_MASKED_LSTM = "masked_lstm"
POLICY_TYPE_FEATURE_WINDOW_LSTM = "feature_window_lstm"
POLICY_TYPE_PPO_FLAT = "ppo_flat_actor_critic"
POLICY_TYPE_PPO_HIERARCHICAL = "ppo_hier_actor_critic"


def save_policy_checkpoint(stem: Path, policy: nn.Module, meta: dict[str, Any]) -> None:
    """
    Write ``{stem}.pt`` (``state_dict``) and ``{stem}.json`` (hyperparameters).

    ``stem`` should have no suffix (e.g. ``Path("artifacts/run1/policy")``).
    """
    stem = stem.expanduser().resolve()
    stem.parent.mkdir(parents=True, exist_ok=True)
    torch.save(policy.state_dict(), stem.with_suffix(".pt"))
    payload = {"schema_version": CHECKPOINT_SCHEMA_VERSION, **meta}
    stem.with_suffix(".json").write_text(
        json.dumps(payload, indent=2, default=str), encoding="utf-8"
    )


def load_policy_checkpoint(
    stem: Path,
    *,
    device: torch.device | str = "cpu",
    strict: bool = True,
) -> tuple[nn.Module, dict[str, Any]]:
    """
    Load ``{stem}.pt`` and ``{stem}.json`` and return ``(policy, meta)``.

    ``policy`` is either ``MaskedLstmPolicyStub`` or ``FeatureWindowLstmPolicy`` depending
    on ``meta['policy_type']``.
    """
    stem = stem.expanduser().resolve()
    pt_path = stem.with_suffix(".pt")
    json_path = stem.with_suffix(".json")
    if not json_path.is_file() or not pt_path.is_file():
        raise FileNotFoundError(
            f"Checkpoint stem {stem}: expected {pt_path.name} and {json_path.name} "
            f"next to each other. Generate them with save_policy_checkpoint(...) or run "
            f"experiments/notebooks/lstm_supervised_benchmark.ipynb (writes under "
            f"experiments/artifacts/). For a ready-made example use "
            f"examples/lstm_checkpoints/demo_lstm_main_testcfg (no suffix on --checkpoint)."
        )
    meta = json.loads(json_path.read_text(encoding="utf-8"))
    if int(meta.get("schema_version", 0)) != CHECKPOINT_SCHEMA_VERSION:
        raise ValueError(
            f"Unsupported checkpoint schema {meta.get('schema_version')!r}; "
            f"expected {CHECKPOINT_SCHEMA_VERSION}"
        )
    ptype = meta.get("policy_type")
    if ptype not in (
        POLICY_TYPE_MASKED_LSTM,
        POLICY_TYPE_FEATURE_WINDOW_LSTM,
        POLICY_TYPE_PPO_FLAT,
        POLICY_TYPE_PPO_HIERARCHICAL,
    ):
        raise ValueError(f"Unsupported policy_type {ptype!r}")
    policy = build_policy_from_meta(meta)
    state = torch.load(pt_path, map_location=device, weights_only=True)
    policy.load_state_dict(state, strict=strict)
    policy.to(device)
    return policy, meta


def build_policy_from_meta(meta: dict[str, Any]) -> nn.Module:
    ptype = meta.get("policy_type")
    if ptype == POLICY_TYPE_FEATURE_WINDOW_LSTM:
        wb = int(meta.get("window_back", meta.get("window", 8)))
        succ = int(meta.get("succ_feat_slots", 0))
        gdim = int(meta.get("global_summary_dim", 0))
        return FeatureWindowLstmPolicy(
            window_back=wb,
            feat_dim=int(meta["feat_dim"]),
            max_actions=int(meta["max_actions"]),
            succ_feat_slots=succ,
            global_summary_dim=gdim,
            lstm_hidden=int(meta.get("lstm_hidden", 64)),
        )
    if ptype == POLICY_TYPE_PPO_FLAT:
        return FlatActorCritic(
            feat_dim=int(meta["feat_dim"]),
            max_actions=int(meta["max_actions"]),
            hidden=int(meta.get("hidden", 128)),
            use_aux_exit=bool(meta.get("use_aux_exit", False)),
        )
    if ptype == POLICY_TYPE_PPO_HIERARCHICAL:
        return HierarchicalActorCritic(
            feat_dim=int(meta["feat_dim"]),
            max_actions=int(meta["max_actions"]),
            num_modes=int(meta.get("num_modes", 4)),
            z_embed_dim=int(meta.get("z_embed_dim", 8)),
            manager_every=int(meta.get("manager_every", 4)),
            hidden=int(meta.get("hidden", 128)),
            use_aux_exit=bool(meta.get("use_aux_exit", False)),
        )
    raise ValueError(f"Unsupported policy_type {ptype!r}")


def feature_window_lstm_meta_for_save(
    *,
    window_back: int,
    feat_dim: int,
    max_actions: int,
    succ_feat_slots: int = 0,
    global_summary_dim: int = 0,
    lstm_hidden: int = 64,
    function_name: str | None = None,
) -> dict[str, Any]:
    out: dict[str, Any] = {
        "policy_type": POLICY_TYPE_FEATURE_WINDOW_LSTM,
        "layout_version": 2,
        "window_back": int(window_back),
        "window": int(window_back),
        "feat_dim": int(feat_dim),
        "max_actions": int(max_actions),
        "succ_feat_slots": int(succ_feat_slots),
        "global_summary_dim": int(global_summary_dim),
        "lstm_hidden": int(lstm_hidden),
    }
    if function_name is not None:
        out["function_name"] = function_name
    return out


def ppo_flat_meta_for_save(
    *,
    feat_dim: int,
    max_actions: int,
    hidden: int = 128,
    function_name: str | None = None,
    use_aux_exit: bool = False,
) -> dict[str, Any]:
    out: dict[str, Any] = {
        "policy_type": POLICY_TYPE_PPO_FLAT,
        "feat_dim": int(feat_dim),
        "max_actions": int(max_actions),
        "hidden": int(hidden),
        "use_aux_exit": bool(use_aux_exit),
    }
    if function_name is not None:
        out["function_name"] = function_name
    return out


def ppo_hier_meta_for_save(
    *,
    feat_dim: int,
    max_actions: int,
    num_modes: int,
    z_embed_dim: int,
    manager_every: int,
    hidden: int = 128,
    function_name: str | None = None,
    use_aux_exit: bool = False,
) -> dict[str, Any]:
    out: dict[str, Any] = {
        "policy_type": POLICY_TYPE_PPO_HIERARCHICAL,
        "feat_dim": int(feat_dim),
        "max_actions": int(max_actions),
        "num_modes": int(num_modes),
        "z_embed_dim": int(z_embed_dim),
        "manager_every": int(manager_every),
        "hidden": int(hidden),
        "use_aux_exit": bool(use_aux_exit),
    }
    if function_name is not None:
        out["function_name"] = function_name
    return out
