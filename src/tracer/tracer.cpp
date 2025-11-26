#include "dr_api.h"
#include "drmgr.h"
#include "drutil.h"

#include <set>
#include <string>

static void *LogMutex;
static file_t Logfile;
static std::set<app_pc> *ExecutedBlocks;
static std::string BinaryName;

static void eventExit(void) {
  dr_mutex_lock(LogMutex);
  dr_fprintf(Logfile, "Trace started\n");
  for (app_pc Addr : *ExecutedBlocks) {
    dr_fprintf(Logfile, "%p\n", Addr);
  }
  dr_fprintf(Logfile, "Done tracing.\n");
  dr_mutex_unlock(LogMutex);

  dr_close_file(Logfile);
  dr_mutex_destroy(LogMutex);
  delete ExecutedBlocks;
  drmgr_exit();
}

static void cleanCall(app_pc InstrAddr) {
  dr_mutex_lock(LogMutex);
  ExecutedBlocks->insert(InstrAddr);
  dr_mutex_unlock(LogMutex);
}

static dr_emit_flags_t eventBbInsert(void *Drcontext, void *Tag,
                                     instrlist_t *Bb, instr_t *Instr,
                                     bool ForTrace, bool Translating,
                                     void *UserData) {
  if (!drmgr_is_first_instr(Drcontext, Instr))
    return DR_EMIT_DEFAULT;

  app_pc InstrAddr = instr_get_app_pc(Instr);
  dr_insert_clean_call(Drcontext, Bb, Instr, (void *)cleanCall, false, 1,
                       OPND_CREATE_INTPTR(InstrAddr));

  return DR_EMIT_DEFAULT;
}

static std::string getBinaryName(const char *Path) {
  std::string FullPath(Path);
  size_t LastSlash = FullPath.find_last_of("/\\");
  if (LastSlash != std::string::npos) {
    return FullPath.substr(LastSlash + 1);
  }
  return FullPath;
}

DR_EXPORT void dr_client_main(client_id_t Id, int Argc, const char *Argv[]) {
  drmgr_init();
  LogMutex = dr_mutex_create();
  ExecutedBlocks = new std::set<app_pc>();

  module_data_t *AppModule = dr_get_main_module();
  BinaryName = getBinaryName(AppModule->names.file_name);
  dr_free_module_data(AppModule);

  char TraceName[128];
  dr_snprintf(TraceName, sizeof(TraceName), "./traces/trace_%s.txt",
              BinaryName.c_str());

  Logfile = dr_open_file(TraceName, DR_FILE_WRITE_OVERWRITE);

  dr_mutex_lock(LogMutex);
  dr_fprintf(Logfile, "Tracing binary: %s\n", BinaryName.c_str());
  dr_fprintf(Logfile, "Command line: ");
  for (int I = 0; I < Argc; I++) {
    dr_fprintf(Logfile, "%s ", Argv[I]);
  }
  dr_fprintf(Logfile, "\n");
  dr_mutex_unlock(LogMutex);

  drmgr_register_bb_instrumentation_event(NULL, eventBbInsert, NULL);
  dr_register_exit_event(eventExit);
}
