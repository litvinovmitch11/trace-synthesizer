if(LT_LLVM_INSTALL_DIR)
    message(STATUS "Using custom LLVM install dir: ${LT_LLVM_INSTALL_DIR}")
    set(LLVM_DIR "${LT_LLVM_INSTALL_DIR}/lib/cmake/llvm")
else()
    message(STATUS "No custom LLVM path provided, searching in system...")
endif()

find_package(LLVM REQUIRED CONFIG)
message(STATUS "Found LLVM ${LLVM_PACKAGE_VERSION}")
message(STATUS "LLVM include dirs: ${LLVM_INCLUDE_DIRS}")
message(STATUS "LLVM library dirs: ${LLVM_LIBRARY_DIRS}")

list(APPEND CMAKE_MODULE_PATH "${LLVM_CMAKE_DIR}")
include(AddLLVM)

add_definitions(${LLVM_DEFINITIONS})
include_directories(${LLVM_INCLUDE_DIRS})
