# apipaw-spec

**APIPaw 算力网络的协议规范集（Protocol Specifications）。**

本仓库是 APIPaw 各协议文档的**唯一权威源**（single source of truth）：
规范写在这里，代码按规范实现，规范变更必须递增版本号。

> ⚠️ 本仓库**只有规范，没有可执行代码**。
> 想跑起来看效果，请用下面三个实现仓。

---

## 规范清单

| 文档 | 版本 | 内容 | 实现位置 |
|---|---|---|---|
| [`PAWMODEL.md`](PAWMODEL.md) | 1.1.0 | **模型包与清单哈希规范**：9 个标准字段 + 别名归一 + 校验规则 + `system_prompt_sha256` / `manifest_sha256` 清单哈希锁 + 上架与 85/15 版税口径 | `apipaw/apipaw-cloud` → `pawmodel_manifest.py` |
| [`POI-PROTOCOL.md`](POI-PROTOCOL.md) | 1.0.0 | **推理证明（PoI）协议**：HMAC-SHA256 收据 + canonical 口径 + 5% 确定性抽检 + Token 膨胀 / 低熵两道防欺诈守卫 + Slashing 扣罚 | 节点侧 `apipaw/apipaw-agent` → `receipt_signing.py`；网关侧 `apipaw/apipaw-cloud` → `poi_engine.py` |

---

## 三个实现仓

| 仓库 | 角色 |
|---|---|
| [`apipaw/apipaw-cloud`](https://github.com/apipaw/apipaw-cloud) | 云端网关：计费、双账本、PoI 校验、Model DAO |
| [`apipaw/apipaw-agent`](https://github.com/apipaw/apipaw-agent) | 节点客户端：本地推理引擎（Ollama / vLLM / llama.cpp）、派单执行、收据签名 |
| [`apipaw/apipaw-pocket`](https://github.com/apipaw/apipaw-pocket) | 买家 / 创作者控制台（Expo SDK 58，当前交付形态为 Web / PWA） |

---

## 规范与实现的一致性怎么保证

规范不是"写了就算数"，它有**机器校验**：

- **CI**：三个实现仓的 GitHub Actions 流水线每次 push/PR 都跑各自的全量用例；
  云端另有 `python:3.6-slim` 容器作业，保证**生产源站的 Python 3.6.8 语法红线**
  在 CI 里被真实执行（不只是"看起来兼容"）。
- **跨仓协议用例**：云端的派单协议 / 模型解析用例在 CI 里会**检出 Agent 仓源码**
  做逐字节对照（`APIPAW_AGENT_REPO`）⇒ 云端与节点的协议漂移会被立刻发现。
- **哈希锁**：模型包的 `manifest_sha256` 是**可复算的指纹**，任何一格改动都会
  让指纹变，而旧指纹仍留在账本里。

---

## 参与贡献

- 规范变更请开 PR，并**递增对应文档的版本号**（破坏性变更递增主版本号）；
- 实现仓的 PR 请附上与本规范的一致性说明；
- 协议口径（canonical 串、分隔符、编码、大小写）**任何改动都属破坏性变更**。

## 许可证

MIT，见 [LICENSE](LICENSE)。
