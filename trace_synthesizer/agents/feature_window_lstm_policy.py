"""LSTM on trace context: back-window of block features + optional successor + global CFG summary."""

from __future__ import annotations

from typing import Optional

import torch
import torch.nn as nn


class FeatureWindowLstmPolicy(nn.Module):
    """
    Input per step: ``concat(back_window, successor_block_features, global_summary)``.

    No global basic-block id embedding — only ``BlockFeatures`` (fixed ``feat_dim``) and
    static CFG structure via successor targets and optional whole-graph summary.
    """

    def __init__(
        self,
        *,
        window_back: int,
        feat_dim: int,
        max_actions: int,
        succ_feat_slots: int = 0,
        global_summary_dim: int = 0,
        lstm_hidden: int = 64,
    ) -> None:
        super().__init__()
        if window_back < 1:
            raise ValueError("window_back must be >= 1")
        self._window_back = int(window_back)
        self._feat_dim = int(feat_dim)
        self._succ_feat_slots = int(succ_feat_slots)
        self._global_summary_dim = int(global_summary_dim)
        self._max_actions = int(max_actions)
        self._in_dim = (
            self._window_back * self._feat_dim
            + self._succ_feat_slots * self._feat_dim
            + self._global_summary_dim
        )
        self._lstm = nn.LSTM(
            input_size=self._in_dim,
            hidden_size=int(lstm_hidden),
            batch_first=True,
        )
        self._head = nn.Linear(int(lstm_hidden), self._max_actions)
        self._edge_hist = nn.Linear(int(lstm_hidden), int(lstm_hidden))
        self._edge_feat = nn.Linear(self._feat_dim, int(lstm_hidden))
        self._edge_out = nn.Linear(int(lstm_hidden), 1)

    @property
    def max_actions(self) -> int:
        return self._max_actions

    @property
    def window(self) -> int:
        """Alias for checkpoint compatibility."""
        return self._window_back

    @property
    def window_back(self) -> int:
        return self._window_back

    @property
    def feat_dim(self) -> int:
        return self._feat_dim

    @property
    def succ_feat_slots(self) -> int:
        return self._succ_feat_slots

    @property
    def global_summary_dim(self) -> int:
        return self._global_summary_dim

    @property
    def input_dim(self) -> int:
        return self._in_dim

    def forward(
        self,
        x: torch.Tensor,
        *,
        action_mask: Optional[torch.Tensor] = None,
        hx: Optional[tuple[torch.Tensor, torch.Tensor]] = None,
    ) -> tuple[torch.Tensor, tuple[torch.Tensor, torch.Tensor]]:
        """
        x: (batch, seq, input_dim) float32
        action_mask: optional (batch, seq, max_actions) bool True = allowed
        """
        out, hx_out = self._lstm(x, hx)
        if self._succ_feat_slots > 0:
            succ_start = self._window_back * self._feat_dim
            succ_end = succ_start + self._succ_feat_slots * self._feat_dim
            succ_flat = x[:, :, succ_start:succ_end]
            succ = succ_flat.view(
                x.shape[0], x.shape[1], self._succ_feat_slots, self._feat_dim
            )
            if self._succ_feat_slots < self._max_actions:
                pad = torch.zeros(
                    x.shape[0],
                    x.shape[1],
                    self._max_actions - self._succ_feat_slots,
                    self._feat_dim,
                    dtype=x.dtype,
                    device=x.device,
                )
                succ = torch.cat([succ, pad], dim=2)
            elif self._succ_feat_slots > self._max_actions:
                succ = succ[:, :, : self._max_actions, :]
            h = self._edge_hist(out).unsqueeze(2)  # (B,T,1,H)
            e = self._edge_feat(succ)  # (B,T,A,H)
            logits = self._edge_out(torch.tanh(h + e)).squeeze(-1)  # (B,T,A)
        else:
            logits = self._head(out)
        if action_mask is not None:
            logits = logits.masked_fill(~action_mask, -1e9)
        return logits, hx_out
