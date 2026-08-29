# 增加 Tagalog 翻译端口技术方案

## 1. 目标与范围

在保持现有 `/anx-reader` 行为、响应格式和上游配置完全不变的前提下，新增 `/anx-reader-tagalog`。新端口接收与 `/anx-reader` 相同的 OpenAI Chat Completions 请求，将英文单词或句子翻译为 Tagalog（菲律宾语）。

本次改造覆盖以下三个入口，确保客户端使用不同的 OpenAI 兼容路径时都有一致能力：

| 现有中文端口 | 新增 Tagalog 端口 |
| --- | --- |
| `/anx-reader` | `/anx-reader-tagalog` |
| `/anx-reader/chat/completions` | `/anx-reader-tagalog/chat/completions` |
| `/anx-reader/v1/chat/completions` | `/anx-reader-tagalog/v1/chat/completions` |

不改动 `/zotero`、`/zotero/json` 和现有 `/anx-reader` 的翻译结果。

## 2. 现状分析

当前 Go 服务的请求路径为：`routes.go` 注册 `/anx-reader` → `translationProxy`（`handlers.go`）解析请求并识别单词 → `buildOutgoingPayload`（`payload.go`）注入中文 system prompt → `proxyDeepSeek`（`proxy.go`）转发至上游。

当前 system prompt 写死在 `buildOutgoingPayload` 中：

- 句子要求输出中文释义；
- 单词要求输出一个中文释义及美式、英式音标；
- 单词缓存以 `word_cache.word` 为唯一键，并且内存缓存同样只以英文单词为键。

最后一点是新增语言端口时的关键风险。例如 `/anx-reader` 已缓存 `example → 例子` 后，请求 `/anx-reader-tagalog` 的 `example` 会直接返回“例子”，不会请求模型。因此语言必须进入缓存键与数据库唯一约束，不能只增加路由和提示词。

## 3. 设计方案

### 3.1 将目标语言抽象为翻译配置

新增内部 `TranslationProfile`（名称可按项目代码风格调整），由以下字段构成：

| 字段 | 含义 | 中文 Anx Reader | Tagalog Anx Reader |
| --- | --- | --- | --- |
| `Name` | 日志中的端点名称 | `Anx-Reader` | `Anx-Reader Tagalog` |
| `TargetLanguage` | 缓存隔离用的稳定语言标识 | `zh-CN` | `tl` |
| `SentencePrompt` | 句子翻译 system prompt | 现有中文提示词 | Tagalog 句子提示词 |
| `WordPrompt` | 单词翻译 system prompt | 现有中文提示词 | Tagalog 单词提示词 |

`translationProxy`、`buildOutgoingPayload` 和缓存读写方法接收该 profile（或至少接收 `targetLanguage`），替代以端点名称字符串和硬编码提示词来控制行为。默认 profile 仍使用原来的中文提示词，以保证 `/zotero` 与旧 Anx Reader 端口兼容。

### 3.2 Tagalog 提示词

建议使用明确、低歧义的中文指令，保持原有客户端可显示的简短结果：

```text
句子：你是一个智能翻译助手。将下面的英文句子翻译成自然、常用的 Tagalog（Filipino）。仅输出译文，不要解释、不要输出思考过程。示例：输入：I want to go home 输出：Gusto kong umuwi. ./no_think

单词：你是一个智能翻译助手。将下面的英文单词翻译为最常用的一个 Tagalog（Filipino）释义，并给出美式音标和英式音标。严格按以下格式输出：
Tagalog：<最常用释义>
American IPA：/<IPA>/
British  IPA：/<IPA>/
不要添加解释或思考过程。 ./no_think
```

说明：Tagalog 也常被称为 Filipino；提示词中并列两种名称可降低模型将目标语言误识别为其他菲律宾语支的概率。单词输出字段使用 `Tagalog` 而非“释义”，让 UI 或人工排查时能一眼识别目标语言；如客户端对字段文案有严格解析要求，则改为沿用当前“释义”字段，仅替换其内容语言。

### 3.3 路由与配置

