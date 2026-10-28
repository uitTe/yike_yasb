# 界面语言

在程序文件夹下的 `defaults/config.yaml` 顶层设置 `language`：

```yaml
language: zh_CN
```

支持 `en`（原版英文）和 `zh_CN`（简体中文）。没有填写时使用 `en`，其他取值会触发配置校验错误。

开启 `watch_config: true` 时，修改语言并保存配置即可重新加载应用。关闭配置监听时，使用托盘菜单重新加载 YASB。

示例配置：[英文配置](examples/config.en.yaml)、[中文配置](examples/config.zh_CN.yaml)。使用示例时，将所需文件复制为配置目录中的 `config.yaml`，并保留同目录的 `styles.css`。已有配置只需添加或修改顶层的 `language` 字段。

菜单、应用窗口、系统提示以及组件内置文案随语言设置切换。自定义组件标题、菜单项、标签格式、应用名称、文件路径和远程内容保留原文。

中文模式下，没有单独指定 `clock.locale` 时，时钟使用简体中文日期；组件中明确指定的 `locale` 继续有效。

中文词条位于 `src/core/locales/zh_cn.py`，英文文案作为源码中的词条标识。新增界面文字通过 `core.i18n.tr` 提供两种语言；格式化参数应放在完整词条中。
