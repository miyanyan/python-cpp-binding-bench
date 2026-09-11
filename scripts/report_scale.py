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
rows = []
for count, backend in sorted({(r['count'], r['backend']) for r in raw}):
    selected = [r for r in raw if r['count'] == count and r['backend'] == backend]
    row = dict(count=count, backend=backend, repeats=len(selected))
    for field in ('clean_seconds', 'incremental_seconds', 'import_seconds', 'module_bytes'):
        row[field] = statistics.median(r[field] for r in selected)
    rows.append(row)
with (directory / 'summary.csv').open('w', newline='', encoding='utf-8') as f:
    writer = csv.DictWriter(f, fieldnames=list(rows[0]))
    writer.writeheader()
    writer.writerows(rows)
fig, axes = plt.subplots(1, 3, figsize=(14, 4.5))
for axis, field, ylabel in zip(axes, ['clean_seconds', 'incremental_seconds', 'module_bytes'],
                               ['Clean build (s)', 'Binding source rebuild (s)', 'Module size (bytes)']):
    for backend, label in [('py', 'pybind11'), ('nb', 'nanobind')]:
        selected = [r for r in rows if r['backend'] == backend]
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
