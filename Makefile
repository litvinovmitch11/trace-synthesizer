BUILD_DIR=build
BUILD_TYPE=Debug

C_COMPILER=clang-21
CXX_COMPILER=clang++-21
CLANG_TIDY=clang-tidy-21
CLANG_FORMAT=clang-format-21

LLVM_INSTALL_DIR="/home/mitchell/dev/llvm/llvm-project/build-install"

NPROC=8

.PHONY: configure build tidy format format-py

configure:
	cmake -B $(BUILD_DIR) \
		-DCMAKE_BUILD_TYPE=$(BUILD_TYPE) \
		-DCMAKE_C_COMPILER=$(C_COMPILER) \
		-DCMAKE_CXX_COMPILER=$(CXX_COMPILER) \
		-DLT_LLVM_INSTALL_DIR=$(LLVM_INSTALL_DIR)

build:
	cmake --build $(BUILD_DIR) -j$(NPROC)

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
