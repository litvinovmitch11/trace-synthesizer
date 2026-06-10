/* No-op implementations for benchmarks that call xopenme under #ifdef XOPENME
 * but also contain unconditional calls (e.g. legacy PGP wrappers). */

void xopenme_init(int a, int b) {
  (void)a;
  (void)b;
}

void xopenme_clock_start(int i) { (void)i; }

void xopenme_clock_end(int i) { (void)i; }

void xopenme_dump_state(void) {}

void xopenme_finish(void) {}
