"""PPO clipped surrogate loss and multi-epoch minibatch updates."""

from __future__ import annotations

import torch
import torch.nn as nn
import torch.nn.functional as F
import torch.optim as optim

from trace_synthesizer.agents.ppo_policies import FlatActorCritic, HierarchicalActorCritic
from trace_synthesizer.rl.rollout_buffer import RolloutBatch, compute_gae


def ppo_losses(
    batch: RolloutBatch,
    policy: nn.Module,
    *,
    clip_coef: float,
    vf_coef: float,
    ent_coef: float,
    aux_exit_coef: float = 0.0,
) -> tuple[torch.Tensor, dict[str, float]]:
    """
    Forward policy/value on batch observations, return (total_loss, metrics).

    Policy must implement
    ``evaluate_actions(obs, mask, actions, manager_z=None, manager_fired=None)``.
    """
    obs = batch.obs_features
    mask = batch.action_mask
    act = batch.actions
    z = batch.manager_z
    mf = batch.manager_fired
    old_lp = batch.old_log_probs
    adv = batch.advantages  # type: ignore[attr-defined]
    ret = batch.returns  # type: ignore[attr-defined]

    log_probs, entropy, values = policy.evaluate_actions(obs, mask, act, z, mf)
    ratio = torch.exp(log_probs - old_lp)
    surr1 = ratio * adv
    surr2 = torch.clamp(ratio, 1.0 - clip_coef, 1.0 + clip_coef) * adv
    policy_loss = -torch.min(surr1, surr2).mean()
    value_loss = 0.5 * ((values - ret) ** 2).mean()
    entropy_loss = -entropy.mean()
    loss = policy_loss + vf_coef * value_loss + ent_coef * entropy_loss

    aux_bce = torch.tensor(0.0, device=obs.device, dtype=torch.float32)
    if (
        float(aux_exit_coef) > 0.0
        and batch.aux_targets is not None
        and getattr(policy, "_use_aux_exit", False)
    ):
        tgt = batch.aux_targets
        if isinstance(policy, FlatActorCritic):
            logit = policy.aux_exit_logit(obs)
        elif isinstance(policy, HierarchicalActorCritic):
            if batch.manager_z is None:
                raise ValueError("aux exit on hierarchical policy requires manager_z")
            zc = batch.manager_z.clamp(min=0, max=policy.num_modes - 1)
            logit = policy.aux_exit_logit(obs, zc)
        else:
            logit = None
        if logit is not None:
            aux_bce = F.binary_cross_entropy_with_logits(logit, tgt)
            loss = loss + float(aux_exit_coef) * aux_bce

    with torch.no_grad():
        approx_kl = float((old_lp - log_probs).mean().item())
        clip_frac = float((torch.abs(ratio - 1.0) > clip_coef).float().mean().item())
    metrics = {
        "loss": float(loss.item()),
        "policy_loss": float(policy_loss.item()),
        "value_loss": float(value_loss.item()),
        "entropy": float((-entropy_loss).item()),
        "approx_kl": approx_kl,
        "clip_frac": clip_frac,
        "aux_bce": float(aux_bce.item()),
    }
    return loss, metrics


def attach_gae_to_batch(
    batch: RolloutBatch,
    *,
    gamma: float,
    lam: float,
    next_value: float,
    normalize_adv: bool = True,
) -> RolloutBatch:
    adv, ret = compute_gae(
        batch.rewards,
        batch.old_values,
        batch.dones,
        gamma=gamma,
        lam=lam,
        next_value=next_value,
    )
    if normalize_adv and adv.numel() > 1:
        adv = (adv - adv.mean()) / (adv.std(unbiased=False) + 1e-8)
    batch.advantages = adv  # type: ignore[attr-defined]
    batch.returns = ret  # type: ignore[attr-defined]
    return batch


def ppo_update(
    batch: RolloutBatch,
    policy: nn.Module,
    optimizer: optim.Optimizer,
    *,
    epochs: int,
    minibatch_size: int,
    clip_coef: float,
    vf_coef: float,
    ent_coef: float,
    max_grad_norm: float,
    aux_exit_coef: float = 0.0,
) -> dict[str, float]:
    """Multiple epochs of minibatch PPO on one stacked rollout."""
    T = batch.actions.shape[0]
    if T == 0:
        raise ValueError("empty batch")
    device = batch.obs_features.device
    idx = torch.arange(T, device=device)

    agg: dict[str, list[float]] = {}
    for _ in range(epochs):
        perm = idx[torch.randperm(T, device=device)]
        for start in range(0, T, minibatch_size):
            mb = perm[start : start + minibatch_size]
            if mb.numel() == 0:
                continue
            sub = RolloutBatch(
                obs_features=batch.obs_features[mb],
                action_mask=batch.action_mask[mb],
                actions=batch.actions[mb],
                rewards=batch.rewards[mb],
                dones=batch.dones[mb],
                old_log_probs=batch.old_log_probs[mb],
                old_values=batch.old_values[mb],
                manager_z=batch.manager_z[mb] if batch.manager_z is not None else None,
                old_manager_log_probs=(
                    batch.old_manager_log_probs[mb]
                    if batch.old_manager_log_probs is not None
                    else None
                ),
                manager_fired=batch.manager_fired[mb] if batch.manager_fired is not None else None,
                aux_targets=batch.aux_targets[mb] if batch.aux_targets is not None else None,
            )
            sub.advantages = batch.advantages[mb]  # type: ignore[attr-defined]
            sub.returns = batch.returns[mb]  # type: ignore[attr-defined]
            loss, m = ppo_losses(
                sub,
                policy,
                clip_coef=clip_coef,
                vf_coef=vf_coef,
                ent_coef=ent_coef,
                aux_exit_coef=aux_exit_coef,
            )
            optimizer.zero_grad(set_to_none=True)
            loss.backward()
            nn.utils.clip_grad_norm_(policy.parameters(), max_grad_norm)
            optimizer.step()
            for k, v in m.items():
                agg.setdefault(k, []).append(v)
    return {k: float(sum(v) / max(len(v), 1)) for k, v in agg.items()}
