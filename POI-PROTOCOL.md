# POI —— 推理证明（Proof of Inference）协议

> 协议版本：`1.0.0` ｜ 状态：已落地（生产网关在用）｜ 许可证：MIT
>
> 参考实现：
> * 节点侧：`apipaw/apipaw-agent` 的 `receipt_signing.py`
> * 网关侧：`apipaw/apipaw-cloud` 的 `poi_engine.py`（标准库零第三方依赖）

---

## 0. 要解决的问题

算力网络里，"节点声称它跑过一次推理"是**可以伪造**的：

- 节点可以上报一个与真实输出毫无关系的 token 数；
- 可以返回一坨复读/乱码，却声称是高质量推理；
- 可以把上一次请求的收据**重放**过来。

PoI 协议给每一次**真实节点推理**加一枚**密码学收据**，并配两道防欺诈守卫与一道确定性抽检。

---

## 1. 收据（Receipt）

### 1.1 三要素

节点完成一次推理后，用**只有自己知道的** `node_secret` 签一枚收据：

```
output_sha256 = SHA256( UTF8(output_text) )                      # 小写 hex
canonical     = "{request_id}:{model_id}:{prompt_tokens}:{completion_tokens}:{output_sha256}"
receipt_sig   = HMAC-SHA256( key=UTF8(node_secret), msg=UTF8(canonical) ).hexdigest()   # 小写 hex
```

### 1.2 逐字节口径（**协议，勿改**）

1. canonical 字段顺序固定、冒号分隔、**无空格**；
2. 所有字段用 `str()` 归一（整数不带小数点，字符串原样）；
3. 十六进制一律**小写**；
4. **空输出照样签名**（哈希空串）—— 网关把"空输出"当 `SIMULATED`，
   **不是**当欺诈；
5. `request_id` **永远由网关生成**，节点不得自选 —— 这是重放防护的根。

### 1.3 收据字段（节点 → 网关，JSON 帧）

| 字段 | 类型 | 说明 |
|---|---|---|
| `output_sha256` | str | 输出文本的 SHA256（小写 hex，64 字符） |
| `receipt_sig` | str | HMAC-SHA256 签名（小写 hex，64 字符） |
| `canonical` | str | 规范化串（便于事后逐字节重放） |
| `model_id` | str | 节点侧的模型标识（可能是本地 tag，与网关目录 id 命名不一致） |
| `output_chars` | int | 输出字符数 |

传输位置：WebSocket 推理帧的 `done` 帧 `receipt` 字段；
HTTP 心跳/遥测报文也带最近一张收据（模块级**单槽**缓存，内存有界）。

> ⚠️ 节点**没有** `node_secret` 时**不带** `receipt` 字段 —— **绝不发假签名**。

### 1.4 验签

网关用同一个 `node_secret` 重算并以 `hmac.compare_digest` **常量时间**比较。
比较失败 ⇒ 收据被伪造 ⇒ `SLASHED`。

---

## 2. 候选规范化串（防误判诚实节点）

节点签收据时用的是**它自己上报的** token 数与模型名；网关侧看到的是
（可能经过**黄金记忆扣减**的）计费 token 数 —— 两者偶尔会差一点点。

若只比对一条规范串，会把**诚实节点**误判成欺诈。因此网关在
**网关自己的 `request_id`** 前提下，枚举少量候选：

- `prompt_tokens` ∈ {计费值, 节点原始上报值}
- `completion_tokens` ∈ {计费值, 节点原始上报值}
- `model_id` ∈ {网关目录 id, 节点上报 id}

任一候选验签通过即视为通过。**`request_id` 永不变** ⇒ 跨请求重放一定验不过。

---

## 3. 5% 确定性抽检

```
bucket    = int(SHA256(UTF8(request_id)).hexdigest(), 16) % 100     # 0..99
spot_due  = bucket < 5                                              # SPOT_CHECK_RATE = 5
```

- **确定性**：同一 `request_id` 永远命中或永远不命中 ⇒ 可复现、可审计、可向用户举证；
- 抽检命中且守卫全过 ⇒ `usage_logs.poi_status = 'SPOT_CHECKED'`，
  并写一条 `poi_audits` 审计行（`audit_type='AUTO_5PCT'`）；
- `bucket` 本身可展示（"这一笔落在第几桶"），便于人工抽查复核。

---

## 4. 防欺诈守卫

### 4.1 守卫 ① —— Token 膨胀（虚报 token）

先从**输出文本**推出一个合理上限：

```
estimate_tokens(text) ≈ CJK字数 + 其它字符数/4        # 向上取整
upper_bound(text)    = max(8, estimate_tokens(text) × 2 + 8)
```

判定（两条**同时**成立才算命中）：

```
reported_tokens > 32   且   reported_tokens > upper_bound × 3.0
```

常量：`TOKEN_INFLATION_RATIO = 3.0`，`TOKEN_INFLATION_MIN_TOKENS = 32`。

