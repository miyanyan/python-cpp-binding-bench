# python-cpp-binding-bench

pybind11、nanobind 与 Cython 的 C++ / Python 绑定对比。

面向选型的可复现 CPU 基准：比较调用、对象、数组转换、计算量增长和绑定规模增长。
**不预设哪个库应该获胜，也不把微基准比例直接解释成业务提速。**

## 工具链

- pixi 管理 Python、Cython、NumPy、pyperf、pytest、matplotlib、CMake 和 Ninja；提交 `pixi.lock` 固定环境。
- vcpkg manifest 管理 **pybind11 3.1.0 / nanobind 3.0.0**；baseline 固定在 `vcpkg.json`。
- `overlay-ports/` 复制该 baseline 的上游 ports，仅移除 `python3` 依赖。没有伪造空 Python port。
  pybind11 用上游 `PYBIND11_NOPYTHON=ON` 安装；nanobind 用 `NB_TEST=OFF` 安装源文件，均不需 Python。
- 主 CMake 项目显式指定 pixi Python，并校验解释器、头文件和已发现的链接库均位于 `CONDA_PREFIX`。
  nanobind 的运行库在消费端构建，随各个 Python 环境独立编译。
- 本机需安装 pixi、已 bootstrap 的 vcpkg，以及 C++17 编译器。Windows 自动发现 Visual Studio C++ 工具链；
  Windows 默认 MSVC，Linux/macOS 默认 `c++`；可通过 `CXX` 指定编译器可执行文件（不含额外参数）。
  设置 `VCPKG_ROOT`，或将 vcpkg 可执行文件放入 PATH。

## 快速开始

```powershell
$env:VCPKG_ROOT = "D:/path/to/vcpkg"
pixi install
pixi run test
pixi run bench-quick
```

默认 Python 3.12。切换版本无需修改全局 Python：

```sh
pixi run -e py310 test
pixi run -e py311 test
pixi run -e py312 bench-quick
pixi run -e py313 test
pixi run -e py314 test
```

构建目录为 `build/<environment>/<profile>`；Python ABI 不同的目标文件不混用。
`build/vcpkg_installed` 仅共享不依赖 Python ABI 的头文件和源文件包。
不要从 vcpkg 或 pip 再安装一套绑定库/Python 来替代此依赖链。

## CMake Presets

`CMakePresets.json` 提供两个 Release 配置，均由 pixi 任务调用：

```sh
pixi run configure
pixi run build --profile native
pixi run test --profile native
pixi run bench --profile matched
```

- `matched`：相同 C++ 标准和 Release 基础优化；pybind11 `NO_EXTRAS`，nanobind `NOMINSIZE NOSTRIP`；
  不启用可选 LTO/裁剪。框架必需的内部编译选项可能仍不同，实际命令保存在结果中。
- `native`：两个框架各自的默认模块辅助函数优化；体现推荐用法，不能视为完全相同的编译参数。
- Windows 使用 Release CPython，因此没有提供需要 debug Python 的 Debug preset。

若直接运行 `cmake --preset matched`，需先激活 pixi 和编译器环境，并将 `BENCH_PYTHON` 设置为 `sys.executable`、`BENCH_CXX` 设置为编译器绝对路径；
推荐使用任务入口，它会自动处理这些步骤。

## 运行时实验

```sh
pixi run bench-quick           # 低样本冒烟，只验证流程
pixi run bench                 # pyperf 标准重复测量；可能需要数分钟
pixi run bench --order nb-first # 次序为 nanobind、Cython、pybind11
pixi run report                # 重建最新完整运行的报告
```

每次生成独立的 `results/<environment>-<profile>-<timestamp>/`，包含：

- `py.json`、`nb.json`、`cy.json`：三方各 40 项 pyperf 原始值及元数据，共 120 项测量。
- `build-info.json`、`environment.json`、`compile_commands.json`：版本、工具链、模块大小和实际编译命令。
- `comparison.csv`：三方长表，每行一个 case/backend，包含均值、标准差、相对 pybind11 的倍率与耗时降低百分比。
  历史双库报告仍支持重建，保留原来的宽表格式；不应混合两种 CSV schema。
- `report.md`、`runtime.png`：表格和计算量/数组长度趋势。

当前包含空调用、位置/关键字参数、对象构造销毁/引用/共享所有权、C++ 回调 Python、
可调迭代计算、list/vector 转换、严格零复制数组归约，以及逐标量调用归约。
`scalar_reduce/N` 与 `array_sum/N` 计算相同的求和任务，但后者将循环移入 C++；数组预先创建，
这是批处理接口的对照，不是包含输入构造成本的端到端应用。

三方使用同一份 `src/kernels.h`，GIL 均保持持有；NumPy 输入为 CPU、一维、C 连续、float64。
输入构造不计时；不匹配 dtype、非连续数组和 list 输入被拒绝，不允许一边偷偷复制。
只读数组应被接受；测试检查指针相同、结果、拷贝语义、对象寿命、回调异常和数据依赖计算。
空数组仅用于测 API 边界；不要给空数组结果计算 ns/元素。

