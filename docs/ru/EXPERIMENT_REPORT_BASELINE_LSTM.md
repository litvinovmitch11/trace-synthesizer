# Строгий отчёт по экспериментам: Baseline + LSTM

## 1) Цель и объём

Этот документ покрывает 1.5 части из 3, как было запрошено:

- полностью baseline (Random-PGO),
- полностью LSTM-часть (supervised Feature-Window LSTM),
- подробная фиксация архитектуры, признаков, запусков, метрик, графиков и интерпретации.

## 2) Среда и воспроизводимость

- ОС: Linux 6.17.0-1017-oem
- Репозиторий: `trace-synthesizer`
- Дата прогона: 2026-04-23
- Полный пайплайн прогона:
  - `make clean-output`
  - `make random-baseline`
  - `make dataset-cbench`
  - `make train-lstm`
  - `make lstm-eval`

## 3) Архитектура решения (по коду)

### 3.1 Baseline: Random-PGO

Агент выбирает следующий CFG-ребро стохастически, с вероятностями из PGO:

```12:44:trace_synthesizer/agents/random_pgo.py
class RandomPGOAgent:
    """Sample a valid successor index proportional to CFG PGO weights."""
    ...
    def act(self, observation: dict[str, Any], info: dict[str, Any]) -> int:
        bb_id = int(observation["bb_id"][0])
        mask = np.asarray(info["action_mask"], dtype=bool)
        block = self._by_id[bb_id]
        w = normalized_successor_weights(block)
        ...
        p /= total
        return int(self._rng.choice(n, p=p))
```

### 3.2 Среда генерации (CFGWalkEnv)

Среда задаёт действие как индекс successor-а, а observation включает `bb_id`, маску допустимых действий и вектор признаков блока:

```21:73:trace_synthesizer/env/cfg_walk_env.py
class CFGWalkEnv(gym.Env):
    """
    Single-function random walk on the CFG.
    ...
    """
    ...
    self.observation_space = spaces.Dict(
        {
            "bb_id": spaces.Box(...),
            "valid_mask": spaces.MultiBinary(self._padded_out),
            "features": spaces.Box(...),
        }
    )
    self.action_space = spaces.Discrete(self._padded_out)
```

### 3.3 Признаки блока (BlockFeatures)

Используется 5-мерный базовый вектор (без embedding в текущем прогоне):

```16:67:trace_synthesizer/features/block_features.py
@dataclass
class BlockFeatures:
    ...
    instr_count: float
    has_call: float
    out_degree: float
    max_out_prob: float
    mean_out_prob: float
    ...
    @property
    def base_dim(self) -> int:
        return 5
```

### 3.4 LSTM-агент и входной контекст

LSTM получает на каждом шаге конкатенацию:

- окна из `window_back` прошлых векторов блоков,
- признаков successor-слотов (`succ_feat_slots`),
- глобального summary CFG (`global_summary_dim`).

```11:47:trace_synthesizer/agents/feature_window_lstm_policy.py
class FeatureWindowLstmPolicy(nn.Module):
    """
    Input per step: ``concat(back_window, successor_block_features, global_summary)``.
    """
    ...
    self._in_dim = (
        self._window_back * self._feat_dim
        + self._succ_feat_slots * self._feat_dim
        + self._global_summary_dim
    )
    self._lstm = nn.LSTM(...)
    self._head = nn.Linear(int(lstm_hidden), self._max_actions)
```

Контекст действительно строится из истории + successors + global summary:

```191:248:trace_synthesizer/agents/cfg_supervision.py
def trace_context_tensors_for_bb_path(...):
    ...
    in_dim = window_back * fd + succ_feat_slots * fd + gdim
    ...
    for ti in range(t):
        ...
        succ_flat = successor_features_flat(...)
        out[ti] = np.concatenate([back, succ_flat, global_vec], axis=0)
```

Во время rollout LSTM использует hidden-state, action mask и выбор действия (`argmax` в этом прогоне):

