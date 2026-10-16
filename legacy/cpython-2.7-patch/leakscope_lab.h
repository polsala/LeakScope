/* Experimental CPython object-block instrumentation, compiled into obmalloc.c.
 * No allocator calls, Python callbacks, I/O, blocking locks in hooks. Frame reads require verified current-thread GIL ownership.
 * Counters are process local. A fork resets the ring before recording in the child.
 * This domain overlaps arenas/native memory and must never be added to them.
 */
#include "lab_protocol.h"
#include <frameobject.h>
#include <unistd.h>
#include <time.h>
#include <sys/syscall.h>
#define LS_CAPACITY 16384
typedef ls_lab_event ls_event;
static ls_lab_stack ls_stacks[LS_LAB_STACKS];
static int ls_active=0;
static uint64_t ls_deadline=0,ls_epoch=0;
static unsigned ls_budget=60;
static int ls_stop_reason=0; /* 0 active/manual, 1 duration, 2 buffer */
static __thread int ls_paused=0;
/* Copy current frames only when the exact CPython 2.7 GIL-state check succeeds.
 * This is the same TLS/current-state comparison used by pystate.c. No frame or
 * code pointer survives; PyFrame_GetLineNumber/Addr2Line only read bytecode data.
 * Subinterpreters not matching GILState TLS deliberately receive no attribution.
 */
static uint64_t ls_stack(uint64_t *flags, uint64_t *interpreter) {
    PyThreadState *state=PyGILState_GetThisThreadState();
    PyFrameObject *frame; ls_lab_stack stack; uint64_t hash=1469598103934665603ULL; unsigned i,n;
    if(!state||state!=_PyThreadState_Current){*flags=1;return 0;}
    frame=state->frame;memset(&stack,0,sizeof(stack));*interpreter=(uintptr_t)state->interp;
    while(frame&&stack.depth<LS_LAB_DEPTH){
        ls_lab_frame *out=&stack.frames[stack.depth++];PyCodeObject *code=frame->f_code;
        if(!PyString_Check(code->co_filename)||!PyString_Check(code->co_name)){*flags|=1;return 0;}
        if(!PyString_Check(code->co_lnotab)||PyString_GET_SIZE(code->co_lnotab)>8192){*flags|=4;return 0;}
        if((size_t)PyString_GET_SIZE(code->co_filename)>=sizeof(out->file)||(size_t)PyString_GET_SIZE(code->co_name)>=sizeof(out->function)){*flags|=4;return 0;}
        strncpy(out->file,PyString_AS_STRING(code->co_filename),sizeof(out->file)-1);
        strncpy(out->function,PyString_AS_STRING(code->co_name),sizeof(out->function)-1);
        out->line=PyFrame_GetLineNumber(frame);out->first_line=code->co_firstlineno;
        frame=frame->f_back;
    }
    if(frame)*flags|=2;
    if(!stack.depth){*flags|=1;return 0;}
    for(i=0;i<sizeof(stack.frames);i++){hash^=((unsigned char*)stack.frames)[i];hash*=1099511628211ULL;}
    for(n=0;n<LS_LAB_STACKS;n++){
        i=(unsigned)(hash+n)&(LS_LAB_STACKS-1);
        if(!ls_stacks[i].id){stack.id=i+1;stack.flags=(uint32_t)*flags;ls_stacks[i]=stack;return i+1;}
        if(ls_stacks[i].depth==stack.depth&&!memcmp(ls_stacks[i].frames,stack.frames,sizeof(stack.frames)))return i+1;
    }
    *flags|=4;return 0;
}
static ls_event ls_ring[LS_CAPACITY];
static unsigned long ls_lock = 0;
static uint64_t ls_used = 0, ls_sequence = 0, ls_lost = 0;
static pid_t ls_pid = 0;
static __thread int ls_depth = 0;
static __thread uint64_t ls_started=0;
/* Selected lifetimes only: profiler-created blocks (paused allocation) must not
 * produce an endless stream of unknown frees at later safe points. No eviction.
 * Hash probes are bounded; exhaustion invalidates and stops this capture. */
