import gc
import importlib
import os
import sys
import numpy as np
import pytest

sys.path.insert(0, os.environ['BENCH_MODULE_DIR'])

@pytest.fixture(params=['bench_py', 'bench_nb', 'bench_cy'])
def mod(request):
    return importlib.import_module(request.param)

def test_scalars_and_work(mod):
    assert mod.noop() is None
    assert mod.add(a=17, b=29) == 46
    for count in [0, 1, 16, 256]:
        expected = 42
        for _ in range(count):
            expected = (expected * 6364136223846793005 + 1442695040888963407) & ((1 << 64) - 1)
        assert mod.work(42, count) == expected

@pytest.mark.parametrize('size', [0, 1, 16, 4096])
def test_arrays_and_copies(mod, size):
    x = np.arange(size, dtype=np.float64)
    assert mod.array_address(x) == x.ctypes.data
    assert mod.array_sum(x) == np.sum(x)
    assert mod.vector_sum(x.tolist()) == np.sum(x)
    original = x.tolist()
    result = mod.vector_echo(original)
    assert result == original
    assert result is not original
    x.flags.writeable = False
    assert mod.array_sum(x) == np.sum(x)

@pytest.mark.parametrize('bad', [np.arange(16, dtype=np.float32), np.arange(16., dtype=np.float64)[::2], np.ones((2, 2)), [1., 2.]])
def test_reject_implicit_array_conversion(mod, bad):
    with pytest.raises((TypeError, ValueError)):
        mod.array_sum(bad)

def test_objects_and_callbacks(mod):
    v = mod.Value(17)
    alias = mod.identity(v)
    assert alias is v
    del v
    gc.collect()
    assert alias.get() == 17
    shared = mod.make_shared(29)
    assert mod.read_shared(shared) == 29
    assert mod.callback(lambda x: x + 1, 16) == 136
    def fail(x):
        raise RuntimeError('callback failure')
    with pytest.raises(RuntimeError, match='callback failure'):
        mod.callback(fail, 1)

def test_integer_boundaries(mod):
    assert mod.add((1 << 63) - 1, 0) == (1 << 63) - 1
    assert mod.add(-(1 << 63), 0) == -(1 << 63)
    assert mod.work((1 << 64) - 1, 0) == (1 << 64) - 1
    for function, arguments in [(mod.add, (1 << 63, 0)), (mod.work, (-1, 0)),
                                (mod.work, (0, -1))]:
        with pytest.raises((TypeError, OverflowError, ValueError)):
            function(*arguments)

def test_callback_preserves_exception_object(mod):
    failure = RuntimeError('same exception')
    def fail(value):
        raise failure
    with pytest.raises(RuntimeError) as caught:
        mod.callback(fail, 2)
    assert caught.value is failure
    assert mod.callback(lambda value: value, 0) == 0

@pytest.mark.parametrize('bad', [None, np.arange(4, dtype='>f8')])
def test_reject_null_and_non_native_arrays(mod, bad):
    with pytest.raises((TypeError, ValueError)):
        mod.array_sum(bad)
