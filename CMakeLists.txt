cmake_minimum_required(VERSION 3.28.3)
project(TraceSynthesizer)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_EXPORT_COMPILE_COMMANDS ON)

include(cmake/SetupDynamoRIO.cmake)
include(cmake/SetupLLVM.cmake)

include_directories(${CMAKE_SOURCE_DIR}/include)
add_subdirectory(src)