1. 在 `config.go` 的默认 `Routes` 中增加 `anx_reader_tagalog: "/anx-reader-tagalog"`。
2. 在 `config.json` 的 `routes` 中增加同名项，确保服务信息接口 `GET /` 能发现新入口。
3. 在 `routes.go` 注册上述三个 POST 路由，均传入 Tagalog profile。
4. 旧的三个 `/anx-reader*` 路由继续传入中文 profile，路由、请求体、`stream` 行为和上游模型选择逻辑均不改变。

建议路由注册使用配置值作为基础路径，并由该基础路径拼接 `/chat/completions` 与 `/v1/chat/completions`，避免今后修改配置时主路径与兼容路径不一致。

### 3.4 缓存隔离与迁移

将缓存的逻辑唯一键从 `word` 调整为 `(target_language, word)`：

| 层级 | 当前 | 改造后 |
| --- | --- | --- |
| 内存缓存键 | `example` | `zh-CN:example`、`tl:example` |
| MySQL 字段 | `word`（唯一） | `word`、`target_language`（组合唯一） |
| 查询条件 | `WHERE word = ?` | `WHERE target_language = ? AND word = ?` |

数据库迁移步骤：

1. 为 `word_cache` 新增非空字段 `target_language VARCHAR(16)`，默认值 `zh-CN`；这样已有中文缓存仍可继续使用。
2. 删除现有 `word` 的唯一索引。
3. 建立组合唯一索引 `uniq_target_language_word(target_language, word)`，并保留按 `word` 查询所需的普通索引（如确有其他查询场景）。
4. 更新 GORM `WordCache` 结构体标签及 `getCachedWord`、`cacheWordTranslation` 调用签名。

迁移须以显式 SQL 或版本化迁移执行，不应仅依赖 `AutoMigrate` 自动调整唯一索引；后者通常不会安全地删除已有索引。上线前须先备份 `word_cache` 表。

## 4. 具体实施清单

1. 在新文件（例如 `translation_profile.go`）定义 profile、中文默认提示词和 Tagalog 提示词。
2. 修改 `payload.go`，按照 profile 和输入类型选择提示词。
3. 修改 `handlers.go`，使 `translationProxy` 接受 profile 并将目标语言向下传递。
4. 修改 `proxy.go` 和 `database.go`，按语言读取、写入内存及 MySQL 单词缓存。
5. 修改 `WordCache` 模型并执行数据库迁移。
6. 修改 `config.go`、`config.json`、`routes.go`，注册三个新路径。
7. 增加单元测试与 HTTP 路由测试，并补充 README/curl 示例。

## 5. 验收与测试

### 自动化测试

- 请求 `/anx-reader-tagalog` 的句子时，上游 payload 的 system message 包含 `Tagalog（Filipino）`，且不包含中文翻译要求。
- 请求旧 `/anx-reader` 时，上游 payload 仍包含原有中文 system prompt。
- 三个 Tagalog 路径都能进入同一 Tagalog profile。
- `example` 在 `zh-CN` 和 `tl` 下能分别存取不同结果，互不命中。
- Tagalog 单词缓存命中时，流式和非流式响应均保持当前 OpenAI 兼容结构。
- 非 JSON 请求、空 messages、上游非 200 和上游流式错误的返回行为与现有端口一致。

### 手工联调

```bash
curl -X POST http://127.0.0.1:13234/anx-reader-tagalog \
  -H 'Content-Type: application/json' \
  -d '{
    "model": "DeepSeek-V3",
    "messages": [{"role": "user", "content": "I want to go home"}],
    "temperature": 0,
    "stream": false
  }'
```

预期 `choices[0].message.content` 为自然的 Tagalog 译文（如 `Gusto kong umuwi.`），不应出现中文翻译或解释。另以 `example` 分别请求中文与 Tagalog 端口两次，确认缓存内容独立。

## 6. 发布与回滚

发布顺序为：先执行数据库迁移，再部署应用，最后进行上述接口冒烟测试。新增端口不影响旧接口；如需回滚应用代码，数据库中新增的 `target_language` 字段可暂时保留，旧版本仍可读取原有 `word` 和 `translation_result` 字段。不要在紧急回滚时删除字段或缓存数据。

## 7. 完成定义

当三个 `/anx-reader-tagalog*` 端点均可返回 Tagalog，中文端口行为不变，且同一英文单词在中文与 Tagalog 端口之间不会共享缓存结果时，本需求完成。
