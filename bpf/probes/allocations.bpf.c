/* Linux x86_64. One independent map set per session/domain. Never blocks a target.
 * Only outermost calls in this allocator domain are emitted. Stacks are captured
 * at entry, before uretprobe return trampolines can destroy the caller context.
 * Pending state is bounded per TID; thread exit removes abandoned calls.
 */
#include "leakscope.h"
struct pending { u64 old_pointer,size,time,caller; long stack; u32 kind,depth; };
/* Wire v1: ten aligned 64-bit words; Rust decodes fields without unsafe casts. */
struct event { u64 version,thread,time,pointer,old_pointer,size; long stack; u64 kind,caller,started; };
struct {__uint(type,1);__uint(max_entries,8192);__type(key,u64);__type(value,struct pending);} calls SEC(".maps");
struct {__uint(type,27);__uint(max_entries,1024*1024);} events SEC(".maps");
/* Cumulative loss counters: allocation, free, correlation/overflow. */
struct {__uint(type,6);__uint(max_entries,3);__type(key,u32);__type(value,u64);} losses SEC(".maps");
struct {__uint(type,7);__uint(max_entries,8192);__type(key,u32);u64 (*value)[32];} stacks SEC(".maps");
/* config[0] TGID, config[1] enabled. Armed only after ALL probes attach. */
struct {__uint(type,2);__uint(max_entries,4);__type(key,u32);__type(value,u64);} config SEC(".maps");
static __attribute__((always_inline)) u64 namespace_thread(void) {
    u32 two=2,three=3;u64 *dev=map_lookup(&config,&two),*ino=map_lookup(&config,&three);
    struct pidns_info info={0};if(!dev||!ino||ns_pid_tgid(*dev,*ino,&info,sizeof(info)))return 0;
    return ((u64)info.tgid<<32)|info.pid;
}
static __attribute__((always_inline)) int enabled(u64 thread) {
    (void)thread;u32 zero=0,one=1;u64 *pid=map_lookup(&config,&zero),*active=map_lookup(&config,&one);
    return pid&&active&&*active&&*pid==(namespace_thread()>>32);
}
static __attribute__((always_inline)) void lost(u32 index) {u64 *v=map_lookup(&losses,&index);if(v)__sync_fetch_and_add(v,1);}
static __attribute__((always_inline)) int emit(u64 thread,u32 kind,u64 ptr,u64 old,u64 size,long stack,u64 caller,u64 started) {
    (void)thread;struct event *e=ring_reserve(&events,sizeof(*e),0);
    if(!e){lost(kind==2?1:0);return 0;}
    e->version=1;e->thread=namespace_thread();e->time=ktime_ns();e->pointer=ptr;e->old_pointer=old;e->size=size;e->stack=stack;e->kind=kind;e->caller=caller;e->started=started;
    ring_submit(e,0);return 0;
}
static __attribute__((always_inline)) int enter(struct pt_regs *ctx,u32 kind,u64 old,u64 size) {
    u64 thread=pid_tgid();if(!enabled(thread))return 0;
    struct pending *p=map_lookup(&calls,&thread);
    if(p){if(p->depth==0xffffffff){lost(2);return 0;}p->depth++;return 0;}
    u64 caller=0;read_user(&caller,sizeof(caller),(void*)ctx->sp);
    struct pending value={.caller=caller,.old_pointer=old,.size=size,.time=ktime_ns(),.stack=get_stackid(ctx,&stacks,1<<8),.kind=kind,.depth=1};
    if(map_update(&calls,&thread,&value,1))lost(2);
    return 0;
}
static __attribute__((always_inline)) int leave(struct pt_regs *ctx) {
    u64 thread=pid_tgid();if(!enabled(thread))return 0;
    struct pending *p=map_lookup(&calls,&thread);if(!p){lost(2);return 0;}
    if(p->depth>1){p->depth--;return 0;}
    struct pending f=*p;map_delete(&calls,&thread);
    return emit(thread,f.kind,ctx->ax,f.old_pointer,f.size,f.stack,f.caller,f.time);
}
SEC("uprobe/malloc") int malloc_enter(struct pt_regs *ctx){return enter(ctx,1,0,ctx->di);}
SEC("uretprobe/malloc") int malloc_leave(struct pt_regs *ctx){return leave(ctx);}
/* Avoid LLVM lowering checked multiplication to unsupported __multi3. */
static __attribute__((noinline)) u64 checked_count(u64 count,u64 item){volatile u64 maximum=~0ULL;if(item&&count>maximum/item)return 0;return count;}
SEC("uprobe/calloc") int calloc_enter(struct pt_regs *ctx){u64 count=checked_count(ctx->di,ctx->si);return enter(ctx,1,0,count*ctx->si);}
SEC("uretprobe/calloc") int calloc_leave(struct pt_regs *ctx){return leave(ctx);}
SEC("uprobe/realloc") int realloc_enter(struct pt_regs *ctx){return enter(ctx,3,ctx->di,ctx->si);}
SEC("uretprobe/realloc") int realloc_leave(struct pt_regs *ctx){return leave(ctx);}
SEC("uprobe/free") int free_enter(struct pt_regs *ctx){u64 t=pid_tgid();if(!enabled(t)||!ctx->di)return 0;struct pending *p=map_lookup(&calls,&t);if(p)return 0;return emit(t,2,ctx->di,0,0,-1,0,0);}
SEC("raw_tp/sched_process_exit") int thread_exit(void *ctx){(void)ctx;u64 t=pid_tgid();map_delete(&calls,&t);return 0;}
SEC("raw_tp/sched_process_exec") int process_exec(void *ctx){(void)ctx;u64 t=pid_tgid();if(!enabled(t))return 0;emit(t,4,0,0,0,-1,0,0);u32 one=1;u64 inactive=0;map_update(&config,&one,&inactive,0);return 0;}
char LICENSE[] SEC("license")="GPL";
