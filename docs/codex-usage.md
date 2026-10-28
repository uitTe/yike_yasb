# Codex 用量

组件类型为 `yasb.codex_usage.CodexUsageWidget`。账户额度通过 Codex 的 `app-server` 协议查询，使用 Codex 已有的账户登录状态。每位使用者需要安装 Codex 并登录自己的账户。

## 程序路径

在配置页面添加或选择 Codex 用量组件，填写 Codex 可执行文件的完整路径并保存。也可以在 `defaults/config.yaml` 的组件 `options.codex_path` 中指定路径；默认命令为 `codex`，需要能够通过 `PATH` 找到。

安装位置发生变化后，可以重新设置该路径。

## 账户额度

状态栏显示额度窗口的剩余百分比，弹窗显示用量、重置时间及账户相关信息。刷新间隔由 `update_interval` 控制，`cache_ttl` 控制缓存有效时间。额度查询失败时，组件显示已有缓存及过期状态。

## 本地 token 统计

启用 `show_token_usage` 后，组件读取 Codex 数据目录中的 `sessions`、`archived_sessions` 和版本号最大的 `state_*.sqlite`，合并日志明细与数据库累计用量。

- 同一会话的续接文件先按会话身份合并，再按照时间计算累计计数的增量。
- 重复日志记录不会重复计入用量。
- 数据库使用只读连接，累计值用于补充已经缺少日志的用量。
- 今日、最近七天、最近三十天与最近一年分别统计；模型分布和每日活动依赖保留下来的日志。
- 缺失日志的会话跨越统计时间边界时，对应时间范围显示无法确定的结果。

Codex 数据目录使用 `CODEX_HOME`，未设置时使用当前用户的 `.codex` 目录。仓库只包含组件代码与样式，使用者的账户凭据、会话记录和数据库均保存在本机。

组件样式见 [codex_usage.css](../src/defaults/codex_usage.css)。
