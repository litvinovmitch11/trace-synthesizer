"""Torch policy stub: block-id embedding + LSTM, masked logits (no training loop)."""

from __future__ import annotations

from typing import Optional

import torch
import torch.nn as nn


class MaskedLstmPolicyStub(nn.Module):
    """
    Maps (bb_id sequence, optional padded features) to logits over max_actions.

    Intended for future RL training; forward() only.
    """

    def __init__(
        self,
        num_blocks: int,
        max_actions: int,
        embed_dim: int = 32,
        lstm_hidden: int = 64,
        *,
        extra_feat_dim: int = 0,
    ) -> None:
        super().__init__()
        self._max_actions = max_actions
        self._embed = nn.Embedding(num_blocks + 1, embed_dim)
        in_dim = embed_dim + extra_feat_dim
        self._lstm = nn.LSTM(
            input_size=in_dim, hidden_size=lstm_hidden, batch_first=True
        )
        self._head = nn.Linear(lstm_hidden, max_actions)

    @property
    def max_actions(self) -> int:
        return self._max_actions

    def forward(
        self,
        bb_ids: torch.Tensor,
        *,
        features: Optional[torch.Tensor] = None,
        action_mask: Optional[torch.Tensor] = None,
        hx: Optional[tuple[torch.Tensor, torch.Tensor]] = None,
    ) -> tuple[torch.Tensor, tuple[torch.Tensor, torch.Tensor]]:
        """
        bb_ids: (batch, seq) int64
        features: optional (batch, seq, feat_dim)
        action_mask: optional (batch, seq, max_actions) bool True = allowed
        Returns (logits, (h, c)) with logits (batch, seq, max_actions).
        """
        emb = self._embed(bb_ids.clamp(min=0, max=self._embed.num_embeddings - 1))
        if features is not None:
            x = torch.cat([emb, features], dim=-1)
        else:
            x = emb
        out, hx_out = self._lstm(x, hx)
        logits = self._head(out)
        if action_mask is not None:
            logits = logits.masked_fill(~action_mask, -1e9)
        return logits, hx_out
