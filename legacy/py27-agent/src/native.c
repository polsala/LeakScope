/* CPython 2.7.18 only. All entry points hold the GIL. No borrowed object pointer
 * survives a call. The gen0 walk makes no allocations and calls no Python code.
 * Socket writes are bounded/nonblocking and reset before use after a fork.
 */
#define PY_SSIZE_T_CLEAN
#include <Python.h>
#include <sys/socket.h>
#include <sys/un.h>
#include <unistd.h>
#include <fcntl.h>
#include <time.h>
#include <stdint.h>
#include <string.h>
#include <stdio.h>
#include <stddef.h>
#include <dlfcn.h>

#include "profile.h"
#include "../include/lab_protocol.h"

#define MAX_TYPES 128
typedef struct { char name[96]; uint64_t count; uint64_t shallow; } TypeCount;
static int agent_fd = -1;
static pid_t owner_pid = 0;
static unsigned long dropped = 0;
/* Updated only with the GIL held, including failed nonblocking lock attempts.
 * Python += spans bytecodes and can lose increments under thread switching. */
static unsigned long reentrant_dropped = 0, contention_dropped = 0, serialization_dropped = 0;
static char endpoint[108] = {0};
static double monotonic_seconds(void) { struct timespec t; clock_gettime(CLOCK_MONOTONIC, &t); return t.tv_sec + t.tv_nsec / 1e9; }
static void reset_socket(void) { if(owner_pid!=getpid()){dropped=0;reentrant_dropped=0;contention_dropped=0;serialization_dropped=0;} if (agent_fd >= 0) close(agent_fd); agent_fd = -1; owner_pid = getpid(); }
static PyObject *abi(PyObject *self, PyObject *args) {
    char result[160];
    (void)self; (void)args;
    snprintf(result, sizeof(result), "cpython-2.7.18-ucs%d-ptr%zu-gc%zu-trace%d", Py_UNICODE_SIZE * 8, sizeof(void*) * 8, sizeof(PyGC_Head),
#ifdef Py_TRACE_REFS
             1
#else
             0
#endif
    );
    return PyString_FromString(result);
}
static PyObject *initialize(PyObject *self, PyObject *args) {
    const char *path; (void)self;
    if (!PyArg_ParseTuple(args, "s", &path)) return NULL;
    if (strlen(path) >= sizeof(endpoint)) { PyErr_SetString(PyExc_ValueError, "Socket path exceeds Unix socket limit"); return NULL; }
    reset_socket(); strncpy(endpoint, path, sizeof(endpoint)-1); Py_RETURN_NONE;
}
static PyObject *send_packet(PyObject *self, PyObject *args) {
    const char *data; Py_ssize_t length; struct sockaddr_un address; ssize_t written; (void)self;
    if (!PyArg_ParseTuple(args, "s#", &data, &length)) return NULL;
    if (length > 32768) { PyErr_SetString(PyExc_ValueError, "Packet exceeds 32 KiB"); return NULL; }
    if (owner_pid != getpid()) reset_socket();
    if (agent_fd < 0 && endpoint[0]) agent_fd = socket(AF_UNIX, SOCK_DGRAM | SOCK_NONBLOCK | SOCK_CLOEXEC, 0);
    if (agent_fd < 0) { dropped++; Py_RETURN_FALSE; }
    memset(&address, 0, sizeof(address)); address.sun_family = AF_UNIX;
    memcpy(address.sun_path, endpoint, strlen(endpoint)+1);
    written = sendto(agent_fd, data, (size_t)length, MSG_DONTWAIT | MSG_NOSIGNAL, (struct sockaddr*)&address, sizeof(address));
    if (written != length) { dropped++; Py_RETURN_FALSE; }
    Py_RETURN_TRUE;
}
static PyObject *shutdown_agent(PyObject *self, PyObject *args) {
    int (*control)(int);(void)self;(void)args;
    if(PyThreadState_GET()->c_profilefunc==ls_profile_hook){ls_profile_hook(Py_None,PyThreadState_GET()->frame,7,NULL);PyEval_SetProfile(NULL,NULL);}
    ls_profile_suspended=0;ls_profile_control_generation++;
    /* Other threads clear their own hooks at their next safe callback. */
    control=(int(*)(int))dlsym(RTLD_DEFAULT,"_PyLeakScope_Control");if(control)control(0);
    reset_socket();endpoint[0]=0;Py_RETURN_NONE;
}
static PyObject *note_drop(PyObject *self, PyObject *args) {
    int reason; (void)self;
    if (!PyArg_ParseTuple(args,"i",&reason)) return NULL;
    if (owner_pid!=getpid()) reset_socket();
    switch(reason) {
        case 1: reentrant_dropped++; break;
        case 2: contention_dropped++; break;
        case 3: serialization_dropped++; break;
        default: PyErr_SetString(PyExc_ValueError,"Unknown drop reason"); return NULL;
    }
    Py_RETURN_NONE;
}
static PyObject *health(PyObject *self, PyObject *args) {
    (void)self;(void)args;if(owner_pid!=getpid())reset_socket();
    return Py_BuildValue("{s:l,s:k,s:k,s:k,s:k,s:K}","pid",(long)getpid(),
        "dropped",dropped,"reentrant_dropped",reentrant_dropped,
        "contention_dropped",contention_dropped,"serialization_dropped",serialization_dropped,
        "total_dropped",(unsigned long long)dropped+reentrant_dropped+contention_dropped+serialization_dropped);
}

