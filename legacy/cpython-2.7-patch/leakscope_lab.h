/* Experimental CPython object-block instrumentation, compiled into obmalloc.c.
 * No allocator calls, Python callbacks, I/O, blocking locks, or stack walks in hooks.
 * Counters are process local. A fork resets the ring before recording in the child.
 * This domain overlaps arenas/native memory and must never be added to them.
 */
#include <stdint.h>
#include <unistd.h>
#include <time.h>
#include <sys/syscall.h>
#define LS_CAPACITY 16384
typedef struct { uint64_t sequence, pointer, old_pointer, size, monotonic_ns, thread; uint32_t kind, pid; } ls_event;
static ls_event ls_ring[LS_CAPACITY];
static unsigned long ls_lock = 0;
static uint64_t ls_used = 0, ls_sequence = 0, ls_lost = 0;
static pid_t ls_pid = 0;
static __thread int ls_depth = 0;
static void ls_record(unsigned kind, void *pointer, void *old_pointer, size_t size) {
    struct timespec ts;
    pid_t pid = getpid();
    /* Child has one thread. Never inherit a parent lock or allocation state. */
    if (ls_pid != pid) { ls_lock=0; ls_used=0; ls_sequence=0; ls_lost=0; ls_pid=pid; }
    if (!__sync_bool_compare_and_swap(&ls_lock,0,1)) { __sync_fetch_and_add(&ls_lost,1); return; }
    ++ls_sequence;
    if (ls_used == LS_CAPACITY) { __sync_fetch_and_add(&ls_lost,1); __sync_lock_release(&ls_lock); return; }
    clock_gettime(CLOCK_MONOTONIC,&ts);
    ls_ring[ls_used].sequence=ls_sequence;
    ls_ring[ls_used].pointer=(uintptr_t)pointer;
    ls_ring[ls_used].old_pointer=(uintptr_t)old_pointer;
    ls_ring[ls_used].size=size;
    ls_ring[ls_used].monotonic_ns=(uint64_t)ts.tv_sec*1000000000ULL+ts.tv_nsec;
    ls_ring[ls_used].thread=(uint64_t)syscall(SYS_gettid);
    ls_ring[ls_used].kind=kind;
    ls_ring[ls_used].pid=(uint32_t)pid;
    ++ls_used;
    __sync_lock_release(&ls_lock);
}
/* Explicit laboratory safe point. Caller owns out and holds the GIL. */
PyAPI_FUNC(size_t) _PyLeakScope_Drain(void *out, size_t capacity, uint64_t *lost) {
    size_t count;
    if (!__sync_bool_compare_and_swap(&ls_lock,0,1)) return 0;
    count=(size_t)ls_used;
    if (count*sizeof(ls_event)>capacity) count=capacity/sizeof(ls_event);
    memcpy(out,ls_ring,count*sizeof(ls_event));
    memmove(ls_ring,ls_ring+count,(ls_used-count)*sizeof(ls_event));
    ls_used-=count;
    *lost=ls_lost;
    __sync_lock_release(&ls_lock);
    return count*sizeof(ls_event);
}
