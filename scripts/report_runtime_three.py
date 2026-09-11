"""Three Python entry points wrapping the same C++ kernels."""
import csv
import json
from pathlib import Path
import sys

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import pyperf

directory = Path(sys.argv[1])
environment = json.loads((directory / 'environment.json').read_text())
backends = ['py', 'nb', 'cy']
labels = {'py': 'pybind11', 'nb': 'nanobind', 'cy': 'Cython (C++ wrapper)'}
for backend in backends:
    if not (directory / f'{backend}.json').exists():
        raise SystemExit(f'Missing {backend} measurements; finish all three backends first.')
suites = {b: pyperf.BenchmarkSuite.load(str(directory / f'{b}.json')) for b in backends}
names = suites['py'].get_benchmark_names()
if any(set(s.get_benchmark_names()) != set(names) for s in suites.values()):
    raise SystemExit('The three runtime suites contain different cases.')
rows = []
for name in names:
    baseline = suites['py'].get_benchmark(name).mean()
    for backend in backends:
        bench = suites[backend].get_benchmark(name)
        mean = bench.mean()
        rows.append(dict(case=name, backend=backend, mean_ns=mean*1e9,
                         stdev_ns=bench.stdev()*1e9, ratio_vs_py=baseline/mean,
                         reduction_percent_vs_py=100*(baseline-mean)/baseline))
with (directory / 'comparison.csv').open('w', newline='', encoding='utf-8') as stream:
    writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
    writer.writeheader()
    writer.writerows(rows)
lookup = {(r['case'], r['backend']): r for r in rows}
fig, axes = plt.subplots(1, 3, figsize=(15, 4.8))
for axis, prefix, xlabel in zip(axes, ['work/', 'array_sum/', 'list_to_vector_sum/'],
                               ['C++ recurrence iterations', 'Zero-copy array elements', 'List elements (copy to vector)']):
    selected = [n for n in names if n.startswith(prefix)]
    for backend in backends:
        axis.plot([int(n.split('/')[-1]) for n in selected],
                  [lookup[(n, backend)]['mean_ns'] for n in selected], 'o-', label=labels[backend])
    axis.set_xscale('symlog', linthresh=1)
    axis.set_yscale('log')
    axis.set_xlabel(xlabel)
    axis.set_ylabel('Mean elapsed time (ns, log scale)')
    axis.grid(alpha=.2)
axes[0].legend(fontsize=8)
fig.suptitle(('SMOKE RUN — not publication-quality evidence\n' if environment['fast'] else '') +
             'Same C++ kernels | Python entry points | smaller is faster')
fig.tight_layout()
fig.savefig(directory / 'runtime.png', dpi=160)
plt.close(fig)
lines = ['# Runtime comparison: pybind11 / nanobind / Cython', '',
         '**SMOKE RUN: not publication-quality evidence.**' if environment['fast'] else
         'Inspect stability warnings and repeat complete runs before drawing conclusions.', '',
         f"Cython version: {environment.get('cython_version', 'unknown')}. All three wrap src/kernels.h; GIL held.", '',
         '| Case | pybind11 ns | nanobind ns | Cython ns | nanobind reduction | Cython reduction |',
         '|---|---:|---:|---:|---:|---:|']
for name in names:
    lines.append('| ' + name + ' | ' + ' | '.join(f"{lookup[(name,b)]['mean_ns']:.1f}" for b in backends) +
                 ' | ' + ' | '.join(f"{lookup[(name,b)]['reduction_percent_vs_py']:.1f}%" for b in ['nb', 'cy']) + ' |')
lines += ['', '![Runtime curves](runtime.png)', '',
          'Reductions are relative to pybind11; positive means lower elapsed time. CSV uses long format (one row per backend/case).',
          'Cython uses typed Python def entry points, not internal cdef calls. Arrays use NumPy validation and const contiguous memoryviews.',
          'The Cython Value wrapper explicitly owns shared_ptr; identity returns the existing Python object. Callback bridging is hand-written CPython C API code feeding the same std::function kernel.',
          'These implementation choices are part of this wrapper, not universal Cython defaults. Generated code compilation uses CMake Release flags; native profile adds no special Cython optimization.',
          'Means and standard deviations describe samples, not confidence intervals. No overall ranking or migration threshold is inferred.']
(directory / 'report.md').write_text('\n'.join(lines), encoding='utf-8')
print(directory / 'report.md')
