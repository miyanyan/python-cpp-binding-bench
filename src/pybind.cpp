#include "kernels.h"
#include <pybind11/pybind11.h>
#include <pybind11/numpy.h>
#include <pybind11/stl.h>
#include <pybind11/functional.h>
namespace py = pybind11;
PYBIND11_MODULE(bench_py, m) {
    m.def("noop", &kernel::noop);
    m.def("add", &kernel::add, py::arg("a"), py::arg("b"));
    m.def("work", &kernel::work);
    m.def("vector_sum", &kernel::vector_sum);
    m.def("vector_echo", &kernel::vector_echo);
    m.def("callback", &kernel::callback);
    py::class_<kernel::Value, std::shared_ptr<kernel::Value>>(m, "Value")
        .def(py::init<std::int64_t>()).def("get", &kernel::Value::get);
    m.def("make_shared", &kernel::make_shared);
    m.def("read_shared", &kernel::read_shared);
    m.def("identity", [](kernel::Value& v) -> kernel::Value& { return v; }, py::return_value_policy::reference);
    using Array = py::array_t<double, py::array::c_style>;
    m.def("array_sum", [](const Array& x) {
        if (x.ndim() != 1) throw py::value_error("expected a 1D array");
        return kernel::sum(x.data(), static_cast<std::size_t>(x.size()));
    }, py::arg("x").noconvert());
    m.def("array_address", [](const Array& x) { return reinterpret_cast<std::uintptr_t>(x.data()); }, py::arg("x").noconvert());
}
