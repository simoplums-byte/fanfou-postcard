# Fanfou Postcard（饭否明信片）

饭否个人数据备份与长期保存项目。目前处于调研阶段，尚未把任何实现选为正式基线。

## 当前结论

- 不建议直接运行 `heedless/fanfou-backup`。它的最后一次提交是 2016 年，依赖 Python 2，并使用 HTTP、旧版 OAuth 库和项目目录内明文令牌数据库。
- 该项目的核心思路仍然有效：通过 OAuth 调用 `statuses/user_timeline`，逐页获取消息，保存服务端返回的原始 JSON。
- 旧 `fanfou-echo` 的现有 `data/timeline.json` 不是个人备份：它只有王兴的 60 条公开消息，可作为解析测试样本，不能作为个人历史数据源。
- `fanfou-echo` 是 `mcxiaoke/pyfanfou` 的延续改造，并非来自 `heedless/fanfou-backup`。它的代码比后者更有复用价值：已有 Python 3、OAuth 1.0、SQLite 增量存储、照片下载和多格式渲染。但尚未用有效饭否应用凭据和真实账号完成端到端验证。
- OAuth 应用创建、PIN 授权和 access token 签发均已实测成功；但应用仍为“未审核”，受保护 API 对账号验证和一页时间线均返回 HTTP 401“参数错误”。下一步应先解决应用审核/权限，再进入完整导出实现。

完整证据、风险和建议见 [调研报告](docs/research-2026-09-08.md)。

## 项目边界（调研阶段）

长期备份的权威文件应是尽量保留 API 原始字段的 JSON；SQLite、HTML、Markdown、CSV 等是索引或查看副本，不应反过来限制原始数据结构。首次实测只读取当前账号的少量消息，不发布、不删除、不批量下载照片。
