/* Minimal Linux x86_64 BPF definitions: no dependency on a generated vmlinux.h. */
#ifndef LEAKSCOPE_BPF_H
#define LEAKSCOPE_BPF_H
typedef unsigned long long u64;
typedef unsigned int u32;
#define SEC(name) __attribute__((section(name), used))
#define __uint(name, val) int (*name)[val]
#define __type(name, val) val *name
struct pt_regs {u64 r15,r14,r13,r12,bp,bx,r11,r10,r9,r8,ax,cx,dx,si,di,orig_ax,ip,cs,flags,sp,ss;};
static void *(*map_lookup)(void*,const void*)=(void*)1;
static long (*map_update)(void*,const void*,const void*,u64)=(void*)2;
static long (*map_delete)(void*,const void*)=(void*)3;
static u64 (*ktime_ns)(void)=(void*)5;
static u64 (*pid_tgid)(void)=(void*)14;
static long (*get_stackid)(void*,void*,u64)=(void*)27;
static void *(*ring_reserve)(void*,u64,u64)=(void*)131;
static void (*ring_submit)(void*,u64)=(void*)132;
#endif
