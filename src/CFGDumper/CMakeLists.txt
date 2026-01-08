# Создаем плагин
# add_llvm_pass_plugin - это современный макрос, но для Legacy PM надежнее add_llvm_library MODULE
add_llvm_library(CFGDumper MODULE
  CFGDumper.cpp
  PLUGIN_TOOL llc
)

# Если LLVM собран без RTTI (стандарт), то и плагин должен быть без него.
if(NOT LLVM_ENABLE_RTTI)
    if(MSVC)
        target_compile_options(CFGDumper PRIVATE "/GR-")
    else()
        target_compile_options(CFGDumper PRIVATE "-fno-rtti")
    endif()
endif()

# Разрешаем нерешенные символы, так как они будут в llc при загрузке
if(UNIX AND NOT APPLE)
    target_link_options(CFGDumper PRIVATE "-Wl,--unresolved-symbols=ignore-all")
elseif(APPLE)
    target_link_options(CFGDumper PRIVATE "-undefined dynamic_lookup")
endif()
