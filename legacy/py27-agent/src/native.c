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

#define MAX_TYPES 128
typedef struct { char name[96]; uint64_t count; uint64_t shallow; } TypeCount;
static int agent_fd = -1;
static pid_t owner_pid = 0;
static unsigned long dropped = 0;
static char endpoint[108] = {0};
static double monotonic_seconds(void) { struct timespec t; clock_gettime(CLOCK_MONOTONIC, &t); return t.tv_sec + t.tv_nsec / 1e9; }
static void reset_socket(void) { if (agent_fd >= 0) close(agent_fd); agent_fd = -1; owner_pid = getpid(); }
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
    strncpy(address.sun_path, endpoint, sizeof(address.sun_path)-1);
    written = sendto(agent_fd, data, (size_t)length, MSG_DONTWAIT | MSG_NOSIGNAL, (struct sockaddr*)&address, sizeof(address));
    if (written != length) { dropped++; Py_RETURN_FALSE; }
    Py_RETURN_TRUE;
}
static PyObject *shutdown_agent(PyObject *self, PyObject *args) { (void)self;(void)args;reset_socket();endpoint[0]=0;Py_RETURN_NONE; }
static PyObject *health(PyObject *self, PyObject *args) { (void)self;(void)args;return Py_BuildValue("{s:l,s:k}", "pid", (long)getpid(), "dropped", dropped); }
static PyObject *lab_drain(PyObject *self, PyObject *args) {
    typedef size_t (*drain_fn)(void*,size_t,uint64_t*);
    drain_fn drain; PyObject *data; int maximum=16384; size_t size; uint64_t lost=0; (void)self;
    if (!PyArg_ParseTuple(args,"|i",&maximum)) return NULL;
    if (maximum<1||maximum>16384) { PyErr_SetString(PyExc_ValueError,"Lab drain budget 1..16384 events");return NULL; }
    drain=(drain_fn)dlsym(RTLD_DEFAULT,"_PyLeakScope_Drain");
    if (!drain) { PyErr_SetString(PyExc_RuntimeError,"This interpreter has no verified LeakScope Lab hooks");return NULL; }
    data=PyString_FromStringAndSize(NULL,(Py_ssize_t)maximum*56);if(!data)return NULL;
    size=drain(PyString_AS_STRING(data),(size_t)maximum*56,&lost);
    if(_PyString_Resize(&data,(Py_ssize_t)size)<0)return NULL;
    return Py_BuildValue("NK",data,(unsigned long long)lost);
}
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
    {"abi",abi,METH_NOARGS,"Compiled ABI fingerprint"},{"initialize",initialize,METH_VARARGS,"Configure a nonblocking local endpoint"},
    {"send",send_packet,METH_VARARGS,"Send one bounded packet; return false on loss"},{"snapshot",snapshot,METH_VARARGS,"Bounded generation-zero type aggregation"},
    {"lab_drain",lab_drain,METH_VARARGS,"Drain experimental object-block records at an explicit safe point"},{"health",health,METH_NOARGS,"Agent loss counters"},{"shutdown",shutdown_agent,METH_NOARGS,"Close native resources"},{NULL,NULL,0,NULL}
};
PyMODINIT_FUNC init_leakscope_native(void) {
    if (strncmp(Py_GetVersion(),"2.7.18",6)!=0 || PY_MAJOR_VERSION!=2 || PY_MINOR_VERSION!=7 || PY_MICRO_VERSION!=18) { PyErr_SetString(PyExc_ImportError,"CPython 2.7.18 required");return; }
    Py_InitModule("_leakscope_native",methods);
}
