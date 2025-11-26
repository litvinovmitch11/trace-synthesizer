BUILD_DIR=build
BUILD_TYPE=Debug

C_COMPILER=clang-21
CXX_COMPILER=clang++-21
CLANG_TIDY=clang-tidy-21
CLANG_FORMAT=clang-format-21

DUMMY_SRC_DIR=data/cpp_dummy_files
DUMMY_BUILD_DIR=data/build
TRACES_DIR=traces

NPROC=8

all: configure build install format tidy build-dummy get-traces generate-cfgs

configure:
	cmake -B $(BUILD_DIR) -DCMAKE_BUILD_TYPE=$(BUILD_TYPE) -DCMAKE_C_COMPILER=$(C_COMPILER) -DCMAKE_CXX_COMPILER=$(CXX_COMPILER)

build: configure
	cmake --build $(BUILD_DIR) -j$(NPROC)

install:
	poetry install

build-dummy:
	@for file in $(shell find $(DUMMY_SRC_DIR) -name "*.cpp"); do \
		basename=$$(basename $$file .cpp); \
		$(CXX_COMPILER) -no-pie -g -O0 $$file -o $(DUMMY_BUILD_DIR)/$$basename; \
	done

get-traces:
	@for binary in $(shell find $(DUMMY_BUILD_DIR) -type f -executable); do \
		basename=$$(basename $$binary); \
		$(BUILD_DIR)/_deps/dynamorio_pkg-src/bin64/drrun -c $(BUILD_DIR)/src/tracer/libtracer.so -- $$binary; \
	done

generate-cfgs:
	@for trace_file in $(shell find $(TRACES_DIR) -name "trace_*.txt"); do \
		binary_name=$$(basename $$trace_file .txt | sed 's/trace_//'); \
		graph_name=graph_$$binary_name; \
		binary_path=$(DUMMY_BUILD_DIR)/$$binary_name; \
		poetry run python -m tools_py.visualize_cfg $$binary_path $$trace_file $$graph_name; \
	done

tidy:
	$(CLANG_TIDY) -p $(BUILD_DIR) $(shell find src -name "*.cpp") --config-file=.clang-tidy; \

format:
	@find src -name "*.cpp" -exec $(CLANG_FORMAT) -i {} \;
	@find src -name "*.hpp" -exec $(CLANG_FORMAT) -i {} \;
	poetry run black tools_py/
	poetry run isort tools_py/

clean:
	rm -rf $(BUILD_DIR)/* $(DUMMY_BUILD_DIR)/* $(TRACES_DIR)/* 

.PHONY: all configure build install tidy format build-dummy get-traces generate-cfgs clean
