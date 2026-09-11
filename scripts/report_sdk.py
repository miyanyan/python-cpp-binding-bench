"""SDK comparisons retain unsupported cases as N/A, never as zero elapsed time."""
import csv
import json
from pathlib import Path
import sys

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import pyperf

root = Path(__file__).resolve().parents[1]
if len(sys.argv) > 1:
    directory = Path(sys.argv[1])
else:
    candidates = [p.parent for p in (root / 'results').glob('sdk-*/py.json')
                  if all((p.parent / f'{b}.json').exists() for b in ('smart', 'nb'))]
    if not candidates:
        raise SystemExit('Run pixi run bench-sdk-quick or bench-sdk first.')
    directory = max(candidates, key=lambda p: p.stat().st_mtime)
environment = json.loads((directory / 'environment.json').read_text())
if environment.get('suite') != 'sdk':
    raise SystemExit('Expected an SDK suite directory.')
backends = ['py', 'smart', 'nb']
labels = {'py': 'pybind11 shared_ptr', 'smart': 'pybind11 smart_holder', 'nb': 'nanobind'}
suites = {b: pyperf.BenchmarkSuite.load(str(directory / f'{b}.json')) for b in backends}
common = set()
for count in [1, 4, 16, 32]:
    for pos in (['first'] if count == 1 else ['first', 'middle', 'last']):
        common.update([f'overload_hit/{count}/{pos}', f'overload_direct/{count}/{pos}'])
    common.add(f'overload_miss/{count}')
common.update('ownership/' + case for case in [
    'construct_destroy', 'method', 'reference_read', 'shared_read_python_origin',
    'shared_read_cpp_origin', 'shared_factory_destroy', 'shared_return_existing', 'shared_set_clear'])
unique = {'ownership/unique_roundtrip_python', 'ownership/unique_roundtrip_cpp'}
for backend, suite in suites.items():
    expected = common if backend == 'py' else common | unique
    if set(suite.get_benchmark_names()) != expected:
        raise SystemExit(f'{backend}: missing/unexpected cases; run all three backends to completion.')

rows = []
for name in sorted(common | unique):
    for backend in backends:
        supported = name in common or backend != 'py'
        bench = suites[backend].get_benchmark(name) if supported else None
        rows.append(dict(case=name, backend=backend, holder=labels[backend],
                         status='measured' if supported else 'unsupported',
                         mean_ns=bench.mean()*1e9 if bench else None,
                         stdev_ns=bench.stdev()*1e9 if bench else None))
with (directory / 'comparison.csv').open('w', newline='', encoding='utf-8') as f:
    writer = csv.DictWriter(f, fieldnames=list(rows[0]))
    writer.writeheader()
    writer.writerows(rows)
lookup = {(r['case'], r['backend']): r['mean_ns'] for r in rows}
title_prefix = 'SMOKE RUN — not publication-quality evidence\n' if environment['fast'] else ''

fig, axes = plt.subplots(1, 3, figsize=(15, 4.8))
for axis, position, title in zip(axes, ['first', 'last', 'miss'],
                                ['First matching overload', 'Last matching overload', 'No match: includes TypeError construction/catch']):
    for backend in backends:
        counts = [1, 4, 16, 32]
        names = [(f'overload_miss/{n}' if position == 'miss' else
                  f'overload_hit/{n}/{"first" if n == 1 else position}') for n in counts]
        axis.plot(counts, [lookup[(name, backend)] for name in names], 'o-', label=labels[backend])
    axis.set_xlabel('Registered overloads (strict class references)')
    axis.set_ylabel('Mean elapsed time (ns)')
    axis.set_title(title, fontsize=10)
    axis.set_xticks([1, 4, 16, 32])
    axis.grid(alpha=.2)
axes[0].legend(fontsize=8)
fig.suptitle(title_prefix + 'SDK overload dispatch | descriptive means')
fig.tight_layout()
fig.savefig(directory / 'overloads.png', dpi=160)
plt.close(fig)

names = sorted(n for n in common | unique if n.startswith('ownership/'))
fig, axis = plt.subplots(figsize=(13, 6.5))
for offset, backend in enumerate(backends):
    available = [(i, lookup[(name, backend)]) for i, name in enumerate(names) if lookup[(name, backend)] is not None]
    axis.barh([i + (offset-1)*.24 for i, _ in available], [v for _, v in available], height=.22, label=labels[backend])
for i, name in enumerate(names):
    if name in unique:
        axis.text(0, i-.24, 'N/A (shared_ptr)', fontsize=8, va='center')
axis.set_yticks(range(len(names)), [n.split('/')[1] for n in names])
axis.invert_yaxis()
axis.set_xlabel('Mean elapsed time per complete case (ns); smaller is faster')
axis.legend()
axis.grid(axis='x', alpha=.2)
fig.suptitle(title_prefix + 'Object ownership | creation/destruction included in lifecycle cases')
fig.tight_layout()
fig.savefig(directory / 'ownership.png', dpi=160)
plt.close(fig)

lines = ['# SDK binding comparison', '',
         '**SMOKE RUN: not publication-quality evidence.**' if environment['fast'] else 'Inspect pyperf stability warnings and repeat entire runs before making decisions.',
         '', 'Means are descriptive; sample standard deviations in CSV are not confidence intervals.',
         'The shared_ptr holder is explicit, not pybind11\'s default unique_ptr holder.',
         '', '| Case | pybind11 shared_ptr ns | pybind11 smart_holder ns | nanobind ns |',
         '|---|---:|---:|---:|']
for name in sorted(common | unique):
    values = [lookup[(name, b)] for b in backends]
    lines.append('| ' + name + ' | ' + ' | '.join('N/A' if v is None else f'{v:.1f}' for v in values) + ' |')
lines += ['', '![Overloads](overloads.png)', '', '![Ownership](ownership.png)', '',
          'Compare each overload_hit with overload_direct for the same count/position to assess dispatch cost.',
          'No-match timing includes exception formatting, creation, propagation and Python catch; it is not pure lookup cost.',
          'Shared reads separate Python-origin from C++-origin objects. Existing-return cases reuse a live Python wrapper.',
          'unique_roundtrip includes creation, transfer, destruction and the Python harness; shared_ptr-only is unsupported.',
          'Lifetime counters are used only in correctness fixtures. These workloads do not measure subclass trampolines, numeric conversions or real application throughput.']
(directory / 'report.md').write_text('\n'.join(lines), encoding='utf-8')
print(directory / 'report.md')
