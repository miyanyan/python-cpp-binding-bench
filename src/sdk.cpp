#include "sdk_types.h"
#include <string>
#include <utility>
#ifdef SDK_NANOBIND
#include <nanobind/nanobind.h>
#include <nanobind/stl/shared_ptr.h>
#include <nanobind/stl/unique_ptr.h>
namespace b = nanobind;
#define SDK_MODULE NB_MODULE
#else
#include <pybind11/pybind11.h>
namespace b = pybind11;
#define SDK_MODULE PYBIND11_MODULE
#endif
using namespace SDK_NAMESPACE;

auto value_arg() {
#ifdef SDK_NANOBIND
    return b::arg("value").noconvert(); // None is rejected by default.
#else
    return b::arg("value").noconvert().none(false);
#endif
}

template<typename T> auto bind_class(b::module_& m, const char* name) {
#ifdef SDK_NANOBIND
    return b::class_<T>(m, name);
#elif defined(SDK_SMART_HOLDER)
    return b::class_<T, b::smart_holder>(m, name);
#else
    return b::class_<T, std::shared_ptr<T>>(m, name);
#endif
}
template<std::size_t... I> void tags(b::module_& m, std::index_sequence<I...>) {
    (bind_class<Tag<I>>(m, ("Tag" + std::to_string(I)).c_str()).def(b::init<std::int64_t>()), ...);
    (m.def(("direct" + std::to_string(I)).c_str(), &dispatch<I>, value_arg()), ...);
}
template<std::size_t... I> void overloads(b::module_& m, const char* name, std::index_sequence<I...>) {
    (m.def(name, &dispatch<I>, value_arg()), ...);
}

SDK_MODULE(SDK_NAMESPACE, m) {
    bind_class<Value>(m, "Value").def(b::init<std::int64_t>()).def("get", &Value::get);
    m.def("make_shared", &make_shared);
    m.def("read_shared", &read_shared, value_arg());
    m.def("read_ref", &read_ref, value_arg());
    bind_class<SharedBox>(m, "SharedBox").def(b::init<>())
        .def("set", &SharedBox::set, value_arg())
        .def("clear", &SharedBox::clear).def("get", &SharedBox::get).def("read", &SharedBox::read);
    bind_class<Observer>(m, "Observer").def(b::init<const SharedBox&>())
        .def("expired", &Observer::expired);
    auto parent = bind_class<Parent>(m, "Parent");
    parent.def(b::init<std::int64_t>());
#ifdef SDK_NANOBIND
    parent.def("child", &Parent::get_child, b::rv_policy::reference_internal);
    m.attr("holder") = "nanobind";
#else
    parent.def("child", &Parent::get_child, b::return_value_policy::reference_internal);
#ifdef SDK_SMART_HOLDER
    m.attr("holder") = "pybind11 smart_holder";
#else
    m.attr("holder") = "pybind11 shared_ptr";
#endif
#endif
    m.def("parents_alive", []() { return Parent::alive; });
#if defined(SDK_NANOBIND) || defined(SDK_SMART_HOLDER)
    m.def("make_unique", [](std::int64_t v) { return std::make_unique<Value>(v); });
#ifdef SDK_NANOBIND
    // Required for consuming both Python-inline and C++-allocated instances.
    using Unique = std::unique_ptr<Value, b::deleter<Value>>;
#else
    using Unique = std::unique_ptr<Value>;
#endif
    m.def("consume_unique", [](Unique v) { return v->value; }, value_arg());
#endif
    tags(m, std::make_index_sequence<32>{});
    overloads(m, "dispatch1", std::make_index_sequence<1>{});
    overloads(m, "dispatch4", std::make_index_sequence<4>{});
    overloads(m, "dispatch16", std::make_index_sequence<16>{});
    overloads(m, "dispatch32", std::make_index_sequence<32>{});
}
