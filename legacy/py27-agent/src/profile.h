/* Opt-in CPython 2.7.18 profiling, invoked with the GIL by PyEval_SetProfile.
 * No frame/code reference is retained. Metadata is copied into fixed storage.
 * No Python callbacks, socket writes or Python allocations occur in the hook.
 * These are exact FUNCTION BOUNDARIES, not allocation-time Python stacks.
 * All state access holds the GIL. Each thread explicitly opts in; other profilers
 * are rejected rather than overwritten. PID changes reset inherited storage.
 */
#include <frameobject.h>
#include <sys/syscall.h>
#define LS_PROFILE_EVENTS 4096
#define LS_PROFILE_CODES 512
#define LS_PROFILE_DEPTH 16
typedef struct { uintptr_t code; char file[256], function[96]; int first_line; } ls_code;
typedef struct { uint64_t sequence, time, tid, activation; unsigned kind, depth; unsigned codes[LS_PROFILE_DEPTH]; int lines[LS_PROFILE_DEPTH]; } ls_profile_event;
static ls_code ls_codes[LS_PROFILE_CODES];
static unsigned ls_code_slots[LS_PROFILE_CODES*2];
static ls_profile_event ls_profile_ring[LS_PROFILE_EVENTS];
static unsigned ls_code_count=0, ls_profile_used=0;
static uint64_t ls_profile_sequence=0, ls_profile_lost=0, ls_profile_epoch=0,ls_profile_expired=0;
static pid_t ls_profile_pid=0;
static int ls_profile_busy=0;
static __thread uint64_t ls_profile_deadline=0;
static __thread unsigned ls_profile_suspended=0;
static __thread uint64_t ls_profile_activation=0;
static uint64_t ls_profile_control_generation=1;
static __thread uint64_t ls_profile_generation=0;
static uint64_t ls_ns(void) { struct timespec t;clock_gettime(CLOCK_MONOTONIC,&t);return (uint64_t)t.tv_sec*1000000000ULL+t.tv_nsec; }
static void ls_profile_reset(void) {
    memset(ls_code_slots,0,sizeof(ls_code_slots));
    ls_code_count=0;ls_profile_used=0;ls_profile_sequence=0;ls_profile_lost=0;ls_profile_expired=0;
    ls_profile_pid=getpid();ls_profile_epoch=ls_ns();ls_profile_busy=0;
}
static unsigned ls_intern(PyCodeObject *code) {
    unsigned i,slot,n;
    const char *file=PyString_Check(code->co_filename)?PyString_AS_STRING(code->co_filename):"[non-byte filename]";
    const char *name=PyString_Check(code->co_name)?PyString_AS_STRING(code->co_name):"[unknown function]";
    if(!PyString_Check(code->co_filename)||!PyString_Check(code->co_name)){ls_profile_lost++;return 0;}
    if(PyString_GET_SIZE(code->co_filename)>255||PyString_GET_SIZE(code->co_name)>95){ls_profile_lost++;return 0;}
    /* Bounded open-addressed code cache, no strong code references. Copied
     * identity prevents metadata reuse after a freed code address is recycled. */
    slot=(unsigned)(((uintptr_t)code>>4)^((uintptr_t)code>>16))&(LS_PROFILE_CODES*2-1);
    for(n=0;n<LS_PROFILE_CODES*2;n++){
        unsigned id=ls_code_slots[slot];
        if(!id)break;
        i=id-1;
        if(ls_codes[i].code==(uintptr_t)code&&ls_codes[i].first_line==code->co_firstlineno&&
           !strncmp(ls_codes[i].file,file,255)&&!strncmp(ls_codes[i].function,name,95))return id;
        slot=(slot+1)&(LS_PROFILE_CODES*2-1);
    }
    if(ls_code_count==LS_PROFILE_CODES){ls_profile_lost++;return 0;}
    i=ls_code_count++;ls_codes[i].code=(uintptr_t)code;ls_codes[i].first_line=code->co_firstlineno;
    strncpy(ls_codes[i].file,file,255);ls_codes[i].file[255]=0;
    strncpy(ls_codes[i].function,name,95);ls_codes[i].function[95]=0;
    ls_code_slots[slot]=i+1;
    return i+1;
}
static int ls_profile_hook(PyObject *object, PyFrameObject *frame, int what, PyObject *arg) {
    ls_profile_event *event;unsigned depth=0;(void)object;(void)arg;
    if(ls_profile_pid!=getpid()){ls_profile_reset();PyEval_SetProfile(NULL,NULL);return 0;}
    if(ls_profile_generation!=ls_profile_control_generation){ls_profile_lost++;PyEval_SetProfile(NULL,NULL);return 0;}
    if(ls_profile_busy||ls_profile_suspended)return 0;
    if(ls_profile_deadline&&ls_ns()>ls_profile_deadline){
        /* Our sole profile object is Py_None, so clearing this owned hook cannot
         * invoke a user finalizer. The callback holds the GIL. */
        ls_profile_lost++;ls_profile_expired++;PyEval_SetProfile(NULL,NULL);return 0;
    }
    if(what!=PyTrace_CALL&&what!=PyTrace_RETURN&&what!=PyTrace_C_CALL&&what!=PyTrace_C_RETURN&&what!=PyTrace_C_EXCEPTION&&what!=7&&what!=8)return 0;
    ls_profile_sequence++;
    if(ls_profile_used==LS_PROFILE_EVENTS){ls_profile_lost++;PyEval_SetProfile(NULL,NULL);return 0;}
    ls_profile_busy=1;
    event=&ls_profile_ring[ls_profile_used++];memset(event,0,sizeof(*event));
    event->activation=ls_profile_activation;event->sequence=ls_profile_sequence;event->time=ls_ns();event->tid=(uint64_t)syscall(SYS_gettid);event->kind=(unsigned)what;
    while(frame&&depth<LS_PROFILE_DEPTH){
        event->codes[depth]=ls_intern(frame->f_code);
        event->lines[depth]=(PyString_Check(frame->f_code->co_lnotab)&&PyString_GET_SIZE(frame->f_code->co_lnotab)<=8192)?PyFrame_GetLineNumber(frame):0; /* exact at this boundary only */
        depth++;frame=frame->f_back;
    }
    event->depth=depth;if(frame)ls_profile_lost++;
    ls_profile_busy=0;return 0;
}
/* Metadata retirement is explicit and safe only after every hook is disabled
 * and all records are drained. Other interpreter threads are inspected under GIL. */
