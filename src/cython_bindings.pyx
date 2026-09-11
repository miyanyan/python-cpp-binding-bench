# cython: language_level=3
from libc.stdint cimport int64_t, uint64_t, uintptr_t
from libc.stddef cimport size_t
from libcpp.vector cimport vector
from libcpp.memory cimport shared_ptr
from cpython.ref cimport PyObject
import numpy as np

cdef extern from "kernels.h" namespace "kernel":
    void cpp_noop "kernel::noop"()
    int64_t cpp_add "kernel::add"(int64_t, int64_t)
    uint64_t cpp_work "kernel::work"(uint64_t, size_t)
    double cpp_sum "kernel::sum"(const double*, size_t)
    double cpp_vector_sum "kernel::vector_sum"(const vector[double]&) except +
    vector[double] cpp_vector_echo "kernel::vector_echo"(const vector[double]&) except +
    cdef cppclass CppValue "kernel::Value":
        CppValue(int64_t) except +
        int64_t get() const
    shared_ptr[CppValue] cpp_make_shared "kernel::make_shared"(int64_t) except +
    int64_t cpp_read_shared "kernel::read_shared"(const shared_ptr[CppValue]&)

cdef extern from "cython_bridge.h" namespace "cython_bridge":
    void translate_python_error()
    int64_t cpp_callback "cython_bridge::callback"(PyObject*, size_t) except +translate_python_error

def noop():
    cpp_noop()

def add(int64_t a, int64_t b):
    return cpp_add(a, b)

def work(uint64_t seed, size_t iterations):
    return cpp_work(seed, iterations)

def vector_sum(vector[double] x):
    return cpp_vector_sum(x)

def vector_echo(vector[double] x):
    return cpp_vector_echo(x)

cdef class Value:
    cdef shared_ptr[CppValue] owner

    def __init__(self, int64_t value):
        self.owner = cpp_make_shared(value)

    def get(self):
        if not self.owner:
            raise ValueError('uninitialized Value')
        return self.owner.get().get()

def make_shared(int64_t value):
    cdef Value result = Value.__new__(Value)
    result.owner = cpp_make_shared(value)
    return result

def read_shared(Value value not None):
    if not value.owner:
        raise ValueError('uninitialized Value')
    return cpp_read_shared(value.owner)

def identity(Value value not None):
    return value

cdef const double[::1] checked_array(object x):
    # Match the public NumPy-only contract, rather than accept arbitrary buffers.
    if not isinstance(x, np.ndarray):
        raise TypeError('expected a NumPy array')
    if x.ndim != 1:
        raise ValueError('expected a 1D array')
    return x

def array_sum(object x):
    cdef const double[::1] view = checked_array(x)
    if view.shape[0] == 0:
        return cpp_sum(NULL, 0)
    return cpp_sum(&view[0], view.shape[0])

def array_address(object x):
    cdef const double[::1] view = checked_array(x)
    # NumPy retains a data pointer even for an empty array.
    if view.shape[0] == 0:
        return x.ctypes.data
    return <uintptr_t>&view[0]

def callback(object function, size_t n):
    if not callable(function):
        raise TypeError('expected a callable')
    return cpp_callback(<PyObject*>function, n)
