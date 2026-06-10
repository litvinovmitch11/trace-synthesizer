"""Training loop for flat/hierarchical PPO on CFGWalkRewardWrapper."""

from __future__ import annotations

import json
import random
import sys
from collections import Counter, deque
from pathlib import Path
from typing import Any

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.utils.tensorboard import SummaryWriter

from trace_synthesizer.agents.checkpoint import (
    load_policy_checkpoint,
    ppo_flat_meta_for_save,
    ppo_hier_meta_for_save,
    save_policy_checkpoint,
)
from trace_synthesizer.agents.ppo_policies import (
    FlatActorCritic,
    HierarchicalActorCritic,
)
from trace_synthesizer.core.grammar import CfgProgram, ordered_successors
from trace_synthesizer.env.cfg_reward_wrapper import CFGWalkRewardWrapper
from trace_synthesizer.env.feature_window_wrapper import FeatureWindowWrapper
from trace_synthesizer.env.interproc_walk_env import InterproceduralCFGWalkEnv
from trace_synthesizer.metrics.loaders import (
    load_path_from_compressed_trace,
    load_path_from_intra_trace_json,
    load_paths_from_intra_traces_jsonl,
)
from trace_synthesizer.rl.loop_profile import (
    exit_aux_label,
    load_loop_profile,
    load_reference_paths_as_bb_sequences,
    pack_actor_observation_features,
)
from trace_synthesizer.rl.ppo import attach_gae_to_batch, ppo_update
from trace_synthesizer.rl.rewards import RewardConfig
from trace_synthesizer.rl.rollout_buffer import RolloutBuffer


def _configure_trainable_params(policy: torch.nn.Module, freeze_mode: str) -> None:
    mode = str(freeze_mode).strip().lower()
    if mode in {"none", "", "full"}:
        for p in policy.parameters():
            p.requires_grad = True
        return
    if mode != "head-only":
        raise ValueError(f"unsupported freeze mode: {freeze_mode!r}")
    for p in policy.parameters():
        p.requires_grad = False
    if isinstance(policy, FlatActorCritic):
        for p in policy.pi.parameters():
            p.requires_grad = True
        for p in policy.v.parameters():
            p.requires_grad = True
        if getattr(policy, "_use_aux_exit", False):
            for p in policy.aux_exit.parameters():
                p.requires_grad = True
        return
    if isinstance(policy, HierarchicalActorCritic):
        # Keep only final affine heads trainable for fast per-graph calibration.
        for p in policy.manager[-1].parameters():
            p.requires_grad = True
        for p in policy.worker[-1].parameters():
            p.requires_grad = True
        for p in policy.critic[-1].parameters():
            p.requires_grad = True
        if getattr(policy, "_use_aux_exit", False):
            for p in policy.aux_exit.parameters():
                p.requires_grad = True
        return
    raise TypeError(f"unsupported policy type: {type(policy)}")


def load_ref_histogram(
    *,
    ref: Path | None,
    ref_compressed: bool,
    function_name: str,
) -> Counter[int] | None:
    if ref is None:
        return None
    if ref_compressed:
        p = load_path_from_compressed_trace(ref, function_name)
        return Counter(int(bb) for fn, bb in p if fn == function_name)
    if ref.suffix.lower() == ".jsonl":
        paths = load_paths_from_intra_traces_jsonl(ref)
        c: Counter[int] = Counter()
        for path in paths:
            for fn, bb in path:
                if fn == function_name:
                    c[int(bb)] += 1
        return c
    p = load_path_from_intra_trace_json(ref)
    return Counter(int(bb) for fn, bb in p if fn == function_name)


def _policy_in_features(policy: torch.nn.Module) -> int:
    if isinstance(policy, FlatActorCritic):
        return int(policy.body[0].in_features)
    if isinstance(policy, HierarchicalActorCritic):
        return int(policy.manager[0].in_features)
    raise TypeError(type(policy))


