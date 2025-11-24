BUILD_DIR=build
BUILD_TYPE=Debug
C_COMPILER=clang-21
CXX_COMPILER=clang++-21
NPROC=8

all: clean configure build install format

configure:
	cmake -B $(BUILD_DIR) -DCMAKE_BUILD_TYPE=$(BUILD_TYPE) -DCMAKE_C_COMPILER=$(C_COMPILER) -DCMAKE_CXX_COMPILER=$(CXX_COMPILER)

build: configure
	cmake --build $(BUILD_DIR) -j$(NPROC)

install:
	poetry install

format:
	poetry run black .
	poetry run isort .

clean:
	rm -rf $(BUILD_DIR)
