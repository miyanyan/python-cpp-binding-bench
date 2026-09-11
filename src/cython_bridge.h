#pragma once
#include <Python.h>
#include "kernels.h"

namespace cython_bridge {
// The GIL is held throughout. Preserve the original Python callback exception.
struct PythonError {};
inline void translate_python_error() {
    if (!PyErr_Occurred()) PyErr_SetString(PyExc_RuntimeError, "Cython callback bridge failed");
}
inline std::int64_t callback(PyObject* callable, std::size_t n) {
    return kernel::callback([callable](std::int64_t value) -> std::int64_t {
        PyObject* arg = PyLong_FromLongLong(value);
        if (!arg) throw PythonError{};
        PyObject* result = PyObject_CallOneArg(callable, arg);
        Py_DECREF(arg);
        if (!result) throw PythonError{};
        auto number = PyLong_AsLongLong(result);
        Py_DECREF(result);
        if (PyErr_Occurred()) throw PythonError{};
        return number;
    }, n);
}
}