static int lab_api(void) {
    unsigned (*version)(void)=(unsigned(*)(void))dlsym(RTLD_DEFAULT,"_PyLeakScope_Version");
    unsigned (*size)(void)=(unsigned(*)(void))dlsym(RTLD_DEFAULT,"_PyLeakScope_EventSize");
    if(!version||version()!=LS_LAB_VERSION||!size||size()!=sizeof(ls_lab_event)||!dlsym(RTLD_DEFAULT,"_PyLeakScope_Budget")||!dlsym(RTLD_DEFAULT,"_PyLeakScope_Epoch")){PyErr_SetString(PyExc_RuntimeError,"Verified Lab protocol v2 interpreter required");return 0;}return 1;
}
static PyObject *lab_available(PyObject *self,PyObject *args) {
    unsigned (*version)(void)=(unsigned(*)(void))dlsym(RTLD_DEFAULT,"_PyLeakScope_Version");(void)self;(void)args;
    unsigned (*size)(void)=(unsigned(*)(void))dlsym(RTLD_DEFAULT,"_PyLeakScope_EventSize");
    return PyBool_FromLong(version&&version()==LS_LAB_VERSION&&size&&size()==sizeof(ls_lab_event)&&dlsym(RTLD_DEFAULT,"_PyLeakScope_Budget")&&dlsym(RTLD_DEFAULT,"_PyLeakScope_Epoch"));
}
static PyObject *lab_pause(PyObject *self,PyObject *args) {
    int active;void (*pause)(int);(void)self;
    if(!PyArg_ParseTuple(args,"i",&active)||!lab_api())return NULL;
    pause=(void(*)(int))dlsym(RTLD_DEFAULT,"_PyLeakScope_Pause");pause(active);Py_RETURN_NONE;
}
static PyObject *lab_state(PyObject *self,PyObject *args) {
    uint64_t (*epoch)(void);int (*active)(void);(void)self;(void)args;
    if(!lab_api())return NULL;
    epoch=(uint64_t(*)(void))dlsym(RTLD_DEFAULT,"_PyLeakScope_Epoch");active=(int(*)(void))dlsym(RTLD_DEFAULT,"_PyLeakScope_Active");
    return Py_BuildValue("{s:K,s:O}","epoch",(unsigned long long)epoch(),"active",active()?Py_True:Py_False);
}
static PyObject *lab_start(PyObject *self,PyObject *args) {
    int active=1,seconds=60;int (*control)(int);void (*budget)(unsigned);(void)self;
    if(!PyArg_ParseTuple(args,"|ii",&active,&seconds)||!lab_api())return NULL;
    if(seconds<1||seconds>600){PyErr_SetString(PyExc_ValueError,"Lab duration budget 1..600 seconds");return NULL;}
    budget=(void(*)(unsigned))dlsym(RTLD_DEFAULT,"_PyLeakScope_Budget");if(!budget){PyErr_SetString(PyExc_RuntimeError,"Lab budget support missing");return NULL;}budget((unsigned)seconds);
    control=(int(*)(int))dlsym(RTLD_DEFAULT,"_PyLeakScope_Control");if(!control(active)){PyErr_SetString(PyExc_RuntimeError,"Lab control busy; retry at an explicit safe point");return NULL;}Py_RETURN_NONE;
}
static PyObject *lab_drain(PyObject *self, PyObject *args) {
    typedef size_t (*drain_fn)(void*,size_t,uint64_t*);
    drain_fn drain;void (*pause)(int);PyObject *data;int maximum=16384;size_t size;uint64_t lost=0;(void)self;
    if(!PyArg_ParseTuple(args,"|i",&maximum)||!lab_api())return NULL;
    if(maximum<1||maximum>16384){PyErr_SetString(PyExc_ValueError,"Lab drain budget 1..16384 events");return NULL;}
    drain=(drain_fn)dlsym(RTLD_DEFAULT,"_PyLeakScope_Drain");pause=(void(*)(int))dlsym(RTLD_DEFAULT,"_PyLeakScope_Pause");pause(1);
    data=PyString_FromStringAndSize(NULL,(Py_ssize_t)maximum*sizeof(ls_lab_event));if(!data){pause(0);return NULL;}
    size=drain(PyString_AS_STRING(data),(size_t)maximum*sizeof(ls_lab_event),&lost);
    if(_PyString_Resize(&data,(Py_ssize_t)size)<0){pause(0);return NULL;}
    pause(0);return Py_BuildValue("NK",data,(unsigned long long)lost);
}
static PyObject *lab_stacks(PyObject *self,PyObject *args) {
    size_t (*get)(unsigned,void*,size_t);void (*pause)(int);PyObject *list;unsigned i,j;(void)self;(void)args;
    if(!lab_api())return NULL;
    get=(size_t(*)(unsigned,void*,size_t))dlsym(RTLD_DEFAULT,"_PyLeakScope_Stack");
    pause=(void(*)(int))dlsym(RTLD_DEFAULT,"_PyLeakScope_Pause");pause(1);list=PyList_New(0);if(!list){pause(0);return NULL;}
    for(i=1;i<=LS_LAB_STACKS;i++){
        ls_lab_stack stack;PyObject *frames,*item;if(!get(i,&stack,sizeof(stack))||!stack.id)continue;
        frames=PyList_New(0);if(!frames)goto fail;
        for(j=0;j<stack.depth;j++){
            ls_lab_frame *f=&stack.frames[j];item=Py_BuildValue("{s:s,s:s,s:I,s:I,s:s,s:s}","file",f->file,"function",f->function,"line",f->line,"first_line",f->first_line,"module",f->file,"evidence","verified_lab_allocation_frame");
            if(!item||PyList_Append(frames,item)<0){Py_XDECREF(item);Py_DECREF(frames);goto fail;}Py_DECREF(item);
        }
        item=Py_BuildValue("{s:K,s:I,s:N}","id",(unsigned long long)stack.id,"flags",stack.flags,"frames",frames);
        if(!item||PyList_Append(list,item)<0){Py_XDECREF(item);goto fail;}Py_DECREF(item);
    }
    pause(0);return list;
fail:Py_DECREF(list);pause(0);return NULL;
}
#include "lab_snapshot.h"

