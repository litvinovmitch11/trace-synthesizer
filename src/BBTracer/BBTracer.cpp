#include "dr_api.h"
#include <stdio.h>

/* Файл для записи трейса */
static file_t log_file;

/* Событие выхода: закрываем файл */
static void event_exit(void) {
    dr_close_file(log_file);
    dr_printf("[bb_tracer] Trace saved.\n");
}

/* Событие выполнения блока: пишем его смещение */
static dr_emit_flags_t event_basic_block(void *drcontext, void *tag, instrlist_t *bb,
                                         bool for_trace, bool translating) {
    // Получаем информацию о модуле, чтобы писать смещение, а не абс. адрес (для ASLR)
    module_data_t *mod = dr_lookup_module((app_pc)tag);
    if (mod != NULL) {
        // Фильтруем: пишем только если это наш app_bin (можно настроить по имени)
        // Для простоты пишем всё, фильтрацию сделаем в Python, 
        // или можно проверять if (strstr(dr_module_preferred_name(mod), "app_bin"))
        
        // Пишем адрес начала блока в бинарном виде (для скорости)
        // Формат: uint64_t absolute_addr
        app_pc addr = (app_pc)tag;
        dr_write_file(log_file, &addr, sizeof(addr));
        
        dr_free_module_data(mod);
    }
    
    // Возвращаем DR_EMIT_DEFAULT, чтобы код выполнялся как обычно
    return DR_EMIT_DEFAULT;
}

DR_EXPORT void dr_client_main(client_id_t id, int argc, const char *argv[]) {
    // Открываем файл для записи
    log_file = dr_open_file("bb_trace.bin", DR_FILE_WRITE_OVERWRITE);
    if (log_file == INVALID_FILE) {
        dr_printf("[bb_tracer] Error opening log file!\n");
        return;
    }

    // Регистрируем события
    dr_register_exit_event(event_exit);
    dr_register_bb_event(event_basic_block);
    
    dr_printf("[bb_tracer] Client initialized. Writing to bb_trace.bin\n");
}
