# 第三方内容与依赖许可

本项目的 MIT 许可及 YASB 上游版权声明保存在 [LICENSE](LICENSE)。第三方内容继续适用其原有许可；项目的 MIT 声明不授予其他项目商标或品牌的使用权。

## 源码与随附资源

| 来源 | 使用内容 | 许可与声明 |
| --- | --- | --- |
| [amnweb/yasb](https://github.com/amnweb/yasb) 与 [da-rth/yasb](https://github.com/da-rth/yasb) | 状态栏主体、组件、图片、音效、图标数据、托盘 Hook 源码和 DLL | MIT，完整声明见 [LICENSE](LICENSE) |
| [Everything SDK](https://www.voidtools.com/support/everything/sdk/) | `Everything64.dll`、`EverythingARM64.dll` | MIT，声明见 [Everything-SDK.txt](licenses/Everything-SDK.txt)；SDK 通过 IPC 调用用户安装的 Everything |
| [Ciantic/VirtualDesktopAccessor](https://github.com/Ciantic/VirtualDesktopAccessor) | Windows 虚拟桌面接口定义与 GUID，见 `src/core/widgets/services/windows_desktops/interfaces.py` | MIT，声明见 [VirtualDesktopAccessor.txt](licenses/VirtualDesktopAccessor.txt) |
| [ninthDevilHAUNSTER/ArknightsAutoHelper](https://github.com/ninthDevilHAUNSTER/ArknightsAutoHelper) | `src/core/utils/win32/bindings/combase.py` 中的 HSTRING 实现 | MIT，声明见 [ArknightsAutoHelper.txt](licenses/ArknightsAutoHelper.txt) |
| [Video-Nomad/qt-css-engine](https://github.com/Video-Nomad/qt-css-engine) | 通过依赖安装的 Qt CSS 动画引擎 | MIT，声明见 [qt-css-engine.txt](licenses/qt-css-engine.txt)；依赖固定到 `684e1217d00bf4138ec9bcf6d83c5956ce2ba589` |
| [microsoft/microsoft-ui-xaml](https://github.com/microsoft/microsoft-ui-xaml) | `src/core/ui/tokens.py` 中的颜色定义 | MIT，声明见 [microsoft-ui-xaml.txt](licenses/microsoft-ui-xaml.txt) |

图片、音效、图标数据和托盘 DLL 随 YASB 上游引入。资源中的产品名称和品牌标识用于识别相关应用或服务，相关权利属于各自权利人。

## Python 与 Qt 依赖

`pyproject.toml` 列出项目依赖，安装时由对应软件包提供其许可证。源码仓库不包含 Python 虚拟环境或 Python 依赖的二进制安装文件。

- [PyQt6](https://www.riverbankcomputing.com/static/Docs/PyQt6/introduction.html#license) 提供 GPLv3 和商业许可，PyPI 安装版本采用 `GPL-3.0-only`。MIT 许可允许本项目源码用于 GPLv3 组合程序。分发包含 GPLv3 版 PyQt6 的组合程序时，整体分发需要遵守 GPLv3，包括随附许可、保留版权声明，以及提供完整对应源码、依赖源码和构建所需文件。许可全文见 [GPL-3.0.txt](licenses/GPL-3.0.txt)。
- Qt 运行库、Qt 插件及其内部组件具有各自的许可。使用商业 PyQt6 许可时仍需单独履行所用 Qt 组件的许可条件；使用开源版本时须保留 Qt 的许可文件，并按实际组件履行 LGPLv3/GPLv3 等要求。
- certifi 采用 MPL-2.0；重新分发其文件时需要保留许可并满足其源码提供要求。
- watchdog、tzdata 等采用 Apache-2.0；重新分发时需要保留相应 LICENSE、版权声明及适用的 NOTICE。
- 其他依赖分别采用 MIT、BSD、PSF、MIT-CMU 等许可。打包发布者需要随附实际包含软件包的许可文件，具体内容以对应版本的软件包为准。

本仓库发布源码。安装包的发布者需要针对实际打包的依赖、Qt 模块和资源，完成对应的许可与源码交付。
