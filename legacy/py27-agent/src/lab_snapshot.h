/* Atomic safe-point snapshot of Lab records AND their copied stack metadata.
 * The GIL serializes legal CPython allocator callers and control changes. Copy
 * native data before any container allocation can run a reentrant GC finalizer.
 * Temporary storage is preallocated; no large stack allocation or frame refs.
 */
static ls_lab_stack lab_snapshot_copies[LS_LAB_STACKS];
static int lab_snapshot_busy=0;
static pid_t lab_snapshot_pid=0;
static PyObject *lab_snapshot(PyObject *self,PyObject *args) {
    size_t (*drain)(void*,size_t,uint64_t*),(*get)(unsigned,void*,size_t);
    int (*active_fn)(void),(*reason_fn)(void),active,reason;
    void (*pause)(int);uint64_t (*epoch_fn)(void),(*unknown_fn)(void),epoch,lost=0,unknown=0;
    PyObject *raw=NULL,*stacks=NULL,*result=NULL;int maximum=2048;size_t size,offset;unsigned i,j;
    unsigned char required[LS_LAB_STACKS]={0};(void)self;
    if(!PyArg_ParseTuple(args,"|i",&maximum)||!lab_api())return NULL;
    if(maximum<1||maximum>16384){PyErr_SetString(PyExc_ValueError,"Lab snapshot budget 1..16384");return NULL;}
    if(lab_snapshot_pid!=getpid()){lab_snapshot_pid=getpid();lab_snapshot_busy=0;}
    if(lab_snapshot_busy){PyErr_SetString(PyExc_RuntimeError,"Reentrant Lab snapshot declined");return NULL;}
    lab_snapshot_busy=1;
    drain=(size_t(*)(void*,size_t,uint64_t*))dlsym(RTLD_DEFAULT,"_PyLeakScope_Drain");
    get=(size_t(*)(unsigned,void*,size_t))dlsym(RTLD_DEFAULT,"_PyLeakScope_Stack");
    pause=(void(*)(int))dlsym(RTLD_DEFAULT,"_PyLeakScope_Pause");
    epoch_fn=(uint64_t(*)(void))dlsym(RTLD_DEFAULT,"_PyLeakScope_Epoch");
    unknown_fn=(uint64_t(*)(void))dlsym(RTLD_DEFAULT,"_PyLeakScope_UnknownFrees");
    pause(1);raw=PyString_FromStringAndSize(NULL,(Py_ssize_t)maximum*sizeof(ls_lab_event));if(!raw)goto fail;
    active_fn=(int(*)(void))dlsym(RTLD_DEFAULT,"_PyLeakScope_Active");reason_fn=(int(*)(void))dlsym(RTLD_DEFAULT,"_PyLeakScope_StopReason");
    epoch=epoch_fn();active=active_fn();reason=reason_fn?reason_fn():0;size=drain(PyString_AS_STRING(raw),(size_t)maximum*sizeof(ls_lab_event),&lost);unknown=unknown_fn?unknown_fn():0;
    for(offset=0;offset+sizeof(ls_lab_event)<=size;offset+=sizeof(ls_lab_event)){
        ls_lab_event event;
        /* PyString data need not have uint64_t alignment. */
        memcpy(&event,PyString_AS_STRING(raw)+offset,sizeof(event));
        if(event.stack&&event.stack<=LS_LAB_STACKS)required[event.stack-1]=1;
    }
    for(i=0;i<LS_LAB_STACKS;i++)if(required[i]){
        if(!get(i+1,&lab_snapshot_copies[i],sizeof(ls_lab_stack))){required[i]=0;lost++;}
    }
    if(_PyString_Resize(&raw,(Py_ssize_t)size)<0)goto fail;
    stacks=PyList_New(0);if(!stacks)goto fail;
    for(i=0;i<LS_LAB_STACKS;i++)if(required[i]){
        ls_lab_stack *stack=&lab_snapshot_copies[i];PyObject *frames=PyList_New(0),*item;
        if(!frames)goto fail;
        for(j=0;j<stack->depth;j++){
            ls_lab_frame *f=&stack->frames[j];
            item=Py_BuildValue("{s:s,s:s,s:s,s:I,s:I,s:s}","file",f->file,"module",f->file,"function",f->function,"line",f->line,"first_line",f->first_line,"evidence","verified_lab_allocation_frame");
            if(!item||PyList_Append(frames,item)<0){Py_XDECREF(item);Py_DECREF(frames);goto fail;}Py_DECREF(item);
        }
        item=Py_BuildValue("{s:K,s:I,s:N}","id",(unsigned long long)stack->id,"flags",stack->flags,"frames",frames);
        if(!item||PyList_Append(stacks,item)<0){Py_XDECREF(item);goto fail;}Py_DECREF(item);
    }
    result=Py_BuildValue("{s:K,s:K,s:K,s:O,s:i}","epoch",(unsigned long long)epoch,"lost",(unsigned long long)lost,"unknown_frees",(unsigned long long)unknown,"active",active?Py_True:Py_False,"stop_reason",reason);
    if(!result||PyDict_SetItemString(result,"raw",raw)<0||PyDict_SetItemString(result,"stacks",stacks)<0)goto fail;
    Py_DECREF(raw);Py_DECREF(stacks);pause(0);lab_snapshot_busy=0;return result;
fail:Py_XDECREF(raw);Py_XDECREF(stacks);Py_XDECREF(result);pause(0);lab_snapshot_busy=0;return NULL;
}
