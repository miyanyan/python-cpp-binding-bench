import importlib
import os
import sys
import numpy as np
import pyperf

sys.path.insert(0, os.environ['BENCH_MODULE_DIR'])

def add_cmdline_args(cmd, args):
    cmd.extend(['--backend', args.backend])

runner = pyperf.Runner(add_cmdline_args=add_cmdline_args)
runner.argparser.add_argument('--backend', choices=['py', 'nb', 'cy'], required=True)
args = runner.parse_args()
m = importlib.import_module(f'bench_{args.backend}')
runner.metadata['binding_backend'] = args.backend
runner.metadata['build_directory'] = os.environ['BENCH_BUILD_DIR']
runner.metadata['description'] = 'CPU; GIL held; strict zero-copy float64 arrays; inputs preallocated'

runner.bench_func('call/noop', m.noop)
runner.bench_func('call/scalar', m.add, 17, 29)

def keywords(loops):
    f = m.add
    start = pyperf.perf_counter()
    for _ in range(loops):
        f(a=17, b=29)
    return pyperf.perf_counter() - start

runner.bench_time_func('call/keywords', keywords)
value = m.Value(17)
runner.bench_func('object/method', value.get)
runner.bench_func('object/create_destroy', m.Value, 17)
runner.bench_func('object/reference', m.identity, value)
shared = m.make_shared(17)
runner.bench_func('object/shared_read', m.read_shared, shared)
for iterations in [0, 1, 16, 256, 4096, 65536]:
    runner.bench_func(f'work/{iterations}', m.work, 42, iterations)
for size in [0, 1, 16, 256, 4096, 65536, 1000000]:
    x = np.arange(size, dtype=np.float64)
    runner.bench_func(f'array_sum/{size}', m.array_sum, x)
    if size <= 65536:
        values = x.tolist()
        runner.bench_func(f'list_to_vector_sum/{size}', m.vector_sum, values)
        runner.bench_func(f'list_vector_roundtrip/{size}', m.vector_echo, values)

def scalar_reduce(f, n):
    total = 0
    for i in range(n):
        total = f(total, i)
    return total

for size in [1, 16, 256, 4096]:
    runner.bench_func(f'scalar_reduce/{size}', scalar_reduce, m.add, size)
    runner.bench_func(f'callback/{size}', m.callback, lambda x: x + 1, size)
