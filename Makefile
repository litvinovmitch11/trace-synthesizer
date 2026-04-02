BUILD_DIR=build
OUTPUT_DIR=output
BUILD_TYPE=Debug

C_COMPILER=clang-21
CXX_COMPILER=clang++-21
CLANG_TIDY=clang-tidy-21
CLANG_FORMAT=clang-format-21

LLVM_INSTALL_DIR="/home/mitchell/dev/llvm/llvm-project/build-install"

NPROC=8

.PHONY: configure build clean clean-output tidy format format-py cfg-examples trace-examples e2e-pipeline

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
	poetry run isort tools_py/
	poetry run black tools_py/

clean-output:
	rm -rf $(OUTPUT_DIR)/

cfg-examples:
	@for file in examples/*.cpp; do \
		OUT_DIR=$(OUTPUT_DIR) ./scripts/generate_cfg.sh $$file; \
	done

trace-examples:
	@for file in examples/*.cpp; do \
		BASENAME=$$(basename "$$file" .cpp); \
		./scripts/run_tracer.sh output/$$BASENAME.bin $$BASENAME.bin; \
		poetry run python3 tools_py/trace_pipeline.py --cfg output/$$BASENAME.cfg.json --map output/$${BASENAME}_bb_map.txt --trace output/$$BASENAME.trace.bin --out output/$$BASENAME.compressed_trace.json; \
	done

e2e-pipeline:
	@if [ -n "$(FILE)" ]; then \
		echo "Running End-to-End Pipeline for $(FILE)..."; \
		./scripts/full_pipeline.sh $(FILE) $(ARGS); \
	else \
		echo "Running End-to-End Pipeline for all examples..."; \
		for file in examples/*.cpp; do \
			./scripts/full_pipeline.sh $$file $(ARGS); \
		done; \
	fi
