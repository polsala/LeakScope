/* Independent ground truth for controlled ctypes tests. No profiler events or
 * expected responses are generated here; these are real libc allocations.
 */
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <pthread.h>
#define LIMIT 4096
static void *blocks[LIMIT];
static size_t sizes[LIMIT], used, retained;
static pthread_mutex_t lock = PTHREAD_MUTEX_INITIALIZER;
__attribute__((noinline)) void *leakscope_leak_site(size_t size) {
    void *p = malloc(size);
    if (p) memset(p, 0x35, size);
    return p;
}
__attribute__((noinline)) void leakscope_cleanup_site(size_t size) {
    void *p = malloc(size);
    if (p) { memset(p, 0x63, size); __asm__ volatile("" : : "r"(p) : "memory"); free(p); }
}
int fixture_step(unsigned count, size_t size, unsigned mode) {
    pthread_mutex_lock(&lock);
    for (unsigned i = 0; i < count; ++i) {
        if (mode == 1) { leakscope_cleanup_site(size); continue; }
        if (mode == 3 && used >= 16) { leakscope_cleanup_site(size); continue; }
        if (used >= LIMIT) { pthread_mutex_unlock(&lock); return -1; }
        void *p = leakscope_leak_site(size);
        if (!p) { pthread_mutex_unlock(&lock); return -2; }
        blocks[used] = p; sizes[used] = size; used++; retained += size;
        if (mode == 2) {
            void *next = realloc(p, size * 2);
            if (next) { blocks[used-1] = next; sizes[used-1] = size * 2; retained += size; }
            /* A failed realloc MUST preserve the previous allocation. */
            volatile size_t impossible = SIZE_MAX - 4095;
            next = realloc(blocks[used-1], impossible);
            if (next) { free(next); retained -= sizes[used-1]; blocks[--used] = NULL; }
        }
    }
    pthread_mutex_unlock(&lock); return 0;
}
size_t fixture_bytes(void) { return retained; }
size_t fixture_blocks(void) { return used; }
void fixture_release(void) {
    pthread_mutex_lock(&lock);
    for (size_t i = 0; i < used; ++i) free(blocks[i]);
    used = 0; retained = 0;
    pthread_mutex_unlock(&lock);
}
