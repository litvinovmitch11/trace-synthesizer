#include "dr_api.h"

static file_t log_file;
static void *write_lock;
static app_pc mod_start;
static app_pc mod_end;

static void event_exit(void) {
  dr_mutex_destroy(write_lock);
  dr_close_file(log_file);
}

static void clean_call_log_instr(app_pc instr_addr) {
//   unsigned long offset = (unsigned long)(instr_addr - mod_start);

  dr_mutex_lock(write_lock);
  dr_write_file(log_file, &instr_addr, sizeof(instr_addr));
  dr_mutex_unlock(write_lock);
}

static dr_emit_flags_t event_basic_block(void *drcontext, void *tag,
                                         instrlist_t *bb, bool for_trace,
                                         bool translating) {
  for (instr_t *instr = instrlist_first(bb); instr != NULL;
       instr = instr_get_next(instr)) {
    if (!instr_is_app(instr)) {
      continue;
    }
    app_pc addr = instr_get_app_pc(instr);
    if (addr >= mod_start && addr < mod_end) {
      dr_insert_clean_call(drcontext, bb, instr, (void *)clean_call_log_instr,
                           false, 1, OPND_CREATE_INTPTR(addr));
    }
  }

  return DR_EMIT_DEFAULT;
}

DR_EXPORT void dr_client_main(client_id_t id, int argc, const char *argv[]) {
  log_file = dr_open_file("trace.bin", DR_FILE_WRITE_OVERWRITE);
  write_lock = dr_mutex_create();

  module_data_t *main_mod = dr_get_main_module();
  if (main_mod) {
    mod_start = main_mod->start;
    mod_end = main_mod->end;
    dr_printf("Target Module: " PFX " - " PFX "\n", mod_start, mod_end);
    dr_free_module_data(main_mod);
  } else {
    dr_printf("Error receiving target module!\n");
    return;
  }

  dr_register_exit_event(event_exit);
  dr_register_bb_event(event_basic_block);
}
