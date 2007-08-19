%module aprmemcache
//%include typemaps.i
%{
#include </usr/local/include/apr-1/apr.h>
#include </usr/local/include/apr-1/apr_general.h>
%}

%include "apr.i"
%{
#include "/usr/local/include/apr_memcache-0/apr_memcache.h"
// helpers for apr_pools
PyObject *py_apr_pool_create(void);
PyObject *py_apr_pcalloc(apr_pool_t *pool, long size);
%}


// typemaps
typedef int apr_port_t;  // port type is just an int


// for apr_memcache_create
%typemap(in, numinputs=0) apr_memcache_t **mc(apr_memcache_t *temp) {
    $1 = &temp;
}
%typemap(argout) apr_memcache_t **mc {
    $result = SWIG_NewPointerObj(*$1, $descriptor(apr_memcache_t *), 0);
}

// for apr_memcache_server_create
%typemap(in, numinputs=0) apr_memcache_server_t **ns(apr_memcache_server_t *temp){
    $1 = &temp;
}
%typemap(argout) apr_memcache_server_t **ns {
    if (PyInt_AsLong($result)) {
        $result = Py_None;
        Py_INCREF(Py_None);
    }
    else {
        $result = SWIG_NewPointerObj(*$1, $descriptor(apr_memcache_server_t *), 0);
    }
}

// for getters: baton is storage for gotten value, return a python string
%typemap(in, numinputs=0) char **baton (char *temp1) {
    $1 = &temp1;
}
%typemap(argout) (char **baton) {
    // check for non-zero return value first and throw an exception
    if (PyInt_AsLong($result)) {
        $result = Py_None;
        Py_INCREF(Py_None);
        //PyErr_SetString(PyExc_RuntimeError, "An error occured.");
        //return NULL;
    }
    else {
        // single-return char **baton
        $result = PyString_FromString(*$1);
        if (!PyString_Check($result)) {
            $result = Py_None;
            Py_INCREF(Py_None);
        }
    }
}

// apr_memcache_getp expects baton and size, plus flags which we ignore
%typemap(in, numinputs=0) (char **baton, apr_size_t *len, apr_uint16_t *flags) (char *temp1, apr_size_t temp2, apr_uint16_t temp3) {
    $1 = &temp1;
    $2 = &temp2;
    $3 = &temp3;
}
%typemap(argout) (char **baton, apr_size_t *len) {
    // check for non-zero return value first and throw an exception
    if (PyInt_AsLong($result)) {
        $result = Py_None;
        Py_INCREF(Py_None);
        // PyErr_SetString(PyExc_RuntimeError, "An error occurred");
        //return NULL;
    }
    else {
        $result = PyString_FromStringAndSize(*$1, *$2);
        if (!PyString_Check($result)) {
            $result = Py_None;
            Py_INCREF(Py_None);
        }
            
    }
}


// for stats:
%typemap(in, numinputs=0) apr_memcache_stats_t **stats(apr_memcache_stats_t *temp) {
    $1 = &temp;
}
%typemap(argout) apr_memcache_stats_t **stats {
    if (PyInt_AsLong($result)) {
        $result = Py_None;
        Py_INCREF(Py_None);
    }
    else {    
        $result = SWIG_NewPointerObj(*$1, $descriptor(apr_memcache_stats_t *), 0);
    }
}

// initialize apr subsystem at module load
%init %{
    apr_initialize();
%}

// include header file
%include "/usr/local/include/apr_memcache-0/apr_memcache.h"

// helpers for apr_pools
PyObject *py_apr_pool_create(void);
PyObject *py_apr_pcalloc(apr_pool_t *pool, long size);

%{
    PyObject *py_apr_pool_create() {
        apr_pool_t  *p;
        apr_pool_create(&p, NULL);
        return SWIG_NewPointerObj(p, SWIGTYPE_p_apr_pool_t, 0);
    }
    
    PyObject *py_apr_pcalloc(apr_pool_t *pool, long size) {
        return SWIG_NewPointerObj(apr_pcalloc(pool, size), SWIGTYPE_p_char, 0);
    }
%}
