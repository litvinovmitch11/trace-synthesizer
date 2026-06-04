BUILD_DIR=build
OUTPUT_DIR=output
BUILD_TYPE=Debug

C_COMPILER=clang-21
CXX_COMPILER=clang++-21

# Lint / format tooling (override on the command line if your binaries differ).
CLANG_FORMAT ?= clang-format-21
CLANG_TIDY ?= clang-tidy-21
PY_DIRS = trace_synthesizer scripts tests
CXX_SOURCES = $(wildcard src/*/*.cpp src/*/*.h)

# LLVM install prefix for CMake (-DLT_LLVM_INSTALL_DIR=...). Override on the command line or in the environment.
LLVM_INSTALL_DIR ?= /home/mitchell/dev/llvm/llvm-project/build-install

NPROC=8

.PHONY: help configure build clean clean-output test-py check lint lint-py lint-cpp format format-py format-cpp exp-all exp-trigger exp-diamond exp-sorting exp-smart exp-mutation exp-opt corpus-demo visualize-trace

help:
	@echo "======================================================================"
	@echo " TraceSynthesizer — Makefile for LLVM Plugins and Experiments"
	@echo "======================================================================"
	@echo ""
	@echo "Build Targets:"
	@echo "  make configure        — Run cmake into build/ (uses LLVM_INSTALL_DIR)"
	@echo "  make build            — Compile LLVM CFGDumper plugin and DynamoRIO tracer"
	@echo "  make clean            — Clean C++ build artifacts"
	@echo "  make clean-output     — Remove all generated experiment outputs"
	@echo ""
	@echo "Test / Lint / Format Targets:"
	@echo "  make test-py          — Run Python unit tests via pytest"
	@echo "  make lint             — Check style: isort + black (--check) + clang-format + clang-tidy"
	@echo "  make format           — Auto-fix style: isort + black + clang-format -i"
	@echo "  make check            — Full CI: make lint + make test-py"
	@echo "                          (sub-targets: lint-py/lint-cpp, format-py/format-cpp)"
	@echo ""
	@echo "Experiment Targets (End-to-End pipelines, map to thesis Section 7):"
	@echo "  make exp-trigger      — 7.2.3 / Table 7.3: State machine, in-domain (PGO/LSTM/Flat/HRL)"
	@echo "  make exp-diamond      — 7.2.4 / Table 7.4: Context dependency (Diamond Problem)"
	@echo "  make exp-mutation     — 7.3.3 / Table 7.5: Zero-shot trigger CFG mutation"
	@echo "  make exp-sorting      — 7.3.5 / Table 7.6: Zero-shot complex loops (Bubble Sort)"
	@echo "  make exp-smart        — 7.4   / Tables 7.7-7.8: Smart mutations (loop peeling/inversion)"
	@echo "  make exp-opt          — 7.5   / Table 7.10: Cross-optimization O0 -> O3"
	@echo "  make exp-all          — Run every experiment above in sequence"
	@echo ""
	@echo "Corpus (experimental, not a thesis result):"
	@echo "  make corpus-demo      — cBench (bitcount + dijkstra) -> dataset -> shared LSTM"
	@echo ""
	@echo "Utilities:"
	@echo "  make visualize-trace  — Visualize CFG and overlay trace (CFG=... FUNC=... [TRACE=...] [OUT=...])"
	@echo ""

configure:
	cmake -B $(BUILD_DIR) \
		-DCMAKE_BUILD_TYPE=$(BUILD_TYPE) \
		-DCMAKE_C_COMPILER=$(C_COMPILER) \
		-DCMAKE_CXX_COMPILER=$(CXX_COMPILER) \
		-DCMAKE_EXPORT_COMPILE_COMMANDS=ON \
		-DLT_LLVM_INSTALL_DIR=$(LLVM_INSTALL_DIR)

build:
	cmake --build $(BUILD_DIR) -j$(NPROC)

clean:
	cmake --build $(BUILD_DIR) --target clean

test-py:
	poetry run pytest tests/ -q

# Style checks (non-mutating). clang-tidy needs build/compile_commands.json (run `make configure`).
lint: lint-py lint-cpp

lint-py:
	poetry run isort --check-only --diff $(PY_DIRS)
	poetry run black --check --diff $(PY_DIRS)

lint-cpp:
	$(CLANG_FORMAT) --dry-run --Werror $(CXX_SOURCES)
	$(CLANG_TIDY) -p $(BUILD_DIR) $(CXX_SOURCES)

# Auto-fix style in place.
format: format-py format-cpp

format-py:
	poetry run isort $(PY_DIRS)
	poetry run black $(PY_DIRS)

format-cpp:
	$(CLANG_FORMAT) -i $(CXX_SOURCES)

check: lint test-py

clean-output:
	rm -rf $(OUTPUT_DIR)/
	rm -rf benchmarks/local/*/out/*
	rm -rf benchmarks/local/*/build_base/*
	rm -rf benchmarks/local/*/build_mutated/*
	rm -rf benchmarks/local/*/build/*

exp-all: exp-trigger exp-diamond exp-mutation exp-sorting exp-smart exp-opt

exp-trigger:
	PYTHONPATH=. poetry run python3 scripts/run_trigger_exp.py

exp-diamond:
	PYTHONPATH=. poetry run python3 scripts/run_diamond_exp.py

exp-mutation:
	PYTHONPATH=. poetry run python3 scripts/run_cross_mutation_exp.py

exp-sorting:
	PYTHONPATH=. poetry run python3 scripts/run_cross_sorting_exp.py

exp-smart:
	PYTHONPATH=. poetry run python3 scripts/run_cross_smart_exp.py

exp-opt:
	PYTHONPATH=. poetry run python3 scripts/run_cross_opt_exp.py

# Experimental: build a small cBench corpus and train the shared LSTM on it.
# Requires: git submodule update --init benchmarks/external/ctuning-programs
corpus-demo:
	poetry run python3 scripts/build_corpus_dataset.py \
		--ids cbench-automotive-bitcount cbench-network-dijkstra \
		--out-dir output/corpus_demo/artifacts --spec-out output/corpus_demo/spec.json
	poetry run python3 scripts/build_multi_program_intra_dataset.py \
		--spec output/corpus_demo/spec.json --out-dir output/corpus_demo/dataset --with-target-context
	poetry run python3 scripts/train_feature_window_lstm.py \
		--dataset-jsonl output/corpus_demo/dataset/cross.train.jsonl --out-stem output/corpus_demo/lstm_corpus

visualize-trace:
	@chmod +x scripts/visualize_trace.sh 2>/dev/null || true
	@./scripts/visualize_trace.sh