### Cython 包装的范围

`src/cython_bindings.pyx` 使用带类型的 Python `def` 入口调用已有 C++ kernel，
没有将内部 `cdef` 调用速度混入 Python 入口结果。CMake 使用 pixi Python 执行 Cython，
将生成的 `bench_cy.cpp` 编译为扩展模块，不依赖 setuptools 或另一套 Python。
数组使用 NumPy 类型校验和 `const double[::1]` memoryview；对象显式持有 `shared_ptr`，
identity 返回已有 Python 包装。回调通过 `src/cython_bridge.h` 的 CPython C API 桥接进入
同一 `std::function` kernel，并保留原始 Python 异常。这些都是本项目的包装选择，不代表 Cython 的唯一实现。

整数测试覆盖 int64/uint64 边界与越界拒绝；测试输入不触发有符号加法溢出。
这不是完整 Python API 兼容性测试，未承诺所有隐式类型转换规则相同。
Cython 两个 preset 均采用普通 CMake Release 优化，`native` 不额外为其开启 LTO。
当前仅基础运行时套件加入 Cython；SDK 所有权/重载和 `scale` 编译规模仍是原有实现。
Cython 代码生成会在构建日志中显示，但尚未将生成耗时和 C++ 编译耗时独立计量。

## SDK 重载与所有权实验

```sh
pixi run bench-sdk-quick
pixi run bench-sdk --profile matched
pixi run -e py313 bench-sdk --profile native --order nb-first
pixi run report-sdk
```

三种实现来自同一份 `src/sdk.cpp` / `src/sdk_types.h`：显式使用 `std::shared_ptr` holder 的 pybind11、
pybind11 `smart_holder`、nanobind。这里的 `shared_ptr` holder 不是 pybind11 的默认 `unique_ptr` holder。
三模块使用不同 C++ 命名空间以便在正确性测试中同时导入；类布局与操作相同。
性能测量仍在独立的 pyperf 子进程内进行，每个子进程只导入一个变体。

| 方向 | 用例 | 解释边界 |
|---|---|---|
| 重载链长度 | 1、4、16、32 个独特类参数重载，命中首项/中间/末项 | 输入预先创建，传引用并禁止隐式转换；不是数字重载转换实验 |
| 直接调用对照 | 相同参数类型、返回值计算，单独绑定一个签名 | 与相应 `overload_hit` 比较，判断重载查找增加的成本 |
| 无匹配重载 | 传入不支持的对象，并捕获 `TypeError` | 包含错误信息生成、异常传播、Python catch；不能当作纯查找时间 |
| 对象所有权 | 创建销毁、方法、引用读取、shared_ptr 转换、已有包装对象返回、容器持有/释放 | 区分 Python 创建与 C++ 创建的对象；返回已有对象不代表新建包装的成本 |
| 独占所有权 | Python/C++ 创建对象后通过 unique_ptr 消费 | 包含创建、转移、销毁、Python 测试函数开销；shared_ptr-only 变体明确标为 N/A |

Python 创建对象的 `shared_read` 不预先保留额外的 C++ shared_ptr，以测量该路径的转换成本；
C++ 创建对象的用例单独记录。nanobind 的 unique_ptr 消费参数使用 `nb::deleter<T>`，以支持 Python 内联对象。
这项绑定签名差异属于迁移成本，不能忽略。

正确性测试逐一检查每个重载选择、非法参数拒绝（含进入 C++ 前拒绝 `None`）、删除 Python 引用后 C++ 容器仍持有对象、
清空容器后对象最终释放、`reference_internal` 保持父对象存活、unique_ptr 转移后重复消费被拒绝。
`weak_ptr` 直接观察 C++ 容器的控制块，不假设经 Python 往返后的 shared_ptr 仍保持同一个控制块。
生命周期计数器只用于独立测试夹具，不进入计时的 Value 类型。

结果位于 `results/sdk-<environment>-<profile>-<timestamp>/`：
`py.json`、`smart.json`、`nb.json` 原始值，长表 `comparison.csv`（含 measured/unsupported 状态），
`report.md`、`overloads.png`、`ownership.png`。`report-sdk` 与基础套件的 `report` 分开，旧运行时报告仍可读取。
当前每次三方运行包含 32、34、34 项测量，共 100 项；报告保留不支持的格子，不填零、不凑总体排名。

## 构建规模实验

```sh
pixi run scale --counts 1,10,100,1000 --kind functions --repeats 3 --jobs 2
pixi run scale --counts 1,10,100,1000 --kind classes --repeats 3 --jobs 2
```

自动生成独特模板实例，每个类有构造器和一个方法，所有绑定放在一个翻译单元中。
每次用构建工具 `clean`，分别测两个模块；nanobind 全量构建包含其静态运行库。
依赖下载/安装和 CMake configure 不计入构建耗时。随后仅 touch 当前绑定源文件测增量编译。
记录新 Python 进程内的模块导入耗时（不含解释器启动）、最终 `.pyd/.so` 大小及重复原始值。
以 `scale.json` 为原始输出，另存各规模实际编译命令，生成 `summary.csv` 和 `scale.png` 中位数曲线。默认不启用 ccache/sccache；
正式测量前确认本机编译器未被外部缓存包装。

