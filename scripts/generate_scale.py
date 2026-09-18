import argparse
from pathlib import Path

p = argparse.ArgumentParser()
p.add_argument('--output', type=Path, required=True)
p.add_argument('--count', type=int, required=True)
p.add_argument('--kind', choices=['functions', 'classes'], required=True)
a = p.parse_args()
a.output.mkdir(parents=True, exist_ok=True)
header = ('#pragma once\n'
          'template<int I> struct Item { int v; Item(int x): v(x) {} int get() const { return v + I; } };\n'
          'template<int I> int fn(int x) { return x + I; }\n')
(a.output / 'scale_kernel.h').write_text(header, encoding='utf-8')
for alias, library, macro in [('py', 'pybind11', 'PYBIND11_MODULE'), ('nb', 'nanobind', 'NB_MODULE')]:
    # Unique template instantiations; fixed signature/count controls avoid random fixture drift.
    lines = [f'#include <{library}/{library}.h>', f'namespace b = {library};',
             '#include "scale_kernel.h"',
             f'{macro}(scale_{alias}, m) {{']
    for i in range(a.count):
        if a.kind == 'functions':
            lines.append(f'm.def("f{i}", &fn<{i}>);')
        else:
            lines.append(f'b::class_<Item<{i}>>(m,"C{i}").def(b::init<int>()).def("get", &Item<{i}>::get);')
    lines.append('}')
    (a.output / f'{alias}.cpp').write_text('\n'.join(lines), encoding='utf-8')

lines = ['# cython: language_level=3', 'cdef extern from "scale_kernel.h":']
for i in range(a.count):
    if a.kind == 'functions':
        lines.append(f'    int cpp_f{i} "fn<{i}>"(int)')
    else:
        lines += [f'    cdef cppclass Item{i} "Item<{i}>":',
                  f'        Item{i}(int) except +', '        int get() const']
for i in range(a.count):
    if a.kind == 'functions':
        lines += [f'def f{i}(int x):', f'    return cpp_f{i}(x)']
    else:
        lines += [f'cdef class C{i}:', f'    cdef Item{i}* owner',
                  '    def __cinit__(self, int x):', f'        self.owner = new Item{i}(x)',
                  '    def __dealloc__(self):', '        del self.owner',
                  '    def get(self):', '        return self.owner.get()']
(a.output / 'cy.pyx').write_text('\n'.join(lines), encoding='utf-8')
