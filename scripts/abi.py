"""Compare ordinary nanobind with linked abi3; optionally reuse an existing binary."""
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
import time

from project import ROOT, configure, run, setup


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def audit_commands(build):
    commands = json.loads((build / 'compile_commands.json').read_text())
    stable = [c for c in commands if 'bench_nb_abi.dir' in c['command'] or 'nanobind-static-abi3.dir' in c['command']]
    ordinary = [c for c in commands if 'bench_nb.dir' in c['command'] or 'nanobind-static.dir' in c['command']]
    if len(stable) < 2 or len(ordinary) < 2:
        raise RuntimeError('Missing module/runtime compile commands for ABI audit')
    if not all('Py_LIMITED_API=0x030C0000' in c['command'] for c in stable):
        raise RuntimeError('Stable module/runtime not compiled for Limited API 3.12')
    if any('Py_LIMITED_API' in c['command'] for c in ordinary):
        raise RuntimeError('Ordinary baseline unexpectedly uses Limited API')
    return {'stable_translation_units': len(stable), 'ordinary_translation_units': len(ordinary)}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--fast', action='store_true')
    parser.add_argument('--test-only', action='store_true')
    parser.add_argument('--reuse', type=Path, help='Manifest from a prior abi-export; stable binary is copied, never rebuilt')
    parser.add_argument('--profile', choices=['matched', 'native'], default='matched')
    parser.add_argument('--order', choices=['ordinary-first', 'stable-first'], default='ordinary-first')
    parser.add_argument('--jobs', type=int, default=2)
    args = parser.parse_args()
    if sys.version_info < (3, 12) or args.jobs < 1:
        parser.error('Requires CPython >=3.12 and positive --jobs')
    setup()
    build = ROOT / 'build' / os.environ['PIXI_ENVIRONMENT_NAME'] / f'abi-{args.profile}'
    sources = {str(p.relative_to(ROOT)): digest(p) for p in
               [ROOT / 'src/nanobind.cpp', ROOT / 'src/kernels.h', ROOT / 'vcpkg.json', ROOT / 'pixi.lock']}
    original = None
    if args.reuse:
        args.reuse = args.reuse.resolve()
        original = json.loads(args.reuse.read_text())
        if (original['sources'] != sources or original['profile'] != args.profile or
                original['platform'] != sys.platform or original['machine'] != platform.machine() or
                original['floor'] != '3.12'):
            raise SystemExit('Reuse manifest source/profile/platform/floor mismatch')
        candidate = Path(original['filename'])
        if candidate.name != str(candidate):
            raise SystemExit('Reuse manifest filename must be a basename')
        artifact = args.reuse.parent / candidate
        if digest(artifact) != original['sha256']:
            raise SystemExit('Reuse binary hash mismatch')
    configure(args.profile, build, ['-DBENCH_ABI_ONLY=ON'])
    targets = ['bench_nb'] if original else ['bench_nb', 'bench_nb_abi']
    run(['cmake', '--build', build, '--target', *targets, '--parallel', args.jobs])
    audit = audit_commands(build)
    info = json.loads((build / 'build-info.json').read_text())
    if original and original['build_info']['compiler'] != info['compiler']:
        raise SystemExit('Reuse compiler differs from current baseline')
    output = ROOT / 'results' / f'abi-{os.environ["PIXI_ENVIRONMENT_NAME"]}-{args.profile}-{time.strftime("%Y%m%d-%H%M%S")}'
    modules = output / 'modules'
    modules.mkdir(parents=True)
    ordinary = next(p for p in (build / 'modules').iterdir()
                    if p.name.startswith('bench_nb.') and p.suffix in ('.pyd', '.so'))
    shutil.copy2(ordinary, modules / ordinary.name)
    if not original:
        artifact = next(p for p in (build / 'modules').iterdir()
                        if p.name.startswith('bench_nb_abi.') and p.suffix in ('.pyd', '.so'))
        original = dict(filename=artifact.name, sha256=digest(artifact), sources=sources,
                        profile=args.profile, platform=sys.platform, machine=platform.machine(),
                        floor='3.12', build_python=sys.version, build_info=info, build_audit=audit)
        export = build / 'abi-export'
        export.mkdir(exist_ok=True)
        shutil.copy2(artifact, export / artifact.name)
        (export / 'manifest.json').write_text(json.dumps(original, indent=2), encoding='utf-8')
        shutil.copy2(build / 'compile_commands.json', export / 'compile_commands.json')
        print(f'Reusable manifest: {export / "manifest.json"}', flush=True)
    stable = modules / artifact.name
    shutil.copy2(artifact, stable)
    if sys.platform == 'win32':
        for module, expected in [(stable, 'python3.dll'), (modules / ordinary.name, f'python{sys.version_info.major}{sys.version_info.minor}.dll')]:
            deps = subprocess.check_output(['dumpbin', '/DEPENDENTS', str(module)], text=True, errors='replace')
            (output / f'{module.stem}-dependencies.txt').write_text(deps, encoding='utf-8')
            python_dlls = re.findall(r'\bpython\d+(?:_d)?\.dll\b', deps.lower())
            if set(python_dlls) != {expected}:
                raise RuntimeError(f'Unexpected Python DLL dependencies: {python_dlls}')
        audit['windows_python_dlls_verified'] = True
    os.environ['BENCH_MODULE_DIR'] = str(modules)
    os.environ['BENCH_BUILD_DIR'] = str(build)
    for backend, floor in [('nb', 0), ('nb_abi', 0x030C0000)]:
        env = dict(os.environ, BENCH_TEST_MODULES=f'bench_{backend}')
        run([sys.executable, '-m', 'pytest', '-q', 'tests/test_bindings.py'], env=env)
        run([sys.executable, '-c', f'import sys; sys.path.insert(0,{str(modules)!r}); import bench_{backend} as m; assert m.abi_floor == {floor}; assert m.__file__.startswith({str(modules)!r})'])
    metadata = dict(suite='abi', fast=args.fast, test_only=args.test_only, order=args.order,
                    run_python=sys.version, executable=sys.executable, platform=platform.platform(),
                    processor=platform.processor(), stable_manifest=original, reused=bool(args.reuse),
                    stable_sha256=digest(stable), ordinary_sha256=digest(modules / ordinary.name),
                    build_info=info, audit=audit, status='correctness-passed')
    metadata['measurement_sources'] = {str(p.relative_to(ROOT)): digest(p) for p in
        [ROOT / 'scripts/abi.py', ROOT / 'scripts/report_abi.py', ROOT / 'benchmarks/runtime.py', ROOT / 'CMakeLists.txt']}
    for filename in ['compile_commands.json', 'build-info.json']:
        shutil.copy2(build / filename, output / filename)
    (output / 'environment.json').write_text(json.dumps(metadata, indent=2), encoding='utf-8')
    if not args.test_only:
        backends = ['nb', 'nb_abi'] if args.order == 'ordinary-first' else ['nb_abi', 'nb']
        for backend in backends:
            run([sys.executable, 'benchmarks/runtime.py', '--backend', backend, '--output', output / f'{backend}.json',
                 '--inherit-environ', 'BENCH_MODULE_DIR,BENCH_BUILD_DIR'] +
                (['--processes', '2', '--values', '2', '--warmups', '1', '--min-time', '0.01'] if args.fast else []))
        run([sys.executable, 'scripts/report_abi.py', output])
    if digest(stable) != original['sha256'] or digest(artifact) != original['sha256']:
        raise RuntimeError('Stable binary changed during validation/measurement')
    print(f'ABI results: {output}', flush=True)


if __name__ == '__main__':
    main()