此处“全量”指干净目标文件构建，**不代表冷文件系统缓存**；动态系统依赖大小不计入模块大小。
当前规模测试没有统计进程树峰值 RSS，也没有公共头文件增量或多翻译单元测试；
不能据此推断超大生产项目的并行构建表现。

## 如何解释

`reduction = (pybind11_time - nanobind_time) / pybind11_time`；负数表示 nanobind 更慢。
记录绝对 ns 和分布；报告标准差不是置信区间。自动图表仅描述均值，不做显著性结论。
历史双库图中的 5% 为阅读参照，不是自动推荐迁移阈值；新版三方图展示绝对耗时，纵轴为对数尺度。使用
`python -m pyperf compare_to results/.../py.json results/.../nb.json --table`
进一步检查差异，并阅读测量过程中的稳定性警告。

正式发布前使用安静、固定电源策略的机器，记录 CPU/系统/编译器/库版本，重复完整实验并改变实现的执行次序；
不要混合不同平台的数字。单次冒烟结果不足以宣称性能优势。
实际任务可先估算 `节省秒数 = 调用次数 × 每次节省秒数`，再跑端到端工作负载确认。
迁移工作量、功能兼容性和 wheel 发布成本应另行评估。

后续扩展：真实应用端到端工作负载、子类虚函数回调、进程树峰值内存、多翻译单元、
重复实验置信区间及阈值区间报告、ABI/wheel 矩阵。GPU、free-threaded Python 不在当前范围。

## 验证范围

GitHub Actions 配置位于 `.github/workflows/ci.yml`，在 push、PR 和手动触发时运行：

- Windows 2022 x64 / MSVC、Ubuntu 24.04 x64 / GCC、macOS 15 ARM64 / Apple Clang。
- 每个平台覆盖 Python 3.10–3.14，共 15 个 job；各自测试 `matched` 和 `native`。
- 每个平台的 Python 3.12 额外运行三方各 40 组基础运行时用例、原有 SDK 套件，以及函数/类各 1、10 个绑定的规模冒烟测试。
- 使用 `pixi.lock` 和固定 pixi 版本；vcpkg checkout 的提交直接读取 `vcpkg.json` 的 baseline。
  验证安装清单没有 `python3`，Python 路径继续由 CMake 校验。
- 无论 job 成功或失败，都尝试上传 JUnit、基准报告、原始数据及构建诊断，保留 14 天。
- Python 3.12 job 会把已完成的运行时、SDK 和编译规模结果表写入 Actions 的 Summary；
  运行时和 SDK 表格可展开阅读，附有 artifact 下载链接。PNG 曲线图仍需下载查看。
  缺失或失败的套件不会显示为成功，需同时查看 job 状态。

CI 运行器上的计时用于检查测量流程，不设性能阈值，也不用于跨平台性能排名。
此工作流需推送到 GitHub 后才能验证远端平台；下述记录是本机已完成的验证。

本机验证（2026-09-11）：Windows x64 / MSVC 19.51；Python 3.10.21、3.11.16、3.12.14、3.13.15、3.14.7
在第一版中各通过 20 项正确性测试。Python 3.12 的 matched/native 配置均通过，40 组双库运行时用例和
函数/类各 1、100 个绑定的规模扫描已完成冒烟验证。Linux/macOS 尚未实际构建验证。
SDK 扩展后，Python 3.10、3.12、3.14 各通过 50 项正确性测试；3.12 的 matched/native 均通过。
Cython 3.3.0 基础包装加入后，同三个 Python 版本各通过 72 项测试（含整数边界、
非本机字节序数组拒绝、回调异常对象保留）；3.12 的 matched/native 均通过。
这些验证说明工具链与测量流程可运行，不构成可发布的迁移阈值结论。

## 上游参考

- [nanobind 基准说明](https://nanobind.readthedocs.io/en/latest/benchmark.html)
- [nanobind 官方 Notebook](https://github.com/wjakob/nanobind/blob/master/docs/microbenchmark.ipynb)
- [pybind11 历史构建规模基准](https://pybind11.readthedocs.io/en/stable/benchmark.html)
- [pyperf 测量方法](https://pyperf.readthedocs.io/en/latest/run_benchmark.html)
- [pybind11 holder 支持范围](https://pybind11.readthedocs.io/en/stable/advanced/smart_ptrs.html)
- [nanobind 所有权实现](https://nanobind.readthedocs.io/en/latest/ownership_adv.html)

overlay ports 沿用 vcpkg 上游端口逻辑和上游源码哈希。升级时同步审核 portfile 和依赖，
不要只修改版本号；上游库许可证由 ports 安装至对应的 `share/<port>/copyright`。
