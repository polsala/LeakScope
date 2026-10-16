#ifndef LEAKSCOPE_LAB_PROTOCOL_H
#define LEAKSCOPE_LAB_PROTOCOL_H
#include <stdint.h>
#define LS_LAB_VERSION 2
#define LS_LAB_DEPTH 8
#define LS_LAB_STACKS 512
typedef struct { char file[192], function[64]; uint32_t line, first_line; } ls_lab_frame;
typedef struct { uint64_t id; uint32_t depth, flags; ls_lab_frame frames[LS_LAB_DEPTH]; } ls_lab_stack;
/* flags: 1=no verified GIL/thread state, 2=truncated stack, 4=table full. */
typedef struct { uint64_t sequence,pointer,old_pointer,size,monotonic_ns,thread; uint32_t kind,pid; uint64_t stack,interpreter,flags,started_ns; } ls_lab_event;
#endif