def run_bc_pretrain(
    *,
    env: gym.Env,
    policy: torch.nn.Module,
    optimizer: torch.optim.Optimizer,
    grammar: CfgProgram,
    args: Any,
    loop_profile: dict[str, Any] | None,
    device: torch.device,
    policy_max_actions: int,
    bc_epochs: int,
    bc_batch: int,
    bc_aux_coef: float,
    max_grad_norm: float,
) -> None:
    """Behavior cloning on reference paths (worker with z=0 for hierarchical)."""
    if bc_epochs <= 0 or args.reference is None:
        return
    paths = load_reference_paths_as_bb_sequences(
        ref=Path(args.reference),
        ref_compressed=bool(args.reference_compressed),
        function_name=str(args.func),
    )
    if not paths:
        return
    fn_cfg = grammar.function(str(args.func))
    entry = int(grammar.entry_bb_id(str(args.func)))
    transitions: list[tuple[np.ndarray, np.ndarray, int, float]] = []

    from trace_synthesizer.agents.cfg_supervision import (
        action_mask_rows_for_bb_prefix,
        prefix_features_along_bb_path,
        supervision_pairs_from_bb_path,
    )

    for path in paths:
        if not path or int(path[0]) != entry:
            continue
        try:
            feats = prefix_features_along_bb_path(env, grammar, str(args.func), path)
            masks = action_mask_rows_for_bb_prefix(
                grammar, str(args.func), path[:-1], max_actions=policy_max_actions
            )
            pairs = supervision_pairs_from_bb_path(grammar, str(args.func), path)

            if len(pairs) != len(path) - 1:
                continue

            for i in range(len(pairs)):
                u, ai = pairs[i]
                v = int(path[i + 1])
                aux_t = float(exit_aux_label(u, v, fn_cfg))
                transitions.append((feats[i], masks[i], int(ai), aux_t))
        except ValueError:
            continue

    if not transitions:
        return

    for _ in range(bc_epochs):
        random.shuffle(transitions)
        for start in range(0, len(transitions), bc_batch):
            chunk = transitions[start : start + bc_batch]
            if not chunk:
                continue
            obs_np = np.stack([c[0] for c in chunk], axis=0)
            masks_np = np.stack([c[1] for c in chunk], axis=0)
            act_np = np.array([c[2] for c in chunk], dtype=np.int64)
            aux_np = np.array([c[3] for c in chunk], dtype=np.float32)
            obs = torch.tensor(obs_np, dtype=torch.float32, device=device)
            mask = torch.tensor(masks_np, dtype=torch.bool, device=device)
            act = torch.tensor(act_np, dtype=torch.long, device=device)
            aux_tgt = torch.tensor(aux_np, dtype=torch.float32, device=device)

            optimizer.zero_grad(set_to_none=True)
            if isinstance(policy, FlatActorCritic):
                logits, _vals = policy.forward(obs)
                logits = logits.masked_fill(~mask, -1e9)
                logp = torch.log_softmax(logits, dim=-1)
                pi_loss = -logp.gather(1, act.view(-1, 1)).squeeze(-1).mean()
                z0 = None
            elif isinstance(policy, HierarchicalActorCritic):
                z0 = torch.randint(0, policy.num_modes, (obs.shape[0],), device=device)
                logits, _vals = policy.forward_worker_critic(obs, z0)
                logits = logits.masked_fill(~mask, -1e9)
                logp = torch.log_softmax(logits, dim=-1)
                pi_loss = -logp.gather(1, act.view(-1, 1)).squeeze(-1).mean()
            else:
                raise TypeError(type(policy))

            loss = pi_loss
            if getattr(policy, "_use_aux_exit", False) and bc_aux_coef > 0.0:
                if isinstance(policy, FlatActorCritic):
                    la = policy.aux_exit_logit(obs)
                elif isinstance(policy, HierarchicalActorCritic):
                    assert z0 is not None
                    la = policy.aux_exit_logit(obs, z0)
                else:
                    la = None
                if la is not None:
                    loss = loss + float(
                        bc_aux_coef
                    ) * F.binary_cross_entropy_with_logits(la, aux_tgt)
            loss.backward()
            nn.utils.clip_grad_norm_(policy.parameters(), float(max_grad_norm))
            optimizer.step()


def _apply_loop_proposal_reward_defaults(
    args: Any, loop_profile: dict[str, Any] | None
) -> None:
    """
    When a ``loop_profile`` is present, enable proposal-aligned shaping by default:

    - ``ref_edge_log_scale``: dense log p_ref(action|bb) from real traces (III.C).
    - ``short_path_penalty_scale``: penalize episodes far shorter than reference paths.
    - ``loop_timing_scale``: gentle bonus near reference loop-header visit counts.

    Opt out entirely with ``--no-loop-proposal-defaults``. To keep a term at zero
    while using others, pass ``--no-loop-proposal-defaults`` and set scales explicitly.
    """
    if loop_profile is None or bool(getattr(args, "no_loop_proposal_defaults", False)):
        return
    if float(getattr(args, "ref_edge_log_scale", 0.0)) == 0.0:
        setattr(args, "ref_edge_log_scale", 0.35)
    if float(getattr(args, "short_path_penalty_scale", 0.0)) == 0.0:
        setattr(args, "short_path_penalty_scale", 0.55)
    if float(getattr(args, "loop_timing_scale", 0.0)) == 0.0:
        setattr(args, "loop_timing_scale", 0.03)


