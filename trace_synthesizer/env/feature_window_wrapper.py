"""Observation wrapper that stacks the last N frame features."""

from collections import deque
from typing import Any, Optional

import gymnasium as gym
import numpy as np
from gymnasium import spaces


class FeatureWindowWrapper(gym.Wrapper):
    """
    Maintains a rolling window of the last ``window_back`` feature vectors.
    """

    def __init__(self, env: gym.Env, window_back: int = 1):
        super().__init__(env)
        self._window_back = max(1, int(window_back))

        base_space = env.observation_space
        if (
            not isinstance(base_space, spaces.Dict)
            or "features" not in base_space.spaces
        ):
            raise TypeError("FeatureWindowWrapper requires Dict obs with 'features'")

        base_feat = base_space["features"]
        if not isinstance(base_feat, spaces.Box) or len(base_feat.shape) != 1:
            raise TypeError("features must be 1-D Box")

        self._feat_dim = base_feat.shape[0]
        self._window = deque(maxlen=self._window_back)

        new_dim = self._feat_dim * self._window_back
        self.observation_space = spaces.Dict(
            {
                **{k: base_space[k] for k in base_space.spaces},
                "features": spaces.Box(
                    low=-np.inf, high=np.inf, shape=(new_dim,), dtype=np.float32
                ),
            }
        )

    def _get_obs(self, obs: dict[str, Any]) -> dict[str, np.ndarray]:
        f = np.asarray(obs["features"], dtype=np.float32).reshape(-1)
        if len(self._window) == 0:
            for _ in range(self._window_back):
                self._window.append(f)
        else:
            self._window.append(f)

        out = dict(obs)
        out["features"] = np.concatenate(list(self._window), axis=0)
        return out

    def reset(
        self,
        *,
        seed: Optional[int] = None,
        options: Optional[dict[str, Any]] = None,
    ) -> tuple[dict[str, np.ndarray], dict[str, Any]]:
        self._window.clear()
        obs, info = self.env.reset(seed=seed, options=options)
        return self._get_obs(obs), info

    def step(
        self, action: Any
    ) -> tuple[dict[str, np.ndarray], float, bool, bool, dict[str, Any]]:
        obs, reward, terminated, truncated, info = self.env.step(action)
        # If invalid action, we don't advance the window but we return the same window
        return self._get_obs(obs), reward, terminated, truncated, info
