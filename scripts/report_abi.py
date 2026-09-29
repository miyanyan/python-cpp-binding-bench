"""Within-interpreter ABI comparison; never pool Python versions."""
import csv
import json
from pathlib import Path
import sys
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import pyperf

directory = Path(sys.argv[1])
env = json.loads((directory / 'environment.json').read_text())
suites = [pyperf.BenchmarkSuite.load(str(directory / f'{b}.json')) for b in ['nb', 'nb_abi']]
names = suites[0].get_benchmark_names()
if set(names) != set(suites[1].get_benchmark_names()) or len(names) != 40:
    raise SystemExit('Expected two complete 40-case ABI suites')
rows = []
for name in names:
    a, b = [s.get_benchmark(name) for s in suites]
    rows.append(dict(case=name, ordinary_ns=a.mean()*1e9, stable_ns=b.mean()*1e9,
                     ordinary_stdev_ns=a.stdev()*1e9, stable_stdev_ns=b.stdev()*1e9,
                     extra_ns=(b.mean()-a.mean())*1e9, overhead_percent=(b.mean()/a.mean()-1)*100))
with (directory / 'comparison.csv').open('w', newline='', encoding='utf-8') as stream:
    writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
    writer.writeheader()
    writer.writerows(rows)
fig, axes = plt.subplots(1, 3, figsize=(15, 4.8))
for ax, prefix in zip(axes, ['work/', 'array_sum/', 'list_to_vector_sum/']):
    selected = [r for r in rows if r['case'].startswith(prefix)]
    ax.plot([int(r['case'].split('/')[-1]) for r in selected], [r['overhead_percent'] for r in selected], 'o-')
    ax.set_xscale('symlog', linthresh=1)
    ax.axhline(0, color='gray', linewidth=.8)
    ax.set_xlabel(prefix.rstrip('/') + ' size')
    ax.set_ylabel('Stable ABI overhead (%)')
    ax.grid(alpha=.2)
fig.suptitle(('SMOKE RUN — not publication-quality evidence\n' if env['fast'] else '') +
             f'Linked nanobind ABI comparison | runtime Python {env["run_python"].split()[0]}')
fig.tight_layout()
fig.savefig(directory / 'abi.png', dpi=160)
plt.close(fig)
lines = ['# nanobind: ordinary ABI vs Stable ABI', '',
         '**SMOKE RUN: not publication-quality evidence.**' if env['fast'] else 'Repeat complete runs and inspect sample variability.', '',
         f'Runtime Python: {env["run_python"].split()[0]}; stable build Python: {env["stable_manifest"]["build_python"].split()[0]}; reused binary: {env["reused"]}.',
         f'Stable SHA-256: `{env["stable_sha256"]}`.', '',
         'Positive overhead means stable is slower. Comparisons stay within one interpreter; standard deviations in CSV are not confidence intervals.', '',
         '| Case | Ordinary ns | Stable ns | Extra ns | Overhead |', '|---|---:|---:|---:|---:|']
for r in rows:
    lines.append(f"| {r['case']} | {r['ordinary_ns']:.1f} | {r['stable_ns']:.1f} | {r['extra_ns']:.1f} | {r['overhead_percent']:.1f}% |")
lines += ['', '![Stable ABI overhead](abi.png)', '',
          'Same binding/kernel source, GIL held, NB_STATIC linked mode, same selected optimization profile. No split backend.',
          'Cross-version reuse measures the deployment configuration, including different build headers; only the build-interpreter run isolates the ABI toggle most closely.',
          'Compatibility evidence is for this binary and these tested interpreter environments, not a complete wheel/distribution ABI audit.']
(directory / 'report.md').write_text('\n'.join(lines), encoding='utf-8')
print(directory / 'report.md')