static PyObject *snapshot(PyObject *self, PyObject *args) {
    int max_objects = 10000, max_ms = 5, partial = 0, used = 0, index;
    uint64_t visited = 0; double begin = monotonic_seconds();
    TypeCount counts[MAX_TYPES]; PyGC_Head *head, *cursor; PyObject *types, *result;
    (void)self;
    if (!PyArg_ParseTuple(args, "|ii", &max_objects, &max_ms)) return NULL;
    if (max_objects < 1 || max_objects > 50000 || max_ms < 1 || max_ms > 50) { PyErr_SetString(PyExc_ValueError, "Snapshot budgets: objects 1..50000, duration 1..50 ms"); return NULL; }
    memset(counts, 0, sizeof(counts)); head = _PyGC_generation0; cursor = head->gc.gc_next;
    /* Only generation zero is exported by CPython. Do not infer private generation
     * array layout or call gc.get_objects(), which builds an unbounded strong-ref list. */
    while (cursor != head) {
        PyObject *object; const char *name; uint64_t shallow;
        if (visited >= (uint64_t)max_objects || ((visited & 63) == 0 && monotonic_seconds()-begin >= max_ms/1000.0)) { partial=1; break; }
        object = (PyObject*)(cursor + 1); name = Py_TYPE(object)->tp_name;
        for (index=0; index<used; index++) if (strncmp(counts[index].name,name,sizeof(counts[index].name)-1)==0) break;
        if (index==used) { if (used==MAX_TYPES) { partial=1; break; } strncpy(counts[used].name,name,sizeof(counts[used].name)-1);used++; }
        shallow = (uint64_t)Py_TYPE(object)->tp_basicsize;
        if (Py_TYPE(object)->tp_itemsize > 0) {
            Py_ssize_t n=Py_SIZE(object); if (n < 0) n=-(n+1); /* conservative estimate for signed-size objects */
            if ((uint64_t)n < UINT64_MAX/(uint64_t)Py_TYPE(object)->tp_itemsize) shallow += (uint64_t)n*(uint64_t)Py_TYPE(object)->tp_itemsize;
        }
        counts[index].count++; counts[index].shallow += shallow; visited++; cursor=cursor->gc.gc_next;
    }
    /* The traversal is complete before creating Python objects. Never call __sizeof__ or repr. */
    types = PyDict_New(); if (!types) return NULL;
    for (index=0;index<used;index++) {
        PyObject *v=Py_BuildValue("{s:K,s:K}","count",(unsigned long long)counts[index].count,"shallow_bytes_estimate",(unsigned long long)counts[index].shallow);
        if (!v || PyDict_SetItemString(types,counts[index].name,v)<0) { Py_XDECREF(v);Py_DECREF(types);return NULL; } Py_DECREF(v);
    }
    result=Py_BuildValue("{s:O,s:K,s:O,s:s,s:d}","types",types,"visited",(unsigned long long)visited,"partial",partial?Py_True:Py_False,"visibility","gc_generation_zero_only","duration_ms",(monotonic_seconds()-begin)*1000);
    Py_DECREF(types);return result;
}
static PyMethodDef methods[] = {
    {"lab_available",lab_available,METH_NOARGS,"Verified Lab v2 hooks available"},
    {"lab_pause",lab_pause,METH_VARARGS,"Suspend this thread during explicit profiler safe points"},
    {"lab_snapshot",lab_snapshot,METH_VARARGS,"Atomically drain records and copy matching Lab frame metadata"},
    {"lab_state",lab_state,METH_NOARGS,"Lab activation epoch and current enabled state"},
    {"lab_start",lab_start,METH_VARARGS,"Explicitly enable or disable experimental object-block hooks"},
    {"lab_stacks",lab_stacks,METH_NOARGS,"Copied allocation-time Python frames from verified Lab hooks"},
    {"context",context_clock,METH_NOARGS,"Native TID and CLOCK_MONOTONIC timestamp"},
    {"profile_reset",profile_reset,METH_NOARGS,"Retire metadata only with no active hooks or pending records"},
    {"profile_start",profile_start,METH_VARARGS,"Opt in this thread; reject existing profilers"},
    {"profile_pause",profile_pause,METH_VARARGS,"Explicit same-thread gaps for profiler safe points"},
    {"profile_stop",profile_stop,METH_NOARGS,"Stop only LeakScope profiling on this thread"},
    {"profile_drain",profile_drain,METH_VARARGS,"Drain bounded function-boundary records at a safe point"},
    {"abi",abi,METH_NOARGS,"Compiled ABI fingerprint"},{"initialize",initialize,METH_VARARGS,"Configure a nonblocking local endpoint"},
    {"note_drop",note_drop,METH_VARARGS,"Record one failed diagnostic attempt atomically under the GIL"},
    {"send",send_packet,METH_VARARGS,"Send one bounded packet; return false on loss"},{"snapshot",snapshot,METH_VARARGS,"Bounded generation-zero type aggregation"},
    {"lab_drain",lab_drain,METH_VARARGS,"Drain experimental object-block records at an explicit safe point"},{"health",health,METH_NOARGS,"Agent loss counters"},{"shutdown",shutdown_agent,METH_NOARGS,"Close native resources"},{NULL,NULL,0,NULL}
};
PyMODINIT_FUNC init_leakscope_native(void) {
    if (strncmp(Py_GetVersion(),"2.7.18",6)!=0 || PY_MAJOR_VERSION!=2 || PY_MINOR_VERSION!=7 || PY_MICRO_VERSION!=18) { PyErr_SetString(PyExc_ImportError,"CPython 2.7.18 required");return; }
    Py_InitModule("_leakscope_native",methods);
}
