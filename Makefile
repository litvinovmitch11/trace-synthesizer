BUILD_DIR=build
OUTPUT_DIR=output
BUILD_TYPE=Debug

C_COMPILER=clang-21
CXX_COMPILER=clang++-21
CLANG_TIDY=clang-tidy-21
CLANG_FORMAT=clang-format-21

# LLVM install prefix for CMake (-DLT_LLVM_INSTALL_DIR=...). Override on the command line or in the environment.
LLVM_INSTALL_DIR ?= /home/mitchell/dev/llvm/llvm-project/build-install

NPROC=8

.PHONY: help configure build clean clean-output test-py check ctuning-bootstrap plugins-demo random-baseline dataset-cbench train-lstm lstm-eval visualize-trace compare-traces

help:
	@echo "trace-synthesizer — common targets"
	@echo "  make configure        — cmake -B \$(BUILD_DIR) (uses LLVM_INSTALL_DIR=\$(LLVM_INSTALL_DIR))"
	@echo "  make build            — compile plugins + DynamoRIO"
	@echo "  make test-py          — poetry run pytest"
	@echo "  make plugins-demo     — demo of LLVM plugins and DynamoRIO tracer"
	@echo "  make random-baseline  — run random walk baseline and compute metrics"
	@echo "  make dataset-cbench   — build JSONL dataset from cbench programs"
	@echo "  make train-lstm       — train Feature-Window LSTM on dataset-cbench"
	@echo "  make lstm-eval        — evaluate trained LSTM and compare with baseline"
	@echo "  make visualize-trace  — visualize CFG and overlay trace (CFG=... FUNC=... [TRACE=...] [OUT=...])"
	@echo "  make compare-traces   — compare two traces (REF=... CAND=... FUNC=... OUT=...)"

configure:
	cmake -B $(BUILD_DIR) \
		-DCMAKE_BUILD_TYPE=$(BUILD_TYPE) \
		-DCMAKE_C_COMPILER=$(C_COMPILER) \
		-DCMAKE_CXX_COMPILER=$(CXX_COMPILER) \
		-DLT_LLVM_INSTALL_DIR=$(LLVM_INSTALL_DIR)

build:
	cmake --build $(BUILD_DIR) -j$(NPROC)

clean:
	cmake --build $(BUILD_DIR) --target clean

test-py:
	poetry run pytest tests/ -q

check: test-py

clean-output:
	rm -rf $(OUTPUT_DIR)/

plugins-demo:
	@chmod +x scripts/run_plugins_demo.sh 2>/dev/null || true
	@./scripts/run_plugins_demo.sh $(ARGS)

random-baseline:
	@chmod +x scripts/run_random_baseline.sh 2>/dev/null || true
	@./scripts/run_random_baseline.sh $(ARGS)

dataset-cbench: ctuning-bootstrap
	@chmod +x scripts/run_dataset_cbench.sh 2>/dev/null || true
	@./scripts/run_dataset_cbench.sh $(ARGS)

train-lstm:
	@chmod +x scripts/run_train_lstm.sh 2>/dev/null || true
	@./scripts/run_train_lstm.sh $(ARGS)

lstm-eval:
	@chmod +x scripts/run_lstm_eval.sh 2>/dev/null || true
	@./scripts/run_lstm_eval.sh $(ARGS)

visualize-trace:
	@chmod +x scripts/visualize_trace.sh 2>/dev/null || true
	@./scripts/visualize_trace.sh

compare-traces:
	@chmod +x scripts/compare_traces.sh 2>/dev/null || true
	@./scripts/compare_traces.sh

ctuning-bootstrap:
	@chmod +x scripts/init_ctuning_submodule.sh 2>/dev/null || true
	@./scripts/init_ctuning_submodule.sh
