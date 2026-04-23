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

.PHONY: help configure build clean clean-output tidy format format-py test-py check benchmark-complex ctuning-bootstrap ctuning-rollout production-validation

help:
	@echo "trace-synthesizer — common targets"
	@echo "  make configure   — cmake -B $(BUILD_DIR) (uses LLVM_INSTALL_DIR=$(LLVM_INSTALL_DIR))"
	@echo "  make build       — compile plugins + DynamoRIO"
	@echo "  make test-py     — poetry run pytest"
	@echo "  make check       — test-py (build artifacts check removed)"
	@echo "  poetry run python3 -m trace_synthesizer rollout-lstm — LSTM rollouts"
	@echo "  make benchmark-complex / ctuning-rollout — see README and docs/REPRODUCTION_*.md"
	@echo "  make production-validation — full PGO+DR+LSTM validation (see experiments/pipelines/main_validation/README.md)"

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

tidy:
	@find src/ -type f \( -name "*.c" -o -name "*.cpp" -o -name "*.cc" -o -name "*.cxx" \) \
		-exec $(CLANG_TIDY) -p $(BUILD_DIR) --config-file=".clang-tidy" {} \;

format:
	@find src/ -type f \( -name "*.c" -o -name "*.cpp" -o -name "*.cc" -o -name "*.cxx" \) \
		-exec $(CLANG_FORMAT) -i -style=file:.clang-format {} \;
	@find include/ -type f \( -name "*.h" -o -name "*.hpp" -o -name "*.hh" -o -name "*.hxx" \) \
		-exec $(CLANG_FORMAT) -i -style=file:.clang-format {} \;

format-py:
	poetry run isort trace_synthesizer/ tests/
	poetry run black trace_synthesizer/ tests/

test-py:
	poetry run pytest tests/ -q

check: test-py

clean-output:
	rm -rf $(OUTPUT_DIR)/

# Full benchmark_complex: C++ plugins + DynamoRIO + Python (rollout, metrics).
# ARGS are forwarded to the benchmark binary (same as e2e-pipeline). Example: make benchmark-complex ARGS="foo"
benchmark-complex:
	@chmod +x scripts/run_benchmark_complex.sh 2>/dev/null || true
	@./scripts/run_benchmark_complex.sh $(ARGS)

ctuning-bootstrap:
	@chmod +x scripts/init_ctuning_submodule.sh scripts/bootstrap_ctuning_programs.sh 2>/dev/null || true
	@./scripts/init_ctuning_submodule.sh

# Curated ctuning-programs: submodule init if needed, C pipeline + rollout-random (subset via ONLY=).
ctuning-rollout: ctuning-bootstrap
	@chmod +x scripts/ctuning_full_pipeline_c.sh 2>/dev/null || true
	poetry run python3 -m trace_synthesizer ctuning-rollout $(CTUNING_ARGS)

production-validation:
	@chmod +x scripts/run_production_validation_experiment.sh 2>/dev/null || true
	@./scripts/run_production_validation_experiment.sh
