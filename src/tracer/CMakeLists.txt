# Создаем плагин
# add_llvm_pass_plugin - это современный макрос, но для Legacy PM надежнее add_llvm_library MODULE
add_llvm_library(CFGJsonDumper MODULE
  CFGJsonDumper.cpp
  PLUGIN_TOOL llc
)

# Если LLVM собран без RTTI (стандарт), то и плагин должен быть без него.
if(NOT LLVM_ENABLE_RTTI)
    if(MSVC)
        target_compile_options(CFGJsonDumper PRIVATE "/GR-")
    else()
        target_compile_options(CFGJsonDumper PRIVATE "-fno-rtti")
    endif()
endif()

# Разрешаем нерешенные символы, так как они будут в llc при загрузке
if(UNIX AND NOT APPLE)
    target_link_options(CFGJsonDumper PRIVATE "-Wl,--unresolved-symbols=ignore-all")
elseif(APPLE)
    target_link_options(CFGJsonDumper PRIVATE "-undefined dynamic_lookup")
endif()