```98:139:trace_synthesizer/agents/feature_window_lstm_agent.py
def act(self, observation: dict[str, Any], info: dict[str, Any]) -> int:
    ...
    with torch.no_grad():
        logits, self._hx = self._policy(x, action_mask=mask_t, hx=self._hx)
    logit_vec = logits[0, -1, : self._env_max_actions]
    if self._action_select == "argmax":
        return int(logit_vec.argmax().item())
```

## 4) Датасет и train-конфигурация

### 4.1 Датасет (cBench curated)

- программ: 3
- трасс: 30 (10 на программу)
- функции:
  - `cbench-automotive-bitcount` / `bit_count`
  - `cbench-telecom-crc32` / `main1`
  - `cbench-security-sha` / `sha_stream`

Источник: `output/dataset_cbench/dataset/dataset_index.json`.

### 4.2 Конфиг обучения LSTM

- `window_back = 8`
- `succ_feat_slots = 2`
- `global_summary_dim = 6`
- `feat_dim = 5`
- `max_actions = 2`
- `epochs = 20`
- `final_train_loss = 0.02147`

Источник: `output/train_lstm/report.json`.

## 5) Измерения и результаты

## 5.1 Метрики качества (eval на `benchmark_complex`, функция `main`)

| Метрика | Random-PGO | LSTM |
|---|---:|---:|
| `block_visit_kl` | 0.6113 | 19.5650 |
| `edge_transition_kl` | 0.6407 | 19.3891 |
| `hot_path_ngram_overlap` | 1.0000 | 0.0000 |

Источники:
- `output/random_baseline/results/metrics_random.json`
- `output/lstm_eval/results/metrics_lstm.json`

### 5.2 Поведение rollout

- Random-PGO: `mean_length = 1093.0`
- LSTM: `mean_length = 7.0`

LSTM в текущей конфигурации быстро схлопывается в короткий детерминированный путь.

### 5.3 Времена этапов (wall-clock)

- `random-baseline`: 40.40 s
- `dataset-cbench`: 664.70 s
- `train-lstm`: 15.09 s
- `lstm-eval`: 42.10 s

### 5.4 Скорость синтеза 1000 трасс

- Random synthetic (из `metrics-bench-speed`): 61.78 s
- LSTM synthetic (тайминг rollout): 70.60 s
- Оценка DynamoRIO для 1000 трасс (экстраполяция по 10-run avg):
  - random-блок: 115.48 s
  - lstm-eval-блок: 113.69 s

Итоговый выигрыш synthetic vs DynamoRIO:

- Random: **1.87x**
- LSTM: **1.61x**

## 6) Графики

Все графики и агрегаты лежат в `output/report_assets/`.

- `metrics_baseline_vs_lstm.png`
- `rollout_mean_length.png`
- `dr_run_times.png`
- `stage_wall_time.png`
- `speedup_1000.png`

Сводный машинно-читаемый файл:

- `experiment_summary.json`
- `speed_1000_comparison.json`

## 7) Интерпретация (строго по результатам)

- Baseline на этом eval-случае существенно лучше LSTM по всем quality-метрикам.
- LSTM имеет очень низкий train loss, но сильный domain gap на eval CFG: модель предсказывает короткий фиксированный маршрут, не покрывая реальное распределение путей.
- По времени synthetic генерация уже быстрее DynamoRIO (1.6-1.9x на 1000 трасс), но качество LSTM пока недостаточно.

## 8) Что улучшать дальше в LSTM-блоке

Приоритетные эксперименты:

1. Переключить `rollout-lstm` на `--action-select sample` и повторить метрики.
2. Увеличить разнообразие train-данных (больше программ/функций/трасс).
3. Сделать sweep по `window_back`, `succ_feat_slots`, `epochs`.
4. Добавить embedding-компонент в `BlockFeatures` (IR2Vec/MIR2Vec), не только 5 scalar features.
5. Ввести explicit regularization на покрытие путей (чтобы избежать коллапса в короткий path).

---

Документ собран автоматически и опирается на реальные артефакты текущего прогона в `output/`.
