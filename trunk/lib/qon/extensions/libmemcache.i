%module libmemcache
%{
#include "/usr/local/include/memcache.h"
%}

// helper function for mc_aget2
// puts both output args in the argument list so i can get them
// with an argout typemap

%typemap(in, numinputs=0) (void **retval, size_t *retlen) (void *temp1, size_t temp2) {
    $1 = &temp1;
    $2 = &temp2;
}
%typemap(argout) (void **retval, size_t *retlen) {
    if (*$2) {
        $result = PyString_FromStringAndSize(*$1, *$2);
    }
    else{
        $result = Py_None;
        Py_INCREF(Py_None);
    }
}

%inline %{
    void call_mc_aget2(struct memcache *mc, char *key, const size_t len, void **retval, size_t *retlen) {
        void *val = mc_aget2(mc, key, len, retlen);
        *retval = val;
    }
%}


// allow python strings as void* input vars
%typemap(in) void * {
    $1 = (char *) PyString_AsString($input);
}

// tell swig about standard types
typedef unsigned long time_t;
typedef unsigned long u_int32_t;
typedef unsigned int u_int16_t;
typedef unsigned long long u_int64_t;


// SWIG doesn't understand inline keyword
#define inline

// ignore unimplemented functions in header file
%ignore mc_server_reset_all_dns;
%ignore mc_server_reset_dns;

// tell swig that these functions allocate memory that must be freed by python
%newobject mc_aget;
%newobject mc_aget2;


// include libmemcache header file
%include "/usr/local/include/memcache.h"