def run_train_ppo(args: Any) -> dict[str, Any]:
    random.seed(args.seed)
    np.random.seed(args.seed)
    torch.manual_seed(args.seed)
    device = torch.device(args.device)

    grammar = CfgProgram.from_cfg_json(args.cfg)
    base_env = InterproceduralCFGWalkEnv(
        grammar,
        args.func,
        max_steps=int(args.max_steps),
        seed=args.seed,
        device=device,
    )
    lp_path = getattr(args, "loop_profile", None)
    loop_profile: dict[str, Any] | None = None
    if lp_path is not None:
        loop_profile = load_loop_profile(Path(lp_path))

    _apply_loop_proposal_reward_defaults(args, loop_profile)

    aux_exit_head = int(getattr(args, "aux_exit_head", 1)) == 1
    use_aux_exit = bool(loop_profile) and aux_exit_head

    ref_hist = load_ref_histogram(
        ref=args.reference,
        ref_compressed=bool(args.reference_compressed),
        function_name=args.func,
    )
    rew_cfg = RewardConfig(
        pgo_log_scale=float(args.pgo_log_scale),
        invalid_action_penalty=float(args.invalid_action_penalty),
        repeat_bb_penalty_scale=float(getattr(args, "repeat_bb_penalty_scale", 0.0)),
        truncation_penalty=float(getattr(args, "truncation_penalty", 0.0)),
        terminal_kl_scale=float(args.terminal_kl_scale),
        loop_timing_scale=float(getattr(args, "loop_timing_scale", 0.0)),
        ref_edge_log_scale=float(getattr(args, "ref_edge_log_scale", 0.0)),
        short_path_penalty_scale=float(getattr(args, "short_path_penalty_scale", 0.0)),
    )
    env = CFGWalkRewardWrapper(
        base_env,
        grammar,
        args.func,
        reward_config=rew_cfg,
        ref_bb_hist=ref_hist,
        loop_profile=loop_profile,
    )

    window_back = int(getattr(args, "window_back", 1))
    env = FeatureWindowWrapper(env, window_back=window_back)

    feat_dim = int(env.observation_space["features"].shape[0])
    max_actions = int(env.action_space.n)
    init_ckpt = getattr(args, "init_checkpoint", None)
    if init_ckpt is not None:
        loaded, meta = load_policy_checkpoint(
            Path(init_ckpt), device=device, strict=True
        )
        if args.hierarchical and not isinstance(loaded, HierarchicalActorCritic):
            raise ValueError(
                f"--hierarchical requested but init checkpoint is {type(loaded)}"
            )
        if (not args.hierarchical) and not isinstance(loaded, FlatActorCritic):
            raise ValueError(
                f"flat policy requested but init checkpoint is {type(loaded)}"
            )
        got_dim = _policy_in_features(loaded)
        if got_dim != feat_dim:
            raise ValueError(
                f"init checkpoint feat_dim {got_dim} != environment {feat_dim} "
                f"(loop_profile / obs tail mismatch?)"
            )
        if use_aux_exit and not bool(meta.get("use_aux_exit", False)):
            raise ValueError(
                "loop_profile + aux exit requested but init checkpoint lacks use_aux_exit"
            )
        policy = loaded
    elif args.hierarchical:
        policy = HierarchicalActorCritic(
            feat_dim,
            max_actions,
            num_modes=int(args.num_modes),
            z_embed_dim=int(args.z_embed_dim),
            manager_every=int(args.manager_every),
            hidden=int(args.hidden),
            use_aux_exit=use_aux_exit,
        )
    else:
        policy = FlatActorCritic(
            feat_dim, max_actions, hidden=int(args.hidden), use_aux_exit=use_aux_exit
        )
    policy.to(device)
    if isinstance(policy, (FlatActorCritic, HierarchicalActorCritic)):
        policy_max_actions = int(policy.max_actions)
    else:
        raise TypeError(f"unsupported policy type: {type(policy)}")
    if int(max_actions) > policy_max_actions:
        raise ValueError(
            f"env max_actions {max_actions} > policy max_actions {policy_max_actions}"
        )
    freeze_mode = str(getattr(args, "freeze_mode", "none"))
    _configure_trainable_params(policy, freeze_mode)
    trainable = [p for p in policy.parameters() if p.requires_grad]
    if not trainable:
        raise ValueError("no trainable parameters after applying freeze_mode")
    opt = torch.optim.Adam(trainable, lr=float(args.lr))
    writer: SummaryWriter | None = None
    tb_logdir = getattr(args, "tb_logdir", None)
    if tb_logdir is not None:
        run_name = str(getattr(args, "tb_run_name", "train_hrl_ppo"))
        tb_path = Path(tb_logdir) / run_name
        tb_path.mkdir(parents=True, exist_ok=True)
        writer = SummaryWriter(log_dir=str(tb_path))

    bc_epochs = int(getattr(args, "bc_epochs", 0) or 0)
    bc_batch = max(1, int(getattr(args, "bc_batch_size", 64) or 64))
    bc_aux_coef = float(getattr(args, "bc_aux_coef", 0.1) or 0.0)
    run_bc_pretrain(
        env=env,
        policy=policy,
        optimizer=opt,
        grammar=grammar,
        args=args,
        loop_profile=loop_profile,
        device=device,
        policy_max_actions=policy_max_actions,
        bc_epochs=bc_epochs,
        bc_batch=bc_batch,
        bc_aux_coef=bc_aux_coef,
        max_grad_norm=float(args.max_grad_norm),
    )

    aux_exit_coef = float(getattr(args, "aux_exit_coef", 0.05) or 0.0)
    if not use_aux_exit:
        aux_exit_coef = 0.0

    obs, info = env.reset(seed=args.seed)
    episode_reward = 0.0
    episode_returns: list[float] = []
    last_train: dict[str, float] = {}
    z_cur = torch.tensor([-1], dtype=torch.long, device=device)
    t_ep = 0

    for it in range(int(args.iterations)):
        buf = RolloutBuffer()
        for _ in range(int(args.steps_per_iter)):
            feat = np.asarray(obs["features"], dtype=np.float32).reshape(-1)
            raw_mask = np.asarray(info["action_mask"], dtype=np.bool_).reshape(-1)
            mask = np.zeros(policy_max_actions, dtype=np.bool_)
            n = min(raw_mask.size, policy_max_actions)
            mask[:n] = raw_mask[:n]
            feat_t = torch.tensor(feat, dtype=torch.float32, device=device).view(1, -1)
            mask_t = torch.tensor(mask, dtype=torch.bool, device=device).view(1, -1)

            if args.hierarchical:
                assert isinstance(policy, HierarchicalActorCritic)
                fire = t_ep == 0 or (t_ep % policy.manager_every == 0)
                if fire:
                    z_cur, lp_m = policy.sample_manager(feat_t)
                else:
                    lp_m = torch.zeros(1, dtype=torch.float32, device=device)
                act_t, lp_w, v_t = policy.act_worker(feat_t, mask_t, z_cur)
                old_lp = float((lp_w + (lp_m if fire else 0.0)).item())
                z_i = int(z_cur.item())
                manager_fired = bool(fire)
            else:
                assert isinstance(policy, FlatActorCritic)
                act_t, lp_w, v_t = policy.act(feat_t, mask_t)
                old_lp = float(lp_w.item())
                z_i = -1
                manager_fired = False

            action = int(act_t.item())
            obs2, reward, terminated, truncated, info2 = env.step(action)
            done = bool(terminated or truncated)
            buf.append(
                obs_feat=feat,
                mask=mask,
                action=action,
                reward=float(reward),
                done=1.0 if done else 0.0,
                old_log_prob=old_lp,
                old_value=float(v_t.item()),
                manager_z=z_i,
                manager_fired=manager_fired,
                aux_target=float(info2.get("aux_exit_next", 0.0)),
            )
            obs, info = obs2, info2
            episode_reward += float(reward)
            t_ep += 1

            if done:
                episode_returns.append(episode_reward)
                episode_reward = 0.0
                obs, info = env.reset()
                t_ep = 0
                z_cur = torch.tensor([-1], dtype=torch.long, device=device)

        batch = buf.stack(device=device)
        batch = attach_gae_to_batch(
            batch,
            gamma=float(args.gamma),
            lam=float(args.gae_lambda),
            next_value=0.0,
            normalize_adv=True,
        )
        policy.train()
        last_train = ppo_update(
            batch,
            policy,
            opt,
            epochs=int(args.epochs),
            minibatch_size=int(args.minibatch_size),
            clip_coef=float(args.clip_coef),
            vf_coef=float(args.vf_coef),
            ent_coef=float(args.ent_coef),
            max_grad_norm=float(args.max_grad_norm),
            aux_exit_coef=aux_exit_coef,
        )
        if bool(getattr(args, "verbose", False)):
            print(
                f"[ppo] iter {it + 1}/{int(args.iterations)} "
                f"loss={float(last_train.get('loss', 0.0)):.4f} "
                f"kl={float(last_train.get('approx_kl', 0.0)):.5f} "
                f"entropy={float(last_train.get('entropy', 0.0)):.4f} "
                f"episodes={len(episode_returns)}",
                file=sys.stderr,
                flush=True,
            )
        if writer is not None:
            step = it + 1
            writer.add_scalar("train/loss", float(last_train.get("loss", 0.0)), step)
            writer.add_scalar(
                "train/policy_loss", float(last_train.get("policy_loss", 0.0)), step
            )
            writer.add_scalar(
                "train/value_loss", float(last_train.get("value_loss", 0.0)), step
            )
            writer.add_scalar(
                "train/entropy", float(last_train.get("entropy", 0.0)), step
            )
            writer.add_scalar(
                "train/approx_kl", float(last_train.get("approx_kl", 0.0)), step
            )
            writer.add_scalar(
                "train/aux_bce", float(last_train.get("aux_bce", 0.0)), step
            )
            if episode_returns:
                window = episode_returns[-50:]
                writer.add_scalar(
                    "rollout/mean_episode_return_last50",
                    float(sum(window) / len(window)),
                    step,
                )
                writer.add_scalar(
                    "rollout/episodes_finished_total",
                    float(len(episode_returns)),
                    step,
                )

    policy.eval()
    saved_max_actions = int(policy_max_actions)
    if args.hierarchical:
        assert isinstance(policy, HierarchicalActorCritic)
        meta = ppo_hier_meta_for_save(
            feat_dim=feat_dim,
            max_actions=saved_max_actions,
            num_modes=int(args.num_modes),
            z_embed_dim=int(args.z_embed_dim),
            manager_every=int(args.manager_every),
            hidden=int(args.hidden),
            function_name=args.func,
            use_aux_exit=bool(getattr(policy, "_use_aux_exit", False)),
        )
    else:
        meta = ppo_flat_meta_for_save(
            feat_dim=feat_dim,
            max_actions=saved_max_actions,
            hidden=int(args.hidden),
            function_name=args.func,
            use_aux_exit=bool(getattr(policy, "_use_aux_exit", False)),
        )
    meta.update(
        {
            "reward_config": {
                "pgo_log_scale": float(args.pgo_log_scale),
                "invalid_action_penalty": float(args.invalid_action_penalty),
                "repeat_bb_penalty_scale": float(
                    getattr(args, "repeat_bb_penalty_scale", 0.0)
                ),
                "truncation_penalty": float(getattr(args, "truncation_penalty", 0.0)),
                "terminal_kl_scale": float(args.terminal_kl_scale),
                "loop_timing_scale": float(getattr(args, "loop_timing_scale", 0.0)),
                "ref_edge_log_scale": float(getattr(args, "ref_edge_log_scale", 0.0)),
                "short_path_penalty_scale": float(
                    getattr(args, "short_path_penalty_scale", 0.0)
                ),
            },
            "algo": "ppo",
            "loop_profile": (
                str(Path(lp_path).expanduser().resolve())
                if lp_path is not None
                else None
            ),
        }
    )
    save_policy_checkpoint(args.out_stem, policy, {"schema_version": 1, **meta})

    report: dict[str, Any] = {
        "algo": "ppo",
        "hierarchical": bool(args.hierarchical),
        "iterations": int(args.iterations),
        "steps_per_iter": int(args.steps_per_iter),
        "episodes_finished": len(episode_returns),
        "mean_episode_return": (
            float(sum(episode_returns) / len(episode_returns))
            if episode_returns
            else 0.0
        ),
        "last_train": last_train,
        "checkpoint_stem": str(args.out_stem.resolve()),
    }
    if args.train_report is not None:
        args.train_report.parent.mkdir(parents=True, exist_ok=True)
        args.train_report.write_text(json.dumps(report, indent=2), encoding="utf-8")
    if writer is not None:
        writer.add_hparams(
            {
                "hierarchical": bool(args.hierarchical),
                "iterations": int(args.iterations),
                "steps_per_iter": int(args.steps_per_iter),
                "lr": float(args.lr),
                "clip_coef": float(args.clip_coef),
                "vf_coef": float(args.vf_coef),
                "ent_coef": float(args.ent_coef),
                "hidden": int(args.hidden),
            },
            {"hparam/mean_episode_return": float(report["mean_episode_return"])},
        )
        writer.flush()
        writer.close()
    return report
