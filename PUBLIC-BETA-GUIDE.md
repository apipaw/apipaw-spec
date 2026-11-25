# APIPaw 种子公测快速接入指南（Public Beta Guide）

> **面向对象**：想用**官方 OpenAI SDK / Cursor / Cherry Studio**零改造接入
> APIPaw 算力网络的开发者与种子公测用户。
>
> **版本**：1.0.0 · **最后更新**：2026-11-25 · **状态**：公开测试（Public Beta）

---

## 0. 一句话

把客户端里的 `base_url` 从 `https://api.openai.com/v1` 换成
`https://cloud.apipaw.com/v1`，把 API Key 换成你的 `paw-sk-...`，
**其余一个字都不用改** —— 官方 `openai` Python / JS SDK、Cursor、Cherry Studio
都能直接用。

---

## 1. 端点一览

| 能力 | 路径 | 兼容性 |
|---|---|---|
| 模型目录 | `GET /v1/models` | `{"object": "list", "data": [...]}`，与 OpenAI 一致 |
| 聊天补全 | `POST /v1/chat/completions` | 非流式 / SSE 流式均与 OpenAI 一致 |
| 兼容的模型名 | 见 `GET /v1/models` 的 `data[].id` | 例：`qwen2.5:0.5b`、`deepseek-r1` |

> ⚠️ **只有 `/v1/*` 是 OpenAI 兼容面**。`/api/v1/*` 是 APIPaw 自己的
> 业务接口（账本、结算、PoI、DAO…），语义与 OpenAI 无关，不要混用。

---

## 2. Python（官方 `openai` SDK）

```bash
pip install -U openai
```

```python
from openai import OpenAI

client = OpenAI(
    api_key="paw-sk-xxxxxxxxxxxxxxxx",          # 你的 APIPaw Key
    base_url="https://cloud.apipaw.com/v1",     # ← 唯一需要改的地方
)

# 非流式
resp = client.chat.completions.create(
    model="qwen2.5:0.5b",
    messages=[{"role": "user", "content": "用一句话解释默克尔树"}],
)
print(resp.choices[0].message.content)
print(resp.usage.total_tokens)

# 流式（标准 SSE，末尾 data: [DONE]）
stream = client.chat.completions.create(
    model="qwen2.5:0.5b",
    messages=[{"role": "user", "content": "写一首关于算力的短诗"}],
    stream=True,
)
for chunk in stream:
    if chunk.choices and chunk.choices[0].delta.content:
        print(chunk.choices[0].delta.content, end="", flush=True)
```

**不需要**加任何自定义 header、不需要 `extra_body`、不需要改 SDK。

---

## 3. Node.js（官方 `openai` npm 包）

```bash
npm i openai
```

```javascript
import OpenAI from "openai";

const client = new OpenAI({
  apiKey: process.env.APIPAW_API_KEY,          // paw-sk-...
  baseURL: "https://cloud.apipaw.com/v1",       // ← 唯一需要改的地方
});

const stream = await client.chat.completions.create({
  model: "qwen2.5:0.5b",
  messages: [{ role: "user", content: "你好" }],
  stream: true,
});

for await (const part of stream) {
  process.stdout.write(part.choices[0]?.delta?.content ?? "");
}
```

---

## 4. Cursor

`Cursor → Settings → Cursor Settings → Models → OpenAI API Key`

| 字段 | 填什么 |
|---|---|
| Override OpenAI Base URL | `https://cloud.apipaw.com/v1` |
| API Key | 你的 `paw-sk-...` |

> 若你的 Cursor 版本没有「Override Base URL」这一项，请升级到最新版；
> 旧版 Cursor 把 base URL 写死，无法指向第三方兼容端点。

---

## 5. Cherry Studio

`设置 → 模型服务 → 添加 OpenAI 服务`

| 字段 | 填什么 |
|---|---|
| API 地址 | `https://cloud.apipaw.com/v1` |
| API Key | 你的 `paw-sk-...` |
| 模型 | 从「获取模型列表」拉取，或手填 `data[].id` |

---

## 6. 错误体与错误码

所有错误都返回 OpenAI 标准结构：

```json
{ "error": { "message": "请求过于频繁，请稍后再试（每分钟最多 60 次）",
             "type": "rate_limit_error",
             "code": "rate_limit_exceeded" } }
```

| HTTP | `type` | 典型 `code` | 含义 |
|---|---|---|---|
| 400 | `invalid_request_error` | `invalid_request` | 请求体字段不合法（缺 `model` 等） |
| 401 | `authentication_error` | `missing_api_key` / `invalid_api_key` | 缺 Key 或 Key 无效 |
| 403 | `permission_error` | `api_key_frozen` / `scope_not_allowed` / `ip_not_allowed` | Key 被冻结 / 授权范围不足 / IP 不在白名单 |
| 404 | `invalid_request_error` | `model_not_found` | 模型不在目录里 |
| 429 | `rate_limit_error` | `rate_limit_exceeded` | 触发限流（响应带 `Retry-After` 头） |

**限流口径**（刻意宽松，正常使用不会被打断）：

* 账户维度：**60 次/分钟**；
* IP 维度：**300 次/分钟**（运营商 CGNAT / 企业出口共享 IP，所以给得宽）；
* 被限流的请求**不扣费、不计账**（闸门在预扣之前）。

---

## 7. 兼容矩阵（阶段二十五 P1 实测）

| 项目 | 状态 |
|---|---|
| `GET /v1/models` → `{"object":"list","data":[{id,object:"model",created,owned_by}]}` | ✅ |
| 非流式 → `id` / `object` / `created` / `model` / `choices[0].message` / `finish_reason` / `usage` | ✅ |
| 流式 → `object="chat.completion.chunk"` / `choices[0].delta` / 末帧 `finish_reason` / `data: [DONE]` | ✅ |
| 400 / 401 / 403 / 429 → `{"error":{message,type,code}}` | ✅ |
| 错误请求零扣费 | ✅ |

> 契约测试在实现仓里：`apipaw/apipaw-cloud` → `test_phase25_openai_compat.py`
> （33 条断言，每次 CI 必跑）。

---

## 8. 密钥与计费

* Key 形如 `paw-sk-<32 hex>`，**只在你签发的那一刻出现一次**，
  服务端只存 `sha256` 摘要 —— 丢了只能重签，捡不回来；
* 推理按 **token 计费**，账本在 `balance_ledger`，
  每行都能用默克尔包含性证明独立核验；
* 余额不足会返回 `402`，请在控制台充值（`pocket.apipaw.com`）。

---

## 9. 出问题怎么办

| 现象 | 先查 |
|---|---|
| 401 | Key 是否复制完整（前面有没有空格）、是否已被吊销 |
| 403 `scope_not_allowed` | 这把 Key 的 `scopes` 是否包含 `chat` |
| 404 `model_not_found` | 先 `GET /v1/models` 看目录里的准确 id |
| 429 | 看 `Retry-After`，退避后重试（客户端建议指数退避） |
| 回答慢/空 | 先看 `GET /api/v1/network/health` 与节点在线情况 |

---

## 10. 协议规范索引

| 文档 | 内容 |
|---|---|
| [`PAWMODEL.md`](PAWMODEL.md) | 模型包与清单哈希规范 |
| [`POI-PROTOCOL.md`](POI-PROTOCOL.md) | 推理证明（PoI）协议 |
| [`checkpoints/README.md`](checkpoints/README.md) | 默克尔状态根的公开外部锚定（检查点链） |

## 许可证

MIT，见 [LICENSE](LICENSE)。
