"""Descriptive median build curves; keep all repeated measurements in scale.json."""
import csv
import json
from pathlib import Path
import statistics
import sys
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

directory = Path(sys.argv[1])
raw = json.loads((directory / 'scale.json').read_text())
environment = json.loads((directory / 'environment.json').read_text())
if 'counts' in environment:
    expected = {(n, b, r) for n in environment['counts'] for b in environment['backends']
                for r in range(environment['repeats'])}
    actual = {(r['count'], r['backend'], r['repeat']) for r in raw}
    if actual != expected or len(raw) != len(expected):
        raise SystemExit('Incomplete or duplicated scale measurements; refusing a complete report.')
rows = []
for count, backend in sorted({(r['count'], r['backend']) for r in raw}):
    selected = [r for r in raw if r['count'] == count and r['backend'] == backend]
    row = dict(count=count, backend=backend, repeats=len(selected))
    for field in ('clean_seconds', 'incremental_seconds', 'import_seconds', 'module_bytes'):
        row[field] = statistics.median(r[field] for r in selected)
    for field in ('codegen_seconds', 'compile_seconds', 'incremental_codegen_seconds', 'incremental_compile_seconds'):
        row[field] = statistics.median(r[field] for r in selected) if all(field in r for r in selected) else None
    rows.append(row)
with (directory / 'summary.csv').open('w', newline='', encoding='utf-8') as f:
    writer = csv.DictWriter(f, fieldnames=list(rows[0]))
    writer.writeheader()
    writer.writerows(rows)
fig, axes = plt.subplots(1, 3, figsize=(14, 4.5))
for axis, field, ylabel in zip(axes, ['clean_seconds', 'incremental_seconds', 'module_bytes'],
                               ['Clean build (s)', 'Binding source rebuild (s)', 'Module size (bytes)']):
    for backend, label in [('py', 'pybind11'), ('nb', 'nanobind'), ('cy', 'Cython')]:
        selected = [r for r in rows if r['backend'] == backend]
        if not selected:
            continue
        axis.plot([r['count'] for r in selected], [r[field] for r in selected], 'o-', label=label)
    axis.set_xscale('log')
    axis.set_xlabel('Generated bindings (one translation unit)')
    axis.set_ylabel(ylabel)
    axis.grid(alpha=.2)
    axis.legend()
fig.suptitle(('SMOKE RUN — single repetition\n' if min(r['repeats'] for r in rows) < 3 else '') +
             f"Build scale: {environment['kind']} | medians | clean builds include nanobind runtime")
fig.tight_layout()
fig.savefig(directory / 'scale.png', dpi=160)
plt.close(fig)
print(directory / 'scale.png')
lines = ['# Build scale comparison', '',
         '**Smoke run: fewer than three repetitions.**' if min(r['repeats'] for r in rows) < 3 else
         'Three or more repetitions; descriptive medians, not confidence intervals.', '',
         'Single translation unit. Dependency install, configure and fixture generation excluded. '
         'Clean objects with warm filesystem caches; nanobind clean builds include its static runtime. '
         'Cython totals include source generation followed by C++ compilation/linking. Each stage includes build-tool startup.', '',
         '| Bindings | Backend | Repeats | Codegen s | Compile/link s | Clean total s | Incremental total s | Module KiB |',
         '|---:|---|---:|---:|---:|---:|---:|---:|']
for row in rows:
    fmt = lambda v: 'N/A' if v is None else f'{v:.3f}'
    lines.append(f"| {row['count']} | {row['backend']} | {row['repeats']} | {fmt(row['codegen_seconds'])} | "
                 f"{fmt(row['compile_seconds'])} | {row['clean_seconds']:.3f} | {row['incremental_seconds']:.3f} | {row['module_bytes']/1024:.1f} |")
lines += ['', '![Build curves](scale.png)', '',
          'Stage medians need not sum to the median total. A zero codegen stage for py/nb means not applicable.',
          'Incremental Cython measurement touches .pyx and includes regeneration; it is not a generated-.cpp-only rebuild.',
          'All generated functions/classes are exercised after the clean build. Source and Python wrapper implementation choices can affect size and compile costs.']
(directory / 'report.md').write_text('\n'.join(lines), encoding='utf-8')
