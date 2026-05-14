/* Minimal declarations for ctuning benchmarks that include <xopenme.h>
 * without linking the full Collective Mind runtime. */

#ifndef XOPENME_H
#define XOPENME_H

void xopenme_init(int, int);
void xopenme_clock_start(int);
void xopenme_clock_end(int);
void xopenme_dump_state(void);
void xopenme_finish(void);

#endif
