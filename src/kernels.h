#pragma once
#include <cstddef>
#include <cstdint>
#include <functional>
#include <memory>
#include <vector>

namespace kernel {
inline void noop() {}
inline std::int64_t add(std::int64_t a, std::int64_t b) { return a + b; }
// Unsigned recurrence with a data dependency; returned value prevents dead-code elimination.
inline std::uint64_t work(std::uint64_t seed, std::size_t iterations) {
    for (std::size_t i = 0; i < iterations; ++i)
        seed = seed * UINT64_C(6364136223846793005) + UINT64_C(1442695040888963407);
    return seed;
}
inline double sum(const double *x, std::size_t n) {
    double result = 0;
    for (std::size_t i = 0; i < n; ++i) result += x[i];
    return result;
}
inline double vector_sum(const std::vector<double>& x) { return sum(x.data(), x.size()); }
inline std::vector<double> vector_echo(const std::vector<double>& x) { return x; }
inline std::int64_t callback(const std::function<std::int64_t(std::int64_t)>& f,
                             std::size_t n) {
    std::int64_t result = 0;
    for (std::size_t i = 0; i < n; ++i) result += f(static_cast<std::int64_t>(i));
    return result;
}
struct Value {
    std::int64_t value;
    explicit Value(std::int64_t v) : value(v) {}
    std::int64_t get() const { return value; }
};
inline std::shared_ptr<Value> make_shared(std::int64_t v) { return std::make_shared<Value>(v); }
inline std::int64_t read_shared(const std::shared_ptr<Value>& v) { return v->value; }
}
