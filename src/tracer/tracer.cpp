#include "dr_api.h"
#include "drmgr.h"
#include "drutil.h"
#include <algorithm>
#include <cstdint>
#include <map>
#include <string>
#include <vector>

static void *LogMutex;
static file_t Logfile;
static std::vector<app_pc> *ExecutionLog;
static std::string BinaryName;

static app_pc MainBase;
static app_pc MainEnd;

static std::map<app_pc, uint64_t> AddrCounter;
static uint64_t LastPrinted = 0;

static void eventExit(void) {
  dr_mutex_lock(LogMutex);
  dr_fprintf(STDERR, "[DR] Statistics:\n");
  dr_fprintf(STDERR, "[DR]   Log size: %zu\n", ExecutionLog->size());
  dr_fprintf(STDERR, "[DR]   Unique addresses: %zu\n", AddrCounter.size());
  dr_fprintf(STDERR, "[DR]   Top 10 addresses:\n");
  std::vector<std::pair<app_pc, uint64_t>> Sorted(AddrCounter.begin(),
                                                  AddrCounter.end());
  std::sort(Sorted.begin(), Sorted.end(),
            [](auto &A, auto &B) { return A.second > B.second; });

  for (int I = 0; I < 10 && I < Sorted.size(); I++) {
    dr_fprintf(STDERR, "[DR]     %p: %llu\n", Sorted[I].first,
               Sorted[I].second);
  }

  dr_fprintf(Logfile, "Trace started\n");
  for (app_pc Addr : *ExecutionLog) {
    dr_fprintf(Logfile, "%p\n", (void *)Addr);
  }
  dr_fprintf(Logfile, "Done tracing.\n");
  dr_mutex_unlock(LogMutex);

  dr_close_file(Logfile);
  dr_mutex_destroy(LogMutex);
  delete ExecutionLog;
  drmgr_exit();
}

static void cleanCall(app_pc InstrAddr) {
  dr_mutex_lock(LogMutex);
  ExecutionLog->push_back(InstrAddr);
  AddrCounter[InstrAddr]++;
  dr_mutex_unlock(LogMutex);
}

static dr_emit_flags_t eventBbInsert(void *Drcontext, void *Tag,
                                     instrlist_t *Bb, instr_t *Instr,
                                     bool ForTrace, bool Translating,
                                     void *UserData) {
  if (!drmgr_is_first_instr(Drcontext, Instr)) {
    return DR_EMIT_DEFAULT;
  }

  app_pc InstrAddr = instr_get_app_pc(Instr);

  if (InstrAddr < MainBase || InstrAddr >= MainEnd) {
    return DR_EMIT_DEFAULT;
  }

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
  ExecutionLog = new std::vector<app_pc>();

  module_data_t *AppModule = dr_get_main_module();
  if (AppModule) {
    MainBase = AppModule->start;
    MainEnd = AppModule->end;
    BinaryName = getBinaryName(AppModule->names.file_name);
    dr_fprintf(STDERR, "[DR] Main module: %s\n", BinaryName.c_str());
    dr_fprintf(STDERR, "[DR] Main module range: %p - %p\n", MainBase, MainEnd);
    dr_fprintf(STDERR, "[DR] Main module size: %lld bytes\n",
               (long long)(MainEnd - MainBase));

    for (int I = 0; I < AppModule->num_segments; I++) {
      dr_fprintf(STDERR, "[DR] Segment %d: %p - %p (%s)\n", I,
                 AppModule->segments[I].start, AppModule->segments[I].end);
    }

    dr_free_module_data(AppModule);
  } else {
    dr_fprintf(STDERR, "[DR] FATAL: Could not find main module\n");
    return;
  }

  char TraceName[128];
  dr_snprintf(TraceName, sizeof(TraceName), "./traces/trace_%s.txt",
              BinaryName.c_str());
  Logfile = dr_open_file(TraceName, DR_FILE_WRITE_OVERWRITE);
  dr_fprintf(STDERR, "[DR] Writing trace to: %s\n", TraceName);

  drmgr_register_bb_instrumentation_event(NULL, eventBbInsert, NULL);
  dr_register_exit_event(eventExit);
}
