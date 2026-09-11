"""Render completed benchmark reports in GitHub's job summary (stdlib only)."""
import argparse
import csv
import html
import os
from pathlib import Path


def render(root, label, artifact_url=''):
    lines = [f'# Benchmark results: {html.escape(label)}', '',
             '**CI smoke measurements: descriptive results only; no migration recommendation or cross-platform ranking.**', '',
             'Runtime tables show means; build tables show medians. Smaller times are faster. '
             'Runtime reduction = (pybind11 - nanobind) / pybind11; positive favors nanobind.', '']
    if artifact_url:
        lines += [f'[Download charts, full reports, raw measurements and test diagnostics]({artifact_url}) (14-day retention).', '']
    else:
        lines += ['Artifact link unavailable; check the upload step and workflow artifacts.', '']
    found = 0
    for directory in sorted(root.iterdir()) if root.exists() else []:
        if not directory.is_dir():
            continue
        report = directory / 'report.md'
        scale = directory / 'summary.csv'
        if report.exists():
            found += 1
            body = [line for line in report.read_text(encoding='utf-8').splitlines()
                    if not line.startswith('![')]
            lines += ['<details>', f'<summary>{html.escape(directory.name)}</summary>', '',
                      *body, '', '</details>', '']
        elif scale.exists() and (directory / 'scale.json').exists():
            found += 1
            with scale.open(newline='', encoding='utf-8') as stream:
                rows = list(csv.DictReader(stream))
            lines += [f'## {html.escape(directory.name)}', '',
                      'Clean build includes the nanobind runtime; incremental build touches the binding source only.', '',
                      '| Bindings | Backend | Repeats | Clean s | Incremental s | Import ms | Module KiB |',
                      '|---:|---|---:|---:|---:|---:|---:|']
            for row in rows:
                lines.append(f"| {row['count']} | {row['backend']} | {row['repeats']} | "
                             f"{float(row['clean_seconds']):.3f} | {float(row['incremental_seconds']):.3f} | "
                             f"{float(row['import_seconds'])*1000:.3f} | {float(row['module_bytes'])/1024:.1f} |")
            lines += ['']
    if not found:
        lines += ['No completed benchmark reports. Benchmark steps may have failed or been skipped.', '']
    lines += ['Only completed reports are included. Check job status for failed or skipped suites; '
              'PNG charts remain in the downloadable artifact.', '']
    return '\n'.join(lines)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--results', type=Path, default=Path('results'))
    parser.add_argument('--output', type=Path, default=os.environ.get('GITHUB_STEP_SUMMARY'))
    parser.add_argument('--label', default=os.environ.get('BENCH_SUMMARY_LABEL', 'local preview'))
    args = parser.parse_args()
    result = render(args.results, args.label, os.environ.get('BENCH_ARTIFACT_URL', ''))
    if args.output:
        with args.output.open('a', encoding='utf-8') as stream:
            stream.write(result)
    else:
        print(result)
