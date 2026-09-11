import gc
import importlib
import os
import sys
from contextlib import nullcontext

import pytest

sys.path.insert(0, os.environ['BENCH_MODULE_DIR'])

@pytest.fixture(params=['sdk_py', 'sdk_smart', 'sdk_nb'])
def sdk(request):
    return importlib.import_module(request.param)

@pytest.mark.parametrize('count', [1, 4, 16, 32])
def test_every_overload_selects_the_correct_function(sdk, count):
    dispatch = getattr(sdk, f'dispatch{count}')
    for index in range(count):
        value = getattr(sdk, f'Tag{index}')(42)
        assert dispatch(value) == 42 + index
        assert dispatch(value=value) == 42 + index
        assert getattr(sdk, f'direct{index}')(value) == 42 + index
    # Neither unrelated objects nor numeric inputs may silently convert.
    for wrong in (None, 42, 42.0, object(), sdk.Value(42)):
        with pytest.raises(TypeError):
            dispatch(wrong)
    if count < 32:
        with pytest.raises(TypeError):
            dispatch(getattr(sdk, f'Tag{count}')(42))

@pytest.mark.parametrize('origin', ['python', 'cpp'])
def test_shared_ownership_survives_python_deletion_then_releases(sdk, origin):
    value = sdk.Value(17) if origin == 'python' else sdk.make_shared(17)
    box = sdk.SharedBox()
    box.set(value)
    observer = sdk.Observer(box)
    assert sdk.read_ref(value) == sdk.read_shared(value) == 17
    del value
    gc.collect()
    assert not observer.expired()
    assert box.read() == 17
    alias = box.get()
    box.clear()
    assert alias.get() == 17
    # The Python alias still owns Value; the weak control block may already expire
    # for nanobind's inline Python-origin object, so check only final expiration.
    del alias
    gc.collect()
    assert observer.expired()
    assert box.get() is None
    with pytest.raises(RuntimeError, match='empty SharedBox'):
        box.read()

def test_reference_internal_keeps_parent_alive(sdk):
    before = sdk.parents_alive()
    parent = sdk.Parent(29)
    assert sdk.parents_alive() == before + 1
    child = parent.child()
    del parent
    gc.collect()
    assert child.get() == 29
    assert sdk.parents_alive() == before + 1
    del child
    gc.collect()
    assert sdk.parents_alive() == before

def test_shared_holder_does_not_advertise_unique_transfer():
    sdk = importlib.import_module('sdk_py')
    assert not hasattr(sdk, 'make_unique')
    assert not hasattr(sdk, 'consume_unique')

def test_ownership_rejects_null_before_entering_cpp(sdk):
    box = sdk.SharedBox()
    for function in (sdk.read_shared, sdk.read_ref, box.set):
        with pytest.raises(TypeError):
            function(None)
    if hasattr(sdk, 'consume_unique'):
        with pytest.raises(TypeError):
            sdk.consume_unique(None)

@pytest.mark.parametrize('backend', ['smart', 'nb'])
@pytest.mark.parametrize('origin', ['python', 'cpp'])
def test_unique_transfer_disowns_python_wrapper(backend, origin):
    sdk = importlib.import_module(f'sdk_{backend}')
    value = sdk.Value(37) if origin == 'python' else sdk.make_unique(37)
    assert sdk.consume_unique(value) == 37
    # A second transfer must raise, never access the destroyed C++ instance.
    warning = pytest.warns(RuntimeWarning, match='relinquished instance') if backend == 'nb' else nullcontext()
    with warning:
        with pytest.raises((TypeError, ValueError)):
            sdk.consume_unique(value)

def test_variants_coexist_but_do_not_share_cpp_types():
    py = importlib.import_module('sdk_py')
    smart = importlib.import_module('sdk_smart')
    nb = importlib.import_module('sdk_nb')
    for source, destination in [(py, smart), (smart, py), (py, nb), (nb, py)]:
        with pytest.raises(TypeError):
            destination.read_shared(source.Value(17))
