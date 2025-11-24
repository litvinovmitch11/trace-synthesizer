include(FetchContent)

FetchContent_Declare(
    dynamorio_pkg
    URL https://github.com/DynamoRIO/dynamorio/releases/download/release_11.3.0-1/DynamoRIO-Linux-11.3.0.tar.gz
)

FetchContent_GetProperties(dynamorio_pkg)
if(NOT dynamorio_pkg_POPULATED)
    FetchContent_Populate(dynamorio_pkg)
endif()

set(DynamoRIO_DIR "${dynamorio_pkg_SOURCE_DIR}/cmake" CACHE PATH "Path to DynamoRIO" FORCE)
message(STATUS "DynamoRIO setup at: ${DynamoRIO_DIR}")

if(NOT TARGET dynamorio)
    find_package(DynamoRIO REQUIRED CONFIG)
endif()


function(add_dynamorio_client target_name)
    add_library(${target_name} SHARED ${ARGN})
    configure_DynamoRIO_client(${target_name})

    if(CMAKE_BUILD_TYPE STREQUAL "Debug")
        set(DR_LIB_TYPE "debug")
    else()
        set(DR_LIB_TYPE "release")
    endif()

    set(DR_LIB_FULL_PATH "${dynamorio_pkg_SOURCE_DIR}/lib64/${DR_LIB_TYPE}")
    file(RELATIVE_PATH DR_REL_PATH 
        "${CMAKE_CURRENT_BINARY_DIR}"
        "${DR_LIB_FULL_PATH}"
    )
    set_target_properties(${target_name} PROPERTIES
        LINK_FLAGS "-Wl,-rpath,'$ORIGIN/${DR_REL_PATH}'"
        BUILD_WITH_INSTALL_RPATH TRUE
    )
endfunction()
