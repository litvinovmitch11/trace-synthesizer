# TraceSynthesizer (RU)

## Цель

Репозиторий реализует практический пайплайн синтеза execution traces для ML-задач в компиляторах:

1. Извлечение CFG и профиля из LLVM MIR.
2. Сбор реальных трасс через DynamoRIO.
3. Сбор BB-корпуса для обучения.
4. Обучение CFG-независимой Feature-Window LSTM.
5. Сравнение синтетических и реальных трасс формальными метриками.

Текущий production scope сознательно ограничен этапом baseline + простой LSTM (в соответствии с proposal до RL-части).

## Реализованные компоненты

- LLVM-плагин: `CFGDumper`
- DynamoRIO-трейсер: `InstrTracer`
- Среда CFG: `CFGWalkEnv`
- Бейзлайн: случайное блуждание с вероятностями по PGO-весам
- LSTM-модель: sequence policy по окну признаков
- Сборка датасета: curated multi-program cBench JSONL
- Метрики: KL по распределениям + hot-path overlap
- Визуализация: наложение real/random/LSTM трасс на CFG

## Математическая формализация

### MDP-представление

Синтез трассы по CFG функции:

\[
\mathcal{M} = \langle \mathcal{S}, \mathcal{A}, P, R, \gamma \rangle
\]

- \(s_t \in \mathcal{S}\): текущий BB, контекст пути, (опционально) рекуррентное состояние.
- \(a_t \in \mathcal{A}(s_t)\): выбор одного из допустимых исходящих ребер CFG.
- \(P(s_{t+1}\mid s_t,a_t)\): детерминированный переход по CFG.
- \(R\): функция похожести с реальными трассами (актуальна для RL-этапа).

### KL по посещениям блоков

\[
D_{KL}(p\|q)=\sum_i p_i \log \frac{p_i}{q_i}
\]

где \(p\) — реальное распределение, \(q\) — синтетическое.

### KL по переходам ребер

Та же формула KL применяется к распределению переходов по ребрам.

### Перекрытие hot-path

\[
\text{Jaccard@K} = \frac{|H^{(n)}_{real,K} \cap H^{(n)}_{syn,K}|}{|H^{(n)}_{real,K} \cup H^{(n)}_{syn,K}|}
\]

где \(H^{(n)}_{*,K}\) — top-\(K\) n-грамм пути.

## Основные цели

```bash
make plugins-demo
make random-baseline
make dataset-cbench
make train-lstm
make lstm-eval
make visualize-trace
make compare-traces
```

## Разделение train / eval

- Обучение: cBench-корпус из `benchmarks/external/ctuning_curated.json`.
- Оценка: локальный пример `benchmarks/local/benchmark_complex.cpp`.

Подробное воспроизведение: `docs/ru/REPRODUCTION.md`.
