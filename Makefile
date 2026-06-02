BUILD_DIR=build
OUTPUT_DIR=output
BUILD_TYPE=Debug

C_COMPILER=clang-21
CXX_COMPILER=clang++-21

# LLVM install prefix for CMake (-DLT_LLVM_INSTALL_DIR=...). Override on the command line or in the environment.
LLVM_INSTALL_DIR ?= /home/mitchell/dev/llvm/llvm-project/build-install

NPROC=8

.PHONY: help configure build clean clean-output test-py check exp-diamond exp-sorting exp-smart exp-mutation visualize-trace

help:
	@echo "======================================================================"
	@echo " TraceSynthesizer — Makefile for LLVM Plugins and Experiments"
	@echo "======================================================================"
	@echo ""
	@echo "Build Targets:"
	@echo "  make configure        — Run cmake -B \$(BUILD_DIR) (uses LLVM_INSTALL_DIR)"
	@echo "  make build            — Compile LLVM CFGDumper plugin and DynamoRIO tracer"
	@echo "  make clean            — Clean C++ build artifacts"
	@echo "  make clean-output     — Remove all experiment outputs (\$(OUTPUT_DIR))"
	@echo ""
	@echo "Test Targets:"
	@echo "  make test-py          — Run Python unit tests via pytest"
	@echo "  make check            — Alias for make test-py"
	@echo ""
	@echo "Experiment Targets (End-to-End pipelines):"
	@echo "  make exp-diamond      — Run Experiment 1: Context Dependency (Diamond Problem)"
	@echo "  make exp-mutation     — Run Experiment 2: Basic CFG Mutation"
	@echo "  make exp-sorting      — Run Experiment 3: Complex Loops (Sorting algorithm)"
	@echo "  make exp-smart        — Run Experiment 4: Smart Compiler Mutations (Loop Peeling)"
	@echo "  make exp-opt          — Run Experiment 5: Cross-Optimization Levels (O0 to O3)"
	@echo ""
	@echo "Utilities:"
	@echo "  make visualize-trace  — Visualize CFG and overlay trace (CFG=... FUNC=... [TRACE=...] [OUT=...])"
	@echo ""

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
	rm -rf benchmarks/local/*/out/*
	rm -rf benchmarks/local/*/build_base/*
	rm -rf benchmarks/local/*/build_mutated/*
	rm -rf benchmarks/local/*/build/*

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

visualize-trace:
	@chmod +x scripts/visualize_trace.sh 2>/dev/null || true
	@./scripts/visualize_trace.sh