static PyObject *profile_reset(PyObject *self, PyObject *args) {
    PyInterpreterState *interp;PyThreadState *thread;(void)self;(void)args;
    for(interp=PyInterpreterState_Head();interp;interp=PyInterpreterState_Next(interp))
        for(thread=PyInterpreterState_ThreadHead(interp);thread;thread=PyThreadState_Next(thread))
            if(thread->c_profilefunc==ls_profile_hook){PyErr_SetString(PyExc_RuntimeError,"Disable all LeakScope hooks before retiring metadata");return NULL;}
    if(ls_profile_used){PyErr_SetString(PyExc_RuntimeError,"Drain pending profile records before retiring metadata");return NULL;}
    ls_profile_reset();Py_RETURN_NONE;
}
static PyObject *profile_start(PyObject *self, PyObject *args) {
    PyThreadState *thread=PyThreadState_GET();int seconds=60;(void)self;
    if(!PyArg_ParseTuple(args,"|i",&seconds))return NULL;
    if(seconds<1||seconds>600){PyErr_SetString(PyExc_ValueError,"Profile duration budget 1..600 seconds");return NULL;}
    if(ls_profile_pid!=getpid())ls_profile_reset();
    if(thread->c_profilefunc&&thread->c_profilefunc!=ls_profile_hook){PyErr_SetString(PyExc_RuntimeError,"Existing Python profiler: LeakScope will not overwrite its hook");return NULL;}
    if(thread->c_profilefunc==ls_profile_hook)Py_RETURN_FALSE;
    ls_profile_suspended=0;
    ls_profile_generation=ls_profile_control_generation;
    ls_profile_activation=ls_ns();
    ls_profile_deadline=ls_profile_activation+(uint64_t)seconds*1000000000ULL;
    PyEval_SetProfile(ls_profile_hook,Py_None);ls_profile_hook(Py_None,thread->frame,8,NULL);Py_RETURN_TRUE;
}
/* Explicit gaps prevent profiler serialization/finalizers from inheriting a
 * stale business frame. Only this native thread is suspended, under the GIL. */