#define LS_POINTERS 32768
static uintptr_t ls_pointers[LS_POINTERS];
static uint64_t ls_unknown_frees=0;
static int ls_pointer(void *pointer, int insert) {
    uintptr_t p=(uintptr_t)pointer;unsigned start=(unsigned)((p>>4)*11400714819323198485ULL)&(LS_POINTERS-1),i,n,empty=LS_POINTERS;
    if(p<=1)return 0;
    for(n=0;n<64;n++){
        i=(start+n)&(LS_POINTERS-1);
        if(ls_pointers[i]==p){if(!insert)ls_pointers[i]=1;return 1;}
        if(ls_pointers[i]==1&&empty==LS_POINTERS)empty=i;
        if(!ls_pointers[i]){if(insert)ls_pointers[empty==LS_POINTERS?i:empty]=p;return insert?1:0;}
    }
    if(insert&&empty!=LS_POINTERS){ls_pointers[empty]=p;return 1;}
    if(insert){ls_stop_reason=2;__atomic_store_n(&ls_active,0,__ATOMIC_RELEASE);__sync_fetch_and_add(&ls_lost,1);}
    return 0;
}
static void ls_begin_event(void) {struct timespec t;ls_started=0;if(__atomic_load_n(&ls_active,__ATOMIC_ACQUIRE)){clock_gettime(CLOCK_MONOTONIC,&t);ls_started=(uint64_t)t.tv_sec*1000000000ULL+t.tv_nsec;}}
static void ls_record(unsigned kind, void *pointer, void *old_pointer, size_t size) {
    struct timespec ts;
    pid_t pid;
    /* Suppress profiler-created allocations only. Frees and reallocations
     * MUST still be observed: they can release a block selected before pause. */
    if(!__atomic_load_n(&ls_active,__ATOMIC_ACQUIRE)||(ls_paused&&kind==1))return;
    pid=getpid();
    /* Child has one thread. Never inherit a parent lock or allocation state. */
    if (ls_pid != pid) { __atomic_store_n(&ls_active,0,__ATOMIC_RELEASE);ls_epoch=0;ls_lock=0; ls_used=0; ls_sequence=0; ls_lost=0; ls_pid=pid; memset(ls_stacks,0,sizeof(ls_stacks)); return; }
    if (!__sync_bool_compare_and_swap(&ls_lock,0,1)) { __sync_fetch_and_add(&ls_lost,1); return; }
    if(ls_started&&ls_deadline&&ls_started>ls_deadline){ls_stop_reason=1;__atomic_store_n(&ls_active,0,__ATOMIC_RELEASE);__sync_fetch_and_add(&ls_lost,1);__sync_lock_release(&ls_lock);return;}
    if(kind==1&&pointer&&!ls_pointer(pointer,1)){__sync_lock_release(&ls_lock);return;}
    if(kind==2&&!ls_pointer(pointer,0)){if(pointer)ls_unknown_frees++;__sync_lock_release(&ls_lock);return;}
    if(kind==3){
        int selected=ls_pointer(old_pointer,0);
        if(!selected&&ls_paused){__sync_lock_release(&ls_lock);return;}
        /* Failure preserves the previous block; a NULL zero-size outcome is
         * emitted so the lifecycle analyzer can mark its ambiguity. */
        if(!pointer&&size&&selected)ls_pointer(old_pointer,1);
        if(pointer&&!ls_pointer(pointer,1)){__sync_lock_release(&ls_lock);return;}
    }
    ++ls_sequence;
    if (ls_used == LS_CAPACITY) { ls_stop_reason=2;__atomic_store_n(&ls_active,0,__ATOMIC_RELEASE);__sync_fetch_and_add(&ls_lost,1); __sync_lock_release(&ls_lock); return; }
    clock_gettime(CLOCK_MONOTONIC,&ts);
    ls_ring[ls_used].sequence=ls_sequence;
    ls_ring[ls_used].pointer=(uintptr_t)pointer;
    ls_ring[ls_used].old_pointer=(uintptr_t)old_pointer;
    ls_ring[ls_used].size=size;
    ls_ring[ls_used].monotonic_ns=(uint64_t)ts.tv_sec*1000000000ULL+ts.tv_nsec;
    ls_ring[ls_used].thread=(uint64_t)syscall(SYS_gettid);
    ls_ring[ls_used].kind=kind;
    ls_ring[ls_used].pid=(uint32_t)pid;
    ls_ring[ls_used].started_ns=ls_started;
    ls_ring[ls_used].flags=0;ls_ring[ls_used].interpreter=0;
    ls_ring[ls_used].stack=kind==2?0:ls_stack(&ls_ring[ls_used].flags,&ls_ring[ls_used].interpreter);
    ++ls_used;
    __sync_lock_release(&ls_lock);
}
/* Explicit laboratory safe point. Caller owns out and holds the GIL. */
PyAPI_FUNC(size_t) _PyLeakScope_Drain(void *out, size_t capacity, uint64_t *lost) {
    size_t count;
    if (!__sync_bool_compare_and_swap(&ls_lock,0,1)) { __sync_fetch_and_add(&ls_lost,1);*lost=__atomic_load_n(&ls_lost,__ATOMIC_RELAXED);return 0; }
    count=(size_t)ls_used;
    if (count*sizeof(ls_event)>capacity) count=capacity/sizeof(ls_event);
    memcpy(out,ls_ring,count*sizeof(ls_event));
    memmove(ls_ring,ls_ring+count,(ls_used-count)*sizeof(ls_event));
    ls_used-=count;
    *lost=__atomic_load_n(&ls_lost,__ATOMIC_RELAXED);
    __sync_lock_release(&ls_lock);
    return count*sizeof(ls_event);
}

