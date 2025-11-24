// TODO: just for debug

#include "dr_api.h"
#include "drmgr.h"
#include "drutil.h"

static file_t logfile;
static app_pc exe_start;
static app_pc exe_end;

static dr_emit_flags_t event_bb_insert(void *drcontext, void *tag, instrlist_t *bb,
                                       instr_t *instr, bool for_trace,
                                       bool translating, void *user_data) {
    if (!drmgr_is_first_instr(drcontext, instr)) 
        return DR_EMIT_DEFAULT;

    app_pc pc = instr_get_app_pc(instr);

    if (exe_start == NULL) 
        return DR_EMIT_DEFAULT;

    // Check if instruction is in main executable
    if (pc >= exe_start && pc < exe_end) {
        // Calculate RVA (Relative Virtual Address)
        ptr_uint_t offset = (ptr_uint_t)(pc - exe_start);
        
        // Write to file - FIXED: use dr_write_file instead of dr_fprintf for better reliability
        char buffer[32];
        int len = dr_snprintf(buffer, sizeof(buffer), "%lx\n", offset);
        if (len > 0) {
            dr_write_file(logfile, buffer, len);
        }
        
        // Also print to console for debugging
        dr_printf("BB: %lx\n", offset);
    }
    return DR_EMIT_DEFAULT;
}

static void event_module_load(void *drcontext, const module_data_t *info, bool loaded) {
    module_data_t *main_mod = dr_get_main_module();
    
    if (main_mod != NULL) {
        if (info->start == main_mod->start) {
            exe_start = info->start;
            exe_end = info->end;
            dr_printf("Main executable: %s [%p - %p]\n", 
                      info->full_path, exe_start, exe_end);
            
            // Debug: check if file is valid
            if (logfile == INVALID_FILE) {
                dr_printf("ERROR: logfile is invalid!\n");
            } else {
                dr_printf("Logfile is ready\n");
            }
        }
        dr_free_module_data(main_mod);
    }
}

static void event_exit(void) {
    dr_printf("Tracer exiting...\n");
    if (logfile != INVALID_FILE) {
        dr_close_file(logfile);
        dr_printf("Logfile closed\n");
    } else {
        dr_printf("WARNING: logfile was invalid\n");
    }
    drmgr_exit();
}

DR_EXPORT void dr_client_main(client_id_t id, int argc, const char *argv[]) {
    drmgr_init();
    
    // Try to create file in current directory
    logfile = dr_open_file("trace.log", DR_FILE_WRITE_OVERWRITE);
    if (logfile == INVALID_FILE) {
        // Try with full path
        char cwd[1024];
        if (dr_get_current_directory(cwd, sizeof(cwd))) {
            char full_path[2048];
            dr_snprintf(full_path, sizeof(full_path), "%s/trace.log", cwd);
            logfile = dr_open_file(full_path, DR_FILE_WRITE_OVERWRITE);
            dr_printf("Trying full path: %s\n", full_path);
        }
    }
    
    if (logfile == INVALID_FILE) {
        dr_printf("ERROR: Could not create trace.log file!\n");
        // But continue anyway to see what happens
    } else {
        dr_printf("Successfully opened trace.log file\n");
    }

    drmgr_register_module_load_event(event_module_load);
    drmgr_register_bb_instrumentation_event(NULL, event_bb_insert, NULL);
    dr_register_exit_event(event_exit);
    
    dr_printf("Tracer initialized - waiting for main module...\n");
}
