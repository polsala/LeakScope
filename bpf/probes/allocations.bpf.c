/* Experimental probes: compiled, NOT attached by the production sensor.
 * A loader must validate identity, symbol coverage and all entry/return pairs.
 * Never independently sample allocation and free records for survivor totals.
 */
#include "leakscope.h"
struct frame {u64 old_pointer,size;u32 kind,pad;};
struct pending {struct frame frames[8];u32 depth,overflow;};
struct event {u64 thread,time,pointer,old_pointer,size;long stack;u32 kind,flags;};
struct {__uint(type,1);__uint(max_entries,8192);__type(key,u64);__type(value,struct pending);} calls SEC(".maps");
struct {__uint(type,27);__uint(max_entries,8*1024*1024);} events SEC(".maps");
struct {__uint(type,6);__uint(max_entries,3);__type(key,u32);__type(value,u64);} losses SEC(".maps");
struct {__uint(type,7);__uint(max_entries,8192);__type(key,u32);u64 (*value)[32];} stacks SEC(".maps");
const volatile u32 target_tgid=0;
static __attribute__((always_inline)) void lost(u32 index){u64 *v=map_lookup(&losses,&index);if(v)__sync_fetch_and_add(v,1);}
static __attribute__((always_inline)) int emit(void *ctx,u32 kind,u64 ptr,u64 old,u64 size){
    struct event *e=ring_reserve(&events,sizeof(*e),0);
    if(!e){lost(kind==2?1:0);return 0;}
    e->thread=pid_tgid();e->time=ktime_ns();e->pointer=ptr;e->old_pointer=old;e->size=size;e->kind=kind;e->flags=0;
    e->stack=get_stackid(ctx,&stacks,1<<8);if(e->stack<0)e->flags|=1;
    ring_submit(e,0);return 0;
}
static __attribute__((always_inline)) int enter(u32 kind,u64 old,u64 size){
    u64 thread=pid_tgid();struct pending zero={0};struct pending *p;
    if((thread>>32)!=target_tgid)return 0;
    p=map_lookup(&calls,&thread);if(!p){map_update(&calls,&thread,&zero,1);p=map_lookup(&calls,&thread);if(!p){lost(2);return 0;}}
    if(p->depth>=8){p->overflow++;lost(2);return 0;}
    p->frames[p->depth].old_pointer=old;p->frames[p->depth].size=size;p->frames[p->depth].kind=kind;p->depth++;return 0;
}
static __attribute__((always_inline)) int leave(struct pt_regs *ctx){
    u64 thread=pid_tgid();struct pending *p=map_lookup(&calls,&thread);struct frame f;
    if((thread>>32)!=target_tgid)return 0;
    if(!p){lost(2);return 0;}if(p->overflow){p->overflow--;return 0;}
    if(!p->depth||p->depth>8){lost(2);map_delete(&calls,&thread);return 0;}
    p->depth--;f=p->frames[p->depth];
    /* Only emit the outermost allocator layer. Python-block probes require
     * a separate domain/instance; they cannot be added to native heap totals. */
    if(p->depth==0){map_delete(&calls,&thread);return emit(ctx,f.kind,ctx->ax,f.old_pointer,f.size);}return 0;
}
SEC("uprobe/malloc") int malloc_enter(struct pt_regs *ctx){return enter(1,0,ctx->di);}
SEC("uretprobe/malloc") int malloc_leave(struct pt_regs *ctx){return leave(ctx);}
/* Avoid LLVM lowering 64-bit multiply-overflow idioms to unsupported __multi3. */
static __attribute__((noinline)) u64 checked_calloc_size(u64 count,u64 item){volatile u64 maximum=~0ULL;if(item&&count>maximum/item){lost(2);return 0;}return count;}
SEC("uprobe/calloc") int calloc_enter(struct pt_regs *ctx){u64 count=checked_calloc_size(ctx->di,ctx->si);return enter(1,0,count*ctx->si);}
SEC("uretprobe/calloc") int calloc_leave(struct pt_regs *ctx){return leave(ctx);}
SEC("uprobe/realloc") int realloc_enter(struct pt_regs *ctx){return enter(3,ctx->di,ctx->si);}
SEC("uretprobe/realloc") int realloc_leave(struct pt_regs *ctx){return leave(ctx);}
SEC("uprobe/free") int free_enter(struct pt_regs *ctx){u64 t=pid_tgid();if((t>>32)!=target_tgid||!ctx->di)return 0;struct pending *p=map_lookup(&calls,&t);if(p&&p->depth)return 0;return emit(ctx,2,ctx->di,0,0);}
char LICENSE[] SEC("license")="GPL";
