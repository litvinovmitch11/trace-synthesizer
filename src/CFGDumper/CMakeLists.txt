add_llvm_library(CFGDumper MODULE
  CFGDumper.cpp
  PLUGIN_TOOL llc
)

if(NOT LLVM_ENABLE_RTTI)
    if(MSVC)
        target_compile_options(CFGDumper PRIVATE "/GR-")
    else()
        target_compile_options(CFGDumper PRIVATE "-fno-rtti")
    endif()
endif()

if(UNIX AND NOT APPLE)
    target_link_options(CFGDumper PRIVATE "-Wl,--unresolved-symbols=ignore-all")
elseif(APPLE)
    target_link_options(CFGDumper PRIVATE "-undefined dynamic_lookup")
endif()