> 双重条件是为了**不误伤短输出**：小文本的 token 估计天然抖动，
> 只在"上报值足够大"且"远超上限"时才判定。

### 4.2 守卫 ② —— 低熵垃圾输出（复读 / 乱码）

香农信息熵（bit/字符）：

```
H = -Σ p(c) · log2(p(c))      （p(c) = count(c)/len(text)）
```

判定：

```
len(text) >= 64   且   H < 1.2
```

常量：`LOW_ENTROPY_BITS = 1.2`，`LOW_ENTROPY_MIN_CHARS = 64`。

> 短文本（如"好的。"）熵天然低 ⇒ 必须同时要求"足够长"，否则会把
> 正常简短回答当成垃圾。

### 4.3 输出摘要一致性

网关自算 `SHA256(实际输出)`，与节点上报的 `output_sha256` 比对；
不一致 ⇒ `output_hash_mismatch` ⇒ **调包** ⇒ `SLASHED`。

---

## 5. 状态机与扣罚

### 5.1 `usage_logs.poi_status`

| 值 | 含义 |
|---|---|
| `UNCHECKED` | 老节点 / 无收据 —— **不扣分**（向后兼容） |
| `VERIFIED` | 收据验签通过 |
| `SPOT_CHECKED` | 5% 抽检命中且通过 |
| `SLASHED` | 命中欺诈 ⇒ 已扣罚 |
| `SIMULATED` | 模拟回答（无真实节点推理） |

### 5.2 `poi_audits`

| 列 | 说明 |
|---|---|
| `request_id` / `node_id` / `model_id` | 被审计的推理 |
| `audit_type` | `AUTO_5PCT`（抽检）/ `MANUAL`（业主主动验真或演练）/ `GUARD_TRIGGER`（守卫触发） |
| `verdict` | `PASS` / `SLASHED` |
| `reason` | 机器可读原因码（见下） |
| `reported_tokens` / `verified_tokens` | 上报值 / 文本推算值 |
| `entropy_score` | 香农熵（bit/字符） |
| `similarity_score` | `min(1, 推算token / 上报token)`，1.0 = 完全吻合 |
| `slash_penalty` | 本次扣分（0.05） |

**原因码**（`reason` 前缀，机器可解析）：

```
bad_signature               收据签名与规范化串不匹配
output_hash_mismatch        上报的输出摘要与实际输出不一致
token_inflation_fraud       上报 token 远超文本可推出上限
low_entropy_garbage         输出香农熵过低
ok                          验签通过且未命中守卫
```

### 5.3 Slashing

命中欺诈 ⇒ 扣节点信用分 `0.05`（`SLASH_PENALTY`），并写审计行。
扣分失败**不打断结算**（只记日志）。

> ⚠️ **PoI 绝不碰钱**：它只写 `usage_logs` 的 4 个**附加列**
> （`output_sha256` / `receipt_sig` / `receipt_canonical` / `poi_status`）
> 与 `poi_audits` 新表，**不触碰** `balance_ledger` / `revenue_ledger` 的任何金额
> ⇒ 计费不变量 `NET == BAL` 恒成立。

---

## 6. 业主主动验真

`POST /api/v1/owner/poi/audit`（`request_id`）：

1. 取该请求的用量行（含 `receipt_canonical` / `receipt_sig`）；
2. 用节点的 `node_secret` 重算并验签；
3. 写一条 `audit_type='MANUAL'` 的审计行。

⚠️ **不产生任何扣费 / 分账副作用**。有 `receipt_canonical` 时逐字节重放；
没有时按 `{request_id}:{model_id}:{prompt_tokens}:{completion_tokens}:{output_sha256}`
重建。

---

## 7. 兼容与演进

| 版本 | 变更 |
|---|---|
| `1.0.0` | 首版：HMAC-SHA256 收据 + canonical 口径 + 5% 确定性抽检 + Token 膨胀 / 低熵两道守卫 + Slashing 扣罚 |

### 7.1 破坏性变更清单（下列任一改动必须递增主版本号）

- canonical 串的**字段顺序**或**分隔符**变化；
- 哈希/签名的编码口径变化（UTF-8、小写 hex）；
- `request_id` 的生成方约定变化（当前：**必须由网关生成**）；
- 抽检算法变化（当前：`sha256(request_id) % 100 < 5`）。

### 7.2 向后兼容

老版本客户端不带收据 ⇒ 标 `UNCHECKED`，**不扣分** ——
协议升级不得让存量节点被误判为欺诈。

---

## 8. 相关文档

- [`PAWMODEL.md`](PAWMODEL.md) —— 模型包与清单哈希规范；
- `apipaw/apipaw-cloud` 的 `poi_engine.py` —— 网关侧实现；
- `apipaw/apipaw-agent` 的 `receipt_signing.py` —— 节点侧实现。
