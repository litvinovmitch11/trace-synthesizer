include(FetchContent)

set(FETCHCONTENT_QUIET OFF)
FetchContent_Declare(
    dynamorio
    URL https://github.com/DynamoRIO/dynamorio/releases/download/release_11.3.0-1/DynamoRIO-Linux-11.3.0.tar.gz
    GIT_PROGRESS ON
)
FetchContent_MakeAvailable(dynamorio)

set(DynamoRIO_DIR "${dynamorio_SOURCE_DIR}/cmake" CACHE PATH "Path to DynamoRIO" FORCE)
