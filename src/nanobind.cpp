#include "kernels.h"
#include <nanobind/nanobind.h>
#include <nanobind/ndarray.h>
#include <nanobind/stl/vector.h>
#include <nanobind/stl/shared_ptr.h>
#include <nanobind/stl/function.h>
namespace nb = nanobind;
NB_MODULE(bench_nb, m) {
    m.def("noop", &kernel::noop);
    m.def("add", &kernel::add, nb::arg("a"), nb::arg("b"));
    m.def("work", &kernel::work);
    m.def("vector_sum", &kernel::vector_sum);
    m.def("vector_echo", &kernel::vector_echo);
    m.def("callback", &kernel::callback);
    nb::class_<kernel::Value>(m, "Value")
        .def(nb::init<std::int64_t>()).def("get", &kernel::Value::get);
    m.def("make_shared", &kernel::make_shared);
    m.def("read_shared", &kernel::read_shared);
    m.def("identity", [](kernel::Value& v) -> kernel::Value& { return v; }, nb::rv_policy::reference);
    using Array = nb::ndarray<nb::numpy, const double, nb::ndim<1>, nb::c_contig, nb::device::cpu>;
    m.def("array_sum", [](const Array& x) { return kernel::sum(x.data(), x.size()); }, nb::arg("x").noconvert());
    m.def("array_address", [](const Array& x) { return reinterpret_cast<std::uintptr_t>(x.data()); }, nb::arg("x").noconvert());
}
