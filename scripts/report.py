"""Compare independently measured suites. Positive reduction favors nanobind."""
import csv
import json
from pathlib import Path
import sys
import subprocess
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import pyperf

root = Path(__file__).resolve().parents[1]
if len(sys.argv) > 1:
    directory = Path(sys.argv[1])
else:
    candidates = [p.parent for p in (root / 'results').glob('*/py.json')
                  if not p.parent.name.startswith('sdk-') and (p.parent / 'nb.json').exists()]
    candidates = [p for p in candidates if 'cy' not in
                  json.loads((p / 'environment.json').read_text()).get('backends', [])
                  or (p / 'cy.json').exists()]
    if not candidates:
        raise SystemExit('No completed benchmark pair. Run pixi run bench first.')
    directory = max(candidates, key=lambda p: p.stat().st_mtime)
environment = json.loads((directory / 'environment.json').read_text())
if 'cy' in environment.get('backends', []) or (directory / 'cy.json').exists():
    subprocess.run([sys.executable, str(root / 'scripts/report_runtime_three.py'), str(directory)], check=True)
    raise SystemExit(0)
fast = environment['fast']
if json.loads((directory / 'environment.json').read_text()).get('suite') == 'sdk':
    raise SystemExit('Use scripts/report_sdk.py to compare the three SDK backends.')
py = pyperf.BenchmarkSuite.load(str(directory / 'py.json'))
nb = pyperf.BenchmarkSuite.load(str(directory / 'nb.json'))
if set(py.get_benchmark_names()) != set(nb.get_benchmark_names()):
    raise SystemExit('The two suites contain different cases; wait for the run to finish or rerun both backends.')
rows = []
for name in py.get_benchmark_names():
    a, b = py.get_benchmark(name), nb.get_benchmark(name)
    ta, tb = a.mean(), b.mean()
    rows.append(dict(case=name, py_ns=ta * 1e9, nb_ns=tb * 1e9,
                     py_stdev_ns=a.stdev() * 1e9, nb_stdev_ns=b.stdev() * 1e9,
                     ratio=ta/tb, reduction_percent=100*(ta-tb)/ta,
                     saved_ms_per_million_case_executions=(ta-tb)*1e9))
with (directory / 'comparison.csv').open('w', newline='', encoding='utf-8') as f:
    writer = csv.DictWriter(f, fieldnames=list(rows[0]))
    writer.writeheader()
    writer.writerows(rows)
fig, axes = plt.subplots(1, 3, figsize=(15, 4.5))
for axis, prefix, label in zip(axes, ['work/', 'array_sum/', 'list_to_vector_sum/'],
                               ['C++ recurrence iterations', 'Array elements (zero-copy)', 'List elements (copy to vector)']):
    selected = [r for r in rows if r['case'].startswith(prefix)]
    x = [int(r['case'].split('/')[-1]) for r in selected]
    axis.plot(x, [r['reduction_percent'] for r in selected], 'o-')
    axis.set_xscale('symlog', linthresh=1)
    axis.axhline(0, color='black', linewidth=.7)
    axis.axhline(5, color='gray', linestyle=':', label='5% reference (not a recommendation)')
    axis.set_xlabel(label)
    axis.set_ylabel('Mean elapsed-time reduction (%)')
    axis.grid(alpha=.2)
fig.suptitle(('SMOKE RUN — not publication-quality evidence\n' if fast else '') +
             'pybind11 → nanobind | positive favors nanobind | dotted line: 5% reference')
fig.tight_layout()
fig.savefig(directory / 'runtime.png', dpi=160)
plt.close(fig)
lines = ['# Runtime comparison', '',
         '**SMOKE RUN: not publication-quality evidence.**' if fast else 'Repeated measurements; inspect pyperf stability warnings and distributions before drawing conclusions.',
         '', 'Positive reduction favors nanobind. Ratios are descriptive, not significance tests.',
         'Standard deviations are sample dispersion, not confidence intervals.', '',
         '| Case | pybind11 ns | nanobind ns | Ratio | Time reduction |',
         '|---|---:|---:|---:|---:|']
for r in rows:
    lines.append(f"| {r['case']} | {r['py_ns']:.1f} | {r['nb_ns']:.1f} | {r['ratio']:.2f}x | {r['reduction_percent']:.1f}% |")
lines += ['', '![Runtime curves](runtime.png)', '',
          'For a first-order estimate, multiply the measured per-call difference by the actual call count; validate with an end-to-end workload.',
          'These measurements do not estimate migration effort or guarantee a universal crossover point.']
(directory / 'report.md').write_text('\n'.join(lines), encoding='utf-8')
print(directory / 'report.md')
