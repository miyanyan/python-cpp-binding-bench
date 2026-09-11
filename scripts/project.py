"""Pixi entry point. All Python subprocesses use this exact interpreter."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
import sysconfig
import time

ROOT = Path(__file__).resolve().parents[1]

def run(args, **kwargs):
    print('+', ' '.join(map(str, args)), flush=True)
    return subprocess.run(list(map(str, args)), cwd=ROOT, check=True, **kwargs)

def setup():
    prefix = os.environ.get('CONDA_PREFIX')
    if not prefix or not Path(sys.executable).resolve().is_relative_to(Path(prefix).resolve()):
        raise SystemExit('Run with pixi run; Python must belong to CONDA_PREFIX.')
    if sysconfig.get_config_var('Py_GIL_DISABLED'):
        raise SystemExit('This suite currently requires a regular GIL-enabled CPython.')
    os.environ['BENCH_PYTHON'] = Path(sys.executable).as_posix()
    if not os.environ.get('VCPKG_ROOT'):
        exe = shutil.which('vcpkg')
        if not exe:
            raise SystemExit('Set VCPKG_ROOT to a bootstrapped vcpkg checkout.')
        os.environ['VCPKG_ROOT'] = str(Path(exe).parent)
    if sys.platform == 'win32' and not shutil.which('cl'):
        vswhere = Path(os.environ['ProgramFiles(x86)']) / 'Microsoft Visual Studio/Installer/vswhere.exe'
        install = subprocess.check_output([str(vswhere), '-latest', '-products', '*',
            '-requires', 'Microsoft.VisualStudio.Component.VC.Tools.x86.x64',
            '-property', 'installationPath'], text=True).strip()
        if not install:
            raise SystemExit('Install Visual Studio C++ build tools.')
        vcvars = Path(install) / 'VC/Auxiliary/Build/vcvars64.bat'
        # Only environment activation; no filesystem operations are passed across shells.
        env_text = subprocess.check_output(f'"{vcvars}" >nul && set', shell=True, text=True)
        original_path = os.environ['PATH']
        for line in env_text.splitlines():
            key, sep, value = line.partition('=')
            if sep and key:
                os.environ[key] = value
        os.environ['PATH'] = original_path + os.pathsep + os.environ['PATH']
    os.environ.setdefault('PIXI_ENVIRONMENT_NAME', 'default')
    compiler = os.environ.get('CXX') or ('cl' if sys.platform == 'win32' else 'c++')
    resolved_compiler = shutil.which(compiler)
    if not resolved_compiler:
        raise SystemExit(f'C++ compiler not found: {compiler}')
    os.environ['BENCH_CXX'] = Path(resolved_compiler).as_posix()

def configure(profile, directory=None, extra=()):
    args = ['cmake', '--preset', profile]
    destination = directory or ROOT / 'build' / os.environ['PIXI_ENVIRONMENT_NAME'] / profile
    cache = destination / 'CMakeCache.txt'
    selection_file = destination / 'toolchain-selection.json'
    selection = {'python': sys.executable, 'python_version': sys.version,
                 'compiler': os.environ['BENCH_CXX'], 'vcpkg': os.environ['VCPKG_ROOT']}
    if cache.exists():
        content = cache.read_text(encoding='utf-8')
        match = re.search(r'^CMAKE_CXX_COMPILER:[^=]+=(.*)$', content, re.MULTILINE)
        changed = match and Path(match[1]).resolve() != Path(os.environ['BENCH_CXX']).resolve()
        selection_changed = selection_file.exists() and json.loads(selection_file.read_text()) != selection
        if changed or selection_changed or 'CMAKE_TOOLCHAIN_FILE:' not in content:
            args.append('--fresh')
    if directory:
        args += ['-B', directory]
    run(args + list(extra))
    selection_file.write_text(json.dumps(selection, indent=2), encoding='utf-8')

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['configure', 'build', 'test', 'bench', 'sdk', 'scale'])
    parser.add_argument('--profile', choices=['matched', 'native'], default='matched')
    parser.add_argument('--fast', action='store_true', help='Smoke measurements, not publication quality')
    parser.add_argument('--jobs', type=int, default=2)
    parser.add_argument('--counts', default='1,10,100,1000')
    parser.add_argument('--kind', choices=['functions', 'classes'], default='functions')
    parser.add_argument('--repeats', type=int, default=3)
    parser.add_argument('--order', choices=['py-first', 'nb-first'], default='py-first')
    args = parser.parse_args()
    if args.jobs < 1 or args.repeats < 1:
        parser.error('--jobs and --repeats must be positive')
    setup()
    name = os.environ['PIXI_ENVIRONMENT_NAME']
    build = ROOT / 'build' / name / args.profile
    if args.action == 'scale':
        measure_scale(args, name)
        return
    configure(args.profile)
    if args.action == 'configure':
        return
    run(['cmake', '--build', '--preset', args.profile, '--parallel', args.jobs])
    os.environ['BENCH_MODULE_DIR'] = str(build / 'modules')
    os.environ['BENCH_BUILD_DIR'] = str(build)
    if args.action in ('test', 'bench', 'sdk'):
        run([sys.executable, '-m', 'pytest', '-q', 'tests'])
    if args.action in ('bench', 'sdk'):
        suite = 'sdk' if args.action == 'sdk' else 'runtime'
        stamp = time.strftime('%Y%m%d-%H%M%S')
        output = ROOT / 'results' / f'{"sdk-" if suite == "sdk" else ""}{name}-{args.profile}-{stamp}'
        output.mkdir(parents=True)
        shutil.copy2(build / 'build-info.json', output / 'build-info.json')
        # Preserve effective flags and machine/dependency configuration alongside timings.
        shutil.copy2(build / 'compile_commands.json', output / 'compile_commands.json')
        (output / 'environment.json').write_text(json.dumps({
            'python': sys.version, 'executable': sys.executable, 'platform': platform.platform(),
            'processor': platform.processor(), 'fast': args.fast,
            'order': args.order,
            'suite': suite,
            'backends': ['py', 'smart', 'nb'] if suite == 'sdk' else ['py', 'nb', 'cy'],
            'cython_version': __import__('Cython').__version__,
            'source_sha256': {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                              for p in [ROOT / 'pixi.lock', ROOT / 'vcpkg.json', ROOT / 'CMakeLists.txt', ROOT / 'CMakePresets.json',
                                        *sorted((ROOT / 'src').glob('*')), *sorted((ROOT / 'benchmarks').glob('*.py'))]},
            'module_bytes': {p.name: p.stat().st_size for p in (build / 'modules').iterdir() if p.suffix in ('.pyd', '.so')},
        }, indent=2), encoding='utf-8')
        backends = ['py', 'smart', 'nb'] if suite == 'sdk' else ['py', 'nb', 'cy']
        if args.order == 'nb-first':
            backends.reverse()
            backends.remove('nb')
            backends.insert(0, 'nb')
        for library in backends:
            run([sys.executable, f'benchmarks/{suite}.py', '--backend', library,
                 '--output', output / f'{library}.json',
                 '--inherit-environ', 'BENCH_MODULE_DIR,BENCH_BUILD_DIR']
                + (['--processes', '2', '--values', '2', '--warmups', '1', '--min-time', '0.01'] if args.fast else []))
        run([sys.executable, 'scripts/report_sdk.py' if suite == 'sdk' else 'scripts/report.py', output])

def measure_scale(args, name):
    """Dependency install/configure excluded; clean builds include nanobind runtime."""
    rows = []
    output = ROOT / 'results' / f'scale-{name}-{args.profile}-{args.kind}-{time.strftime("%Y%m%d-%H%M%S")}'
    output.mkdir(parents=True)
    (output / 'environment.json').write_text(json.dumps({
        'python': sys.version, 'executable': sys.executable, 'platform': platform.platform(),
        'processor': platform.processor(), 'compiler_path': os.environ['BENCH_CXX'],
        'jobs': args.jobs, 'kind': args.kind, 'repeats': args.repeats,
        'scope': 'single translation unit; clean objects, warm filesystem; dependency configure/install excluded',
    }, indent=2), encoding='utf-8')
    for count in map(int, args.counts.split(',')):
        if count < 1:
            raise SystemExit('counts must be positive')
        directory = ROOT / 'build' / name / f'scale-{args.profile}-{args.kind}-{count}'
        configure(args.profile, directory, [f'-DBENCH_SCALE_COUNT={count}', f'-DBENCH_SCALE_KIND={args.kind}'])
        shutil.copy2(directory / 'build-info.json', output / f'build-info-{count}.json')
        shutil.copy2(directory / 'compile_commands.json', output / f'compile-commands-{count}.json')
        for repeat in range(args.repeats):
            for backend in (('py', 'nb') if repeat % 2 == 0 else ('nb', 'py')):
                target = f'scale_{backend}'
                run(['cmake', '--build', directory, '--target', 'clean'])
                start = time.perf_counter()
                run(['cmake', '--build', directory, '--target', target, '--parallel', args.jobs])
                clean_seconds = time.perf_counter() - start
                module = next(p for p in (directory / 'modules').glob(f'{target}*') if p.suffix in ('.so', '.pyd'))
                # A new process really imports and exercises a generated binding.
                snippet = (f'import sys,time; sys.path.insert(0,{str(directory / "modules")!r}); '
                    f't=time.perf_counter(); import {target} as m; print(time.perf_counter()-t); '
                    + (f'assert m.f0(3)==3; assert m.f{count-1}(3)=={count+2}' if args.kind == 'functions'
                       else f'assert m.C0(3).get()==3; assert m.C{count-1}(3).get()=={count+2}'))
                imported = subprocess.check_output([sys.executable, '-c', snippet], text=True)
                (directory / 'generated' / f'{backend}.cpp').touch()
                start = time.perf_counter()
                run(['cmake', '--build', directory, '--target', target, '--parallel', args.jobs])
                row = dict(count=count, backend=backend, repeat=repeat, jobs=args.jobs,
                           clean_seconds=clean_seconds, incremental_seconds=time.perf_counter()-start,
                           import_seconds=float(imported.strip()), module_bytes=module.stat().st_size)
                rows.append(row)
                (output / 'scale.json').write_text(json.dumps(rows, indent=2), encoding='utf-8')
    print(f'Scale results: {output}')
    run([sys.executable, 'scripts/report_scale.py', output])

if __name__ == '__main__':
    main()
