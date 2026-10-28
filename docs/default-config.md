# 内置默认配置

安装包将 `src/defaults` 中的 `config.yaml`、`styles.css`、`topbar.css`、`dock.css` 和 `codex_usage.css` 安装到程序的 `defaults` 目录。
这些文件包含 YASB Yike 的顶部栏、底部 Dock 和简体中文设置。

程序启动时直接读取自身 `defaults` 文件夹中的配置和样式。托盘和关于页面中的“打开配置文件夹”均打开这个文件夹，`yasbc --config` 输出其完整路径。

配置字段严格按照当前程序的配置结构校验，未知字段和废弃字段会触发错误。

发布默认配置时，修改 `src/defaults` 并重新构建程序和 MSI。配置引用的样式资源需要一起维护。配置或样式文件缺失时，程序终止启动。

安装包输出目录为项目根目录下的 `releases`，名称包含北京时间的年月日时分秒。
