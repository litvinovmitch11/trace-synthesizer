#include "dr_api.h"
#include "drmgr.h"

#include <stdint.h>
#include <string.h>

static file_t log_file;
static void *write_lock;

// [start, end) bounds for each target module we log.
#define MAX_TARGET_MODULES 64
static struct {
  app_pc start;
  app_pc end;
} target_bounds[MAX_TARGET_MODULES];
static int target_bounds_count = 0;

static char **target_modules = NULL;
static int target_module_count = 0;

// Ring buffer to batch writes (much lower overhead than per-instruction I/O).
#define BUF_SIZE 8192
static uint64_t trace_buffer[BUF_SIZE];
static int buf_idx = 0;

static void event_exit(void) {
  dr_mutex_lock(write_lock);
  if (buf_idx > 0) {
    dr_write_file(log_file, trace_buffer, sizeof(uint64_t) * buf_idx);
  }
  dr_mutex_unlock(write_lock);

  dr_mutex_destroy(write_lock);
  dr_close_file(log_file);

  if (target_modules != NULL) {
    for (int i = 0; i < target_module_count; i++) {
      dr_global_free(target_modules[i], strlen(target_modules[i]) + 1);
    }
    dr_global_free(target_modules, sizeof(char *) * target_module_count);
  }

  drmgr_exit();
  dr_printf("[InstrTracer] Trace saved.\n");
}

static void clean_call_log(ptr_uint_t offset) {
  dr_mutex_lock(write_lock);
  trace_buffer[buf_idx++] = (uint64_t)offset;
  if (buf_idx >= BUF_SIZE) {
    dr_write_file(log_file, trace_buffer, sizeof(uint64_t) * BUF_SIZE);
    buf_idx = 0;
  }
  dr_mutex_unlock(write_lock);
}

static bool should_instrument_module(const char *module_name) {
  if (target_module_count == 0) {
    return true; // Instrument all modules when no filter is set.
  }

  for (int i = 0; i < target_module_count; i++) {
    if (strcmp(module_name, target_modules[i]) == 0) {
      return true;
    }
  }
  return false;
}

static dr_emit_flags_t event_basic_block(void *drcontext, void *tag,
                                         instrlist_t *bb, instr_t *inst,
                                         bool for_trace, bool translating,
                                         void *user_data) {
  if (!instr_is_app(inst)) {
    return DR_EMIT_DEFAULT;
  }

  app_pc addr = instr_get_app_pc(inst);

  bool is_target = false;
  uint64_t offset = 0;
  for (int i = 0; i < target_bounds_count; i++) {
    if (addr >= target_bounds[i].start && addr < target_bounds[i].end) {
      is_target = true;
      // RVA from module base (matches llvm_bb_addr_map convention).
      offset = (uint64_t)(addr - target_bounds[i].start);
      break;
    }
  }

  if (is_target) {
    // Insert a clean call before each app instruction in this BB.
    dr_insert_clean_call(drcontext, bb, inst, (void *)clean_call_log, false, 1,
                         OPND_CREATE_INTPTR((ptr_uint_t)offset));
  }

  return DR_EMIT_DEFAULT;
}

static void event_module_load(void *drcontext, const module_data_t *info,
                              bool loaded) {
  const char *module_name = dr_module_preferred_name(info);

  if (should_instrument_module(module_name)) {
    if (target_bounds_count < MAX_TARGET_MODULES) {
      target_bounds[target_bounds_count].start = info->start;
      target_bounds[target_bounds_count].end = info->end;
      target_bounds_count++;
      dr_printf("[InstrTracer] Instrumenting module: %s [" PFX "-" PFX "]\n",
                module_name, info->start, info->end);
    }
  }
}

DR_EXPORT void dr_client_main(client_id_t id, int argc, const char *argv[]) {
  dr_set_client_name("TraceSynthesizer InstrTracer",
                     "http://dynamorio.org/issues");

  const char *trace_out = "trace.bin";

  target_modules = (char **)dr_global_alloc(sizeof(char *) * argc);

  for (int i = 1; i < argc; i++) {
    if (strcmp(argv[i], "-o") == 0 && i + 1 < argc) {
      trace_out = argv[i + 1];
      i++;
    } else {
      size_t len = strlen(argv[i]) + 1;
      target_modules[target_module_count] = (char *)dr_global_alloc(len);
      strncpy(target_modules[target_module_count], argv[i], len);
      dr_printf("[InstrTracer] Target module: %s\n",
                target_modules[target_module_count]);
      target_module_count++;
    }
  }

  log_file = dr_open_file(trace_out, DR_FILE_WRITE_OVERWRITE);
  write_lock = dr_mutex_create();

  drmgr_init();
  drmgr_register_module_load_event(event_module_load);
  drmgr_register_bb_instrumentation_event(NULL, event_basic_block, NULL);
  dr_register_exit_event(event_exit);
}
