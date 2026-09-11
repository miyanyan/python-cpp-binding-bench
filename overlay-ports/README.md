# Python-free binding ports

Copied from microsoft/vcpkg commit `2890dc0b684a80c1d86cb8dad0c7434d2e77a5bb`:

- `ports/pybind11` version 3.1.0
- `ports/nanobind` version 3.0.0

Only the `python3` dependencies in the two manifests are removed. The upstream
portfiles, source archive hashes and usage files are retained unchanged.
The port logic license is retained in `LICENSE.vcpkg.txt`.

pybind11's upstream port installs with `PYBIND11_NOPYTHON=ON`. nanobind installs
its source and CMake files with tests disabled, which returns before Python
discovery. Neither port needs to bind to a particular Python ABI at install time.

The consuming project selects and validates pixi's interpreter, headers and
development libraries. nanobind's runtime is compiled separately in each
consumer build directory. Do not replace this with an empty `python3` port:
such a port would claim to satisfy unrelated consumers' Python requirements.