static PyObject *profile_pause(PyObject *self,PyObject *args) {
    int pause;PyThreadState *thread=PyThreadState_GET();(void)self;
    if(!PyArg_ParseTuple(args,"i",&pause))return NULL;
    if(thread->c_profilefunc!=ls_profile_hook)Py_RETURN_NONE;
    if(pause){if(!ls_profile_suspended)ls_profile_hook(Py_None,thread->frame,7,NULL);ls_profile_suspended++;}
    else if(ls_profile_suspended){ls_profile_suspended--;if(!ls_profile_suspended)ls_profile_hook(Py_None,thread->frame,8,NULL);}
    Py_RETURN_NONE;
}
static PyObject *profile_stop(PyObject *self, PyObject *args) {
    (void)self;(void)args;
    if(PyThreadState_GET()->c_profilefunc==ls_profile_hook){ls_profile_hook(Py_None,PyThreadState_GET()->frame,7,NULL);PyEval_SetProfile(NULL,NULL);}
    ls_profile_suspended=0;
    Py_RETURN_NONE;
}
static PyObject *context_clock(PyObject *self, PyObject *args) {
    (void)self;(void)args;
    return Py_BuildValue("{s:K,s:K}","monotonic_ns",(unsigned long long)ls_ns(),"thread",(unsigned long long)syscall(SYS_gettid));
}
static PyObject *profile_drain(PyObject *self, PyObject *args) {
    int maximum=32;unsigned i,j,n;PyObject *events,*codes,*result;(void)self;
    if(!PyArg_ParseTuple(args,"|i",&maximum))return NULL;
    if(maximum<1||maximum>64){PyErr_SetString(PyExc_ValueError,"Profile drain budget 1..64");return NULL;}
    if(ls_profile_pid!=getpid())ls_profile_reset();
    ls_profile_busy=1;n=ls_profile_used<(unsigned)maximum?ls_profile_used:(unsigned)maximum;
    events=PyList_New(0);codes=PyList_New(0);
    if(!events||!codes)goto fail;
    for(i=0;i<n;i++){
        ls_profile_event *e=&ls_profile_ring[i];PyObject *frames=PyList_New(0),*item;
        if(!frames)goto fail;
        for(j=0;j<e->depth;j++){
            item=Py_BuildValue("(Ii)",e->codes[j],e->lines[j]);
            if(!item||PyList_Append(frames,item)<0){Py_XDECREF(item);Py_DECREF(frames);goto fail;}Py_DECREF(item);
        }
        item=Py_BuildValue("{s:K,s:K,s:K,s:K,s:I,s:N}","activation",(unsigned long long)e->activation,"sequence",(unsigned long long)e->sequence,"monotonic_ns",(unsigned long long)e->time,"thread",(unsigned long long)e->tid,"event",e->kind,"frames",frames);
        if(!item||PyList_Append(events,item)<0){Py_XDECREF(item);goto fail;}Py_DECREF(item);
    }
    /* Metadata remains bounded and immutable until explicit process reset. Safe
     * point caller sends it in small packets; no frames are held between calls. */
    for(i=0;i<ls_code_count;i++){
        ls_code *c=&ls_codes[i];PyObject *item=Py_BuildValue("{s:I,s:s,s:s,s:i}","id",i+1,"file",c->file,"function",c->function,"first_line",c->first_line);
        if(!item||PyList_Append(codes,item)<0){Py_XDECREF(item);goto fail;}Py_DECREF(item);
    }
    memmove(ls_profile_ring,ls_profile_ring+n,(ls_profile_used-n)*sizeof(ls_profile_event));ls_profile_used-=n;
    result=Py_BuildValue("{s:K,s:K,s:K,s:N,s:N,s:I}","epoch",(unsigned long long)ls_profile_epoch,"lost",(unsigned long long)ls_profile_lost,"expired",(unsigned long long)ls_profile_expired,"events",events,"codes",codes,"remaining",ls_profile_used);
    ls_profile_busy=0;return result;
fail:Py_XDECREF(events);Py_XDECREF(codes);ls_profile_busy=0;return NULL;
}
