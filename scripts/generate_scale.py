import argparse
from pathlib import Path

p = argparse.ArgumentParser()
p.add_argument('--output', type=Path, required=True)
p.add_argument('--count', type=int, required=True)
p.add_argument('--kind', choices=['functions', 'classes'], required=True)
a = p.parse_args()
a.output.mkdir(parents=True, exist_ok=True)
for alias, library, macro in [('py', 'pybind11', 'PYBIND11_MODULE'), ('nb', 'nanobind', 'NB_MODULE')]:
    # Unique template instantiations; fixed signature/count controls avoid random fixture drift.
    lines = [f'#include <{library}/{library}.h>', f'namespace b = {library};',
             'template<int I> struct Item { int v; Item(int x): v(x) {} int get() const { return v + I; } };',
             'template<int I> int fn(int x) { return x + I; }',
             f'{macro}(scale_{alias}, m) {{']
    for i in range(a.count):
        if a.kind == 'functions':
            lines.append(f'm.def("f{i}", &fn<{i}>);')
        else:
            lines.append(f'b::class_<Item<{i}>>(m,"C{i}").def(b::init<int>()).def("get", &Item<{i}>::get);')
    lines.append('}')
    (a.output / f'{alias}.cpp').write_text('\n'.join(lines), encoding='utf-8')