PyAPI_FUNC(unsigned) _PyLeakScope_EventSize(void) { return sizeof(ls_event); }
PyAPI_FUNC(unsigned) _PyLeakScope_Version(void) { return LS_LAB_VERSION; }
PyAPI_FUNC(void) _PyLeakScope_Budget(unsigned seconds) { if(seconds>=1&&seconds<=600)ls_budget=seconds; }
PyAPI_FUNC(int) _PyLeakScope_Control(int active) {
    ls_paused=0;
    if(!active){__atomic_store_n(&ls_active,0,__ATOMIC_RELEASE);return 1;}
    if(ls_pid!=getpid()){ls_lock=0;__atomic_store_n(&ls_active,0,__ATOMIC_RELEASE);}
    if(__atomic_load_n(&ls_active,__ATOMIC_ACQUIRE))return 1;
    if(!__sync_bool_compare_and_swap(&ls_lock,0,1))return 0;
    {struct timespec t;clock_gettime(CLOCK_MONOTONIC,&t);ls_epoch=(uint64_t)t.tv_sec*1000000000ULL+t.tv_nsec;ls_deadline=ls_epoch+(uint64_t)ls_budget*1000000000ULL;ls_sequence=0;ls_used=0;__atomic_store_n(&ls_lost,0,__ATOMIC_RELAXED);ls_stop_reason=0;ls_pid=getpid();ls_unknown_frees=0;memset(ls_pointers,0,sizeof(ls_pointers));memset(ls_stacks,0,sizeof(ls_stacks));}
    __atomic_store_n(&ls_active,1,__ATOMIC_RELEASE);__sync_lock_release(&ls_lock);return 1;
}
PyAPI_FUNC(void) _PyLeakScope_Pause(int pause) { if(pause)ls_paused++;else if(ls_paused)ls_paused--; }
PyAPI_FUNC(size_t) _PyLeakScope_Stack(unsigned id, void *out, size_t size) {
    if(!id||id>LS_LAB_STACKS||size<sizeof(ls_lab_stack))return 0;
    if(!__sync_bool_compare_and_swap(&ls_lock,0,1))return 0;
    memcpy(out,&ls_stacks[id-1],sizeof(ls_lab_stack));__sync_lock_release(&ls_lock);return sizeof(ls_lab_stack);
}

PyAPI_FUNC(uint64_t) _PyLeakScope_Epoch(void) {return ls_pid==getpid()?ls_epoch:0;}
PyAPI_FUNC(int) _PyLeakScope_Active(void) {return ls_pid==getpid()?__atomic_load_n(&ls_active,__ATOMIC_ACQUIRE):0;}

PyAPI_FUNC(int) _PyLeakScope_StopReason(void) {return ls_stop_reason;}
PyAPI_FUNC(uint64_t) _PyLeakScope_UnknownFrees(void) {return ls_unknown_frees;}
