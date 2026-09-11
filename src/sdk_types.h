#pragma once
#include <cstdint>
#include <memory>
#include <stdexcept>
#include <utility>

// Separate C++ identities let tests import all three variants in one interpreter.
// The layouts and operations are identical; only the binding holder changes.
namespace SDK_NAMESPACE {
struct Value {
    std::int64_t value;
    explicit Value(std::int64_t v) : value(v) {}
    Value(const Value&) = delete;
    std::int64_t get() const { return value; }
};
inline std::shared_ptr<Value> make_shared(std::int64_t v) { return std::make_shared<Value>(v); }
inline std::int64_t read_shared(const std::shared_ptr<Value>& v) { return v->value; }
inline std::int64_t read_ref(const Value& v) { return v.value; }

struct SharedBox {
    std::shared_ptr<Value> value;
    void set(std::shared_ptr<Value> v) { value = std::move(v); }
    void clear() { value.reset(); }
    std::shared_ptr<Value> get() const { return value; }
    std::int64_t read() const {
        if (!value) throw std::runtime_error("empty SharedBox");
        return value->value;
    }
};
struct Observer {
    std::weak_ptr<Value> value;
    // Observe the exact control block held by C++, without a Python round trip.
    explicit Observer(const SharedBox& box) : value(box.value) {}
    bool expired() const { return value.expired(); }
};

// Lifetime instrumentation belongs only to correctness fixtures, never timed Value.
struct Parent {
    inline static int alive = 0;
    Value child;
    explicit Parent(std::int64_t v) : child(v) { ++alive; }
    ~Parent() { --alive; }
    Parent(const Parent&) = delete;
    Value& get_child() { return child; }
};

template<int I> struct Tag {
    std::int64_t value;
    explicit Tag(std::int64_t v) : value(v) {}
};
template<int I> std::int64_t dispatch(const Tag<I>& v) { return v.value + I; }
}
