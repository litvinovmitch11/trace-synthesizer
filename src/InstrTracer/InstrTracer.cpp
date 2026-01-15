#include "dr_api.h"
#include <stdio.h>

static file_t log_file;
static void *write_lock; // Мьютекс для потокобезопасности

/* Событие выхода */
static void event_exit(void) {
  dr_mutex_destroy(write_lock);
  dr_close_file(log_file);
  dr_printf("[instr_tracer] Trace saved.\n");
}

/* Функция, вызываемая перед каждой инструкцией (clean call) */
static void log_instruction(app_pc instr_addr) {
  dr_mutex_lock(write_lock);
  // Пишем 64-битный абсолютный адрес инструкции
  dr_write_file(log_file, &instr_addr, sizeof(instr_addr));
  dr_mutex_unlock(write_lock);
}

/* Событие формирования блока: инструментируем каждую инструкцию */
static dr_emit_flags_t event_basic_block(void *drcontext, void *tag,
                                         instrlist_t *bb, bool for_trace,
                                         bool translating) {
  instr_t *instr;

  // Итерируемся по списку инструкций в блоке
  for (instr = instrlist_first(bb); instr != NULL;
       instr = instr_get_next(instr)) {
    // Нас интересуют только инструкции приложения (не мета-инструкции DR)
    if (!instr_is_app(instr))
      continue;

    // Получаем адрес инструкции
    app_pc pc = instr_get_app_pc(instr);
    if (pc == NULL)
      continue;

    // Вставляем "чистый вызов" (clean call) перед инструкцией.
    // Это заставит DR выполнить log_instruction(pc) перед выполнением самой
    // инструкции.
    dr_insert_clean_call(drcontext, bb, instr, (void *)log_instruction,
                         false /* save fp state */, 1 /* 1 argument */,
                         OPND_CREATE_INTPTR(pc));
  }

  return DR_EMIT_DEFAULT;
}

DR_EXPORT void dr_client_main(client_id_t id, int argc, const char *argv[]) {
  // Открываем файл
  log_file = dr_open_file("bb_trace.bin", DR_FILE_WRITE_OVERWRITE);
  if (log_file == INVALID_FILE) {
    dr_printf("[instr_tracer] Error opening log file!\n");
    return;
  }

  write_lock = dr_mutex_create();

  dr_register_exit_event(event_exit);
  dr_register_bb_event(event_basic_block);

  dr_printf("[instr_tracer] Client initialized. Logging EVERY instruction.\n");
}
