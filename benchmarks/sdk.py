"""Independent SDK benchmark suite; each backend runs in separate pyperf workers."""
import importlib
import os
import sys

import pyperf

sys.path.insert(0, os.environ['BENCH_MODULE_DIR'])

def worker_arguments(cmd, args):
    cmd.extend(['--backend', args.backend])

def rejected_call(function, value):
    try:
        function(value)
    except TypeError:
        return
    raise RuntimeError('The no-match fixture unexpectedly accepted the argument')

def set_clear(box, value):
    box.set(value)
    box.clear()

def unique_roundtrip(factory, consume):
    return consume(factory(37))

runner = pyperf.Runner(add_cmdline_args=worker_arguments)
runner.argparser.add_argument('--backend', choices=['py', 'smart', 'nb'], required=True)
args = runner.parse_args()
m = importlib.import_module(f'sdk_{args.backend}')
runner.metadata['binding_backend'] = args.backend
runner.metadata['holder'] = m.holder
runner.metadata['suite'] = 'sdk-v1'
runner.metadata['description'] = 'GIL held; strict class overloads; reference inputs; preallocated except lifecycle cases'

for count in [1, 4, 16, 32]:
    positions = [('first', 0)] if count == 1 else [('first', 0), ('middle', count // 2), ('last', count - 1)]
    function = getattr(m, f'dispatch{count}')
    for position, index in positions:
        value = getattr(m, f'Tag{index}')(42)
        runner.bench_func(f'overload_hit/{count}/{position}', function, value)
        # Same type, payload and return computation, but a single registered signature.
        runner.bench_func(f'overload_direct/{count}/{position}', getattr(m, f'direct{index}'), value)
    runner.bench_func(f'overload_miss/{count}', rejected_call, function, object())

python_value = m.Value(17)
cpp_value = m.make_shared(17)
full_box = m.SharedBox()
full_box.set(cpp_value)
empty_box = m.SharedBox()
runner.bench_func('ownership/construct_destroy', m.Value, 17)
runner.bench_func('ownership/method', python_value.get)
runner.bench_func('ownership/reference_read', m.read_ref, python_value)
runner.bench_func('ownership/shared_read_python_origin', m.read_shared, python_value)
runner.bench_func('ownership/shared_read_cpp_origin', m.read_shared, cpp_value)
runner.bench_func('ownership/shared_factory_destroy', m.make_shared, 17)
runner.bench_func('ownership/shared_return_existing', full_box.get)
runner.bench_func('ownership/shared_set_clear', set_clear, empty_box, cpp_value)
if args.backend in ('smart', 'nb'):
    runner.bench_func('ownership/unique_roundtrip_python', unique_roundtrip, m.Value, m.consume_unique)
    runner.bench_func('ownership/unique_roundtrip_cpp', unique_roundtrip, m.make_unique, m.consume_unique)
