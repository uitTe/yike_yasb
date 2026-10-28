# YASB Yike

适用于 Windows 10 与 Windows 11 的状态栏，使用 Python 与 PyQt6 编写，基于 [amnweb/yasb](https://github.com/amnweb/yasb) 修改。

本项目提供简体中文界面、顶部窗口标签、底部 Dock、可视化配置页面、Codex 用量统计和天气位置设置。

## 项目功能

| 功能 | 本项目的修改 |
| --- | --- |
| Codex 用量 | 显示账户额度与重置时间，合并本机会话日志和数据库累计用量，统计模型分布与每日活动；支持在界面设置 Codex 程序路径 |
| 天气 | Open-Meteo 天气弹窗支持城市搜索与自定义经纬度，位置保存到配置文件；天气详情、预报和小时曲线支持简体中文 |
| 顶部状态栏 | 每个运行窗口对应一个标签，支持切换、最小化、关闭及超出可用宽度时滚动；顶部栏可以折叠 |
| 底部 Dock | 读取 Windows 固定应用，支持拖动排序、取消固定、开始菜单入口及多显示器共享顺序 |
| 系统任务栏 | Dock 接管系统任务栏，独立进程在程序退出后恢复任务栏状态 |
| 可视化配置 | 独立配置窗口，支持组件搜索、添加、移除和必要输入设置；保存时校验配置并保留 YAML 注释 |
| 界面语言 | 简体中文与英文切换，涵盖菜单、组件、配置窗口及 Qt 原生控件 |
| 窗口行为 | 包含 Codex 窗口恢复、窗口显示顺序、多显示器、Win+D 和标签溢出相关修改 |

默认配置包含顶部状态栏与底部 Dock，读取程序目录的 `defaults` 文件夹，保存配置和样式后自动重新加载。

## 运行环境

| 项目 | 要求 |
| --- | --- |
| 系统 | Windows 10 或 Windows 11 |
| Python | 3.14 及以上 |
| 界面框架 | PyQt6 6.10.2 |
| 项目版本 | 1.0.0 |
| 许可 | MIT |

安装包包含 Python 与运行依赖。源码运行与构建使用 [pyproject.toml](pyproject.toml) 中的依赖。

## 源码运行

```powershell
git clone https://github.com/uitTe/yike_yasb.git
cd yike_yasb
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe src/main.py
```

使用 Codex 用量组件时，需要安装 Codex 并完成自己的账户登录。配置页面中的 Codex 程序路径可以填写可执行文件的完整路径。

## 配置与数据

| 文件 | 用途 |
| --- | --- |
| [config.yaml](src/defaults/config.yaml) | 状态栏、Dock、组件及语言配置 |
| [styles.css](src/defaults/styles.css) | 主样式及其他样式文件的引用 |
| [topbar.css](src/defaults/topbar.css) | 顶部状态栏样式 |
| [dock.css](src/defaults/dock.css) | Dock 样式 |
| [codex_usage.css](src/defaults/codex_usage.css) | Codex 用量组件与弹窗样式 |
| [schema.json](schema.json) | 配置结构，供编辑器校验使用 |

右键点击托盘图标，选择“打开配置页面”，可以编辑组件与状态栏。保存后自动重新加载的行为由 `watch_config` 和 `watch_stylesheet` 控制。

程序配置固定保存在自身的 `defaults` 目录。天气和用量缓存默认保存在 `%LOCALAPPDATA%\YASB`，Dock 固定应用数据默认保存在程序目录的 `data` 文件夹。设置 `YASB_DATA_HOME` 可以统一指定运行数据目录。仓库忽略运行数据、日志和凭据。

## 构建

```powershell
cd src
..\.venv\Scripts\python.exe build.py build
..\.venv\Scripts\python.exe build.py bdist_msi
```

应用目录输出到 `src/dist`，安装包输出到 `releases`，安装包名称包含北京时间戳。安装目录包含以下程序：

| 程序 | 用途 |
| --- | --- |
| `yasb.exe` | 状态栏主程序 |
| `yasbc.exe` | 命令行工具 |
| `yasb_settings.exe` | 可视化配置页面 |
| `yasb_taskbar.exe` | 系统任务栏恢复进程 |

构建使用的默认配置、示例配置、语言说明和配置页面说明均保存在仓库中。

## 测试

```powershell
.\.venv\Scripts\python.exe -m pytest
```

保留的测试覆盖组件导入、配置结构、中文界面、配置保存与监听、Codex 用量、天气、窗口标签和 Windows 接口。Windows SDK 检查需要安装 Visual Studio 或包含 C++ 工具与 Windows SDK 的 Build Tools。

部分检查需要本机 Codex 登录记录、天气缓存或对应的硬件驱动，缺少这些条件时会显示跳过原因。测试会创建独立运行数据目录。

## 项目文档

| 文档 | 内容 |
| --- | --- |
| [Codex 用量](docs/codex-usage.md) | 账户额度、本地用量、程序路径与统计范围 |
| [天气组件](docs/weather.md) | 城市搜索、经纬度与中文天气详情 |
| [配置页面](docs/settings-page.md) | 组件与状态栏的编辑方式 |
| [默认配置](docs/default-config.md) | 配置目录与发布维护方式 |
| [语言设置](docs/language.md) | 中文与英文界面的切换 |
| [Dock 固定应用](docs/dock-pinned-apps.md) | 排序、取消固定与数据保存 |
| [系统任务栏](docs/taskbar-replacement.md) | 任务栏接管与退出恢复 |

## 仓库内容

仓库保留源码、运行资源、构建配置、项目说明及相关测试。上游参考资料集中保存在 `work/upstream`，实验内容保存在 `work/experiments`，本地报告与验证输出保存在 `work` 中。[.gitignore](.gitignore) 统一忽略 `work`，并忽略开发工具配置、虚拟环境、构建产物、运行数据、日志和安装包。

## 许可与来源

本项目由 [amnweb/yasb](https://github.com/amnweb/yasb) 修改而来，上游项目派生自 [da-rth/yasb](https://github.com/da-rth/yasb)。项目及上游的 MIT 版权声明保存在 [LICENSE](LICENSE) 中。

其他第三方来源、版权声明和依赖发布条件见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。本项目源码采用 MIT；PyQt6 采用 GPLv3 或商业许可。使用 GPLv3 版 PyQt6 分发组合程序时，需要遵守 GPLv3 并提供完整对应源码及构建所需文件。Qt、certifi 等依赖同时保留各自的许可要求。
