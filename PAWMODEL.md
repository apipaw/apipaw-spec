# PAWMODEL —— 模型包与清单哈希规范

> 规范版本：`1.1.0` ｜ 状态：已落地（生产网关在用）｜ 许可证：MIT
>
> 本文件是 **APIPaw 算力网络上"一个模型包长什么样"的唯一权威规范**。
> 网关侧的解析实现见 `apipaw/apipaw-cloud` 的 `pawmodel_manifest.py`
> （纯标准库 + PyYAML 可选，源站 Python 3.6.8 兼容）。

`PAWMODEL.md` 是模型创作者随模型一起发布的**模型包清单文件**。它把三件事钉死：

1. **身份**：模型是谁的（`model_id` / `author_wallet`）、在哪个档位（`tier`）；
2. **计价**：入/出 token 单价与创作者版税率；
3. **不可篡改**：`manifest_sha256` 把上述全部字段 + System Prompt 的哈希绑在一起 ——
   任何一格被改动，清单哈希就会变，而**旧哈希仍然留在账本里**，谁也赖不掉。

---

## 1. 文件形态

`PAWMODEL.md` 放在**模型仓库根目录**。解析器（`parse_pawmodel`）自动识别两种写法：

### 1.1 YAML frontmatter（推荐）

```markdown
---
model_id: qwen2-5-0-5b-paw
display_name: Qwen2.5 0.5B (PAW)
tier: CREATOR
min_vram_gb: 4.0
prompt_price_per_1k: 0.20
completion_price_per_1k: 0.24
royalty_rate: 0.15
author_wallet: "0x71C7656EC7ab88b098defB751B7401B5f6d8976F"
---

# System Prompt

You are a helpful assistant running on the APIPaw compute network.
```

### 1.2 纯 Markdown key-value

没有 frontmatter 时，解析器退化为逐行解析 `key: value`；
`# System Prompt` 标题之后的正文即 `system_prompt`：

```markdown
model_id: qwen2.5-0.5b-paw
display_name: Qwen2.5 0.5B
tier: CREATOR

# System Prompt
You are a helpful assistant.
```

### 1.3 兼容：生态 v1.0 嵌套写法

早期生态里的 `PAWMODEL.md`（见 `apipaw/apipaw-agent` 仓库同名文件）用的是嵌套块：

```yaml
hardware_requirements:
  minimum_vram_gb: 1.8
royalty_pricing:
  enabled: true
  royalty_payout_address: "0x..."
model_name: "DeepSeek-R1-Distill-Qwen-1.5B"
```

解析器会把嵌套块**压平**成标准字段（`minimum_vram_gb` → `min_vram_gb`、
`royalty_payout_address` → `author_wallet`、`model_name` → `display_name` 并推导
`model_id`），因此**新旧两种模型包都能被同一套哈希锁覆盖**。扁平写法优先，
嵌套块只填补缺省字段。

> ⚠️ **YAML 1.1 的坑**：PyYAML 会把不带引号的 `0x71C7...` 解析成**十六进制整数**，
> 钱包地址就此丢失。解析器在 YAML 解析**之前**会自动给裸地址补引号，
> 但创作者仍应**自己加引号**。

---

## 2. 标准字段

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `model_id` | str | ✅ | 模型唯一标识，**只允许小写字母、数字、连字符**（`^[a-z0-9\-]+$`） |
| `display_name` | str | — | 展示名（缺省等于 `model_id`），最长 128 字符 |
| `tier` | str | — | `BASE`（开源基础模型）或 `CREATOR`（社区创作者模型），缺省 `BASE` |
| `min_vram_gb` | float | ✅ | 单节点承载该模型所需的最低显存（GB），取值 `0 ~ 1024` |
| `prompt_price_per_1k` | float | ✅ | 输入 token 单价（USD / 1K tokens），`0 ~ 100` |
| `completion_price_per_1k` | float | ✅ | 输出 token 单价（USD / 1K tokens），`0 ~ 100` |
| `royalty_rate` | float | — | 创作者版税率，`0 ~ 0.30`，`CREATOR` 缺省 `0.15`，`BASE` 必须为 `0` |
| `author_wallet` | str | — | 创作者收款钱包（EVM，`0x` + 40 位十六进制）；`CREATOR` 必填 |
| `system_prompt` | str | — | 模型系统提示词（参与哈希锁） |

### 2.1 字段别名（等价写法）

解析器接受下列别名并归一到标准名（不认识的键**直接丢弃**，不报错）：

```
id / name / display / model_name  → display_name（model_name 另用于推导 model_id）
vram_gb / min_vram                → min_vram_gb
prompt_price / prompt_price_per_1k_tokens → prompt_price_per_1k
completion_price / completion_price_per_1k_tokens → completion_price_per_1k
royalty                           → royalty_rate
creator_wallet / wallet           → author_wallet
prompt / system_prompt_text       → system_prompt
```

### 2.2 校验规则（任一不通过 ⇒ 整包拒收）

| 规则 | 错误码 | 说明 |
|---|---|---|
| 必填字段缺失 | `4001` | `model_id` 缺失直接拒收 |
| `model_id` 非法字符 | `4001` | 只允许小写字母 / 数字 / 连字符 |
| `tier` 非法 | `4001` | 只能是 `BASE` / `CREATOR` |
| 数值越界 | `4001` | 显存 `0~1024`，单价 `0~100` |
| `BASE` 却带 `royalty_rate > 0` | `4001` | **不静默清零** —— 静默清零会让创作者误以为 15% 版税生效了 |
| 钱包格式非法 | `4002` | 必须 `0x` + 40 位十六进制 |
| `CREATOR` 缺 `author_wallet` | `4002` | 场景 B 必须绑定收款地址 |
| 显存不足 | `5003` | 低于节点可用显存的模型不予上架 |

---

## 3. 清单哈希锁（本规范的核心）

### 3.1 两个哈希

```
system_prompt_sha256 = SHA256( UTF8(system_prompt) )                    # 小写 hex
manifest_sha256      = SHA256( UTF8(canonical) )                        # 小写 hex
```

### 3.2 canonical 串（**协议，勿改**）

```
{model_id}:{tier}:{prompt_price_per_1k}:{completion_price_per_1k}:{royalty_rate}:{system_prompt_sha256}
```

字段顺序固定、冒号分隔、**无空格**。三个数值字段必须用
`format_number()` 归一（`"%.10f"` 后去尾零）：

| 输入 | canonical 中的表示 |
|---|---|
| `0.35` | `0.35` |
| `0.0` | `0` |
| `0.15000000000000002` | `0.15` |

> ⚠️ **不能用 `str(float)`**：那会留下 `0.15000000000000002` 这种平台相关的尾巴，
> 导致**同一份清单在不同机器上算出不同的 `manifest_sha256`**。
> `format_number()` 是跨语言稳定的口径。

### 3.3 归一化后再哈希

哈希是在**归一化字段**上算的（而不是原始文本），因此：

- `royalty_rate` 先 `round(x, 4)`；
- `min_vram_gb` 先 `round(x, 3)`；
- `prompt_price_per_1k` / `completion_price_per_1k` 先 `round(x, 6)`；
- `display_name` 截断到 128 字符。

这样 `0.15000` 与 `0.15` 这样的书写差异**不会**造成哈希漂移。

### 3.4 哈希锁解决什么

`models` 表里的 `system_prompt` 本来只是一个普通 TEXT 列 —— 谁都能 `UPDATE`。
而 System Prompt 是**模型能力的一部分**，它被改了，模型行为就变了，
而外界（买家 / 审计 / 白皮书）**没有任何办法发现**。

清单哈希锁把"模型包"变成一个**可验证的整体**：

- 改了价格 ⇒ `manifest_sha256` 变；
- 改了版税率 ⇒ `manifest_sha256` 变；
- 改了 System Prompt ⇒ `system_prompt_sha256` 变 ⇒ `manifest_sha256` 变；
- 改任何一格都**盖不住旧账** —— 历史行的旧哈希仍在库里。

> 结论：`manifest_sha256` **不是**防篡改的密码学签名（它没有密钥），
> 它是**可复算的指纹 + 留痕**。真正的"谁改的"由网关的写入口径与审计流水回答。

---

## 4. 上架与结算口径

| 归属 | `BASE`（场景 A） | `CREATOR`（场景 B） |
|---|---|---|
| 节点（算力提供方） | 85% | 85% |
| 创作者（版税） | — | **15%** |
| 平台 | 15% | 15% |

- 场景 B 的买家实付 = 基价 **× 1.15**（版税是**叠加**而非替换）；
- 创作者身份口径 = `author_wallet`（钱包地址），**不是**平台账号 ID；
- 结算当前为**落库结算**（`creator_withdrawals` 记 `PENDING` 流水），
  **暂不做链上转账**。

---

## 5. 与其他规范的关系

- [`POI-PROTOCOL.md`](POI-PROTOCOL.md) —— 推理收据（HMAC-SHA256）+ 5% 抽检 + 防欺诈守卫；
- `apipaw/apipaw-agent` 仓库的 `PAWMODEL.md` —— 客户端侧的**模型打包说明**
  （层数切片、硬件要求、版税绑定的开发者视角），与本文件是"同一件事的两面"：
  本文件描述**网关如何验收**，那份描述**节点如何承载**。

## 6. 版本演进

| 版本 | 变更 |
|---|---|
| `1.0.0` | 生态 v1.0：嵌套元数据（`hardware_requirements` / `royalty_pricing`）、层数切片、版税钱包 |
| `1.1.0` | 网关落地：扁平 9 字段 + 别名归一 + **清单哈希锁**（`system_prompt_sha256` / `manifest_sha256`）+ `format_number` 跨语言稳定数值口径 |

破坏性变更（删除必填字段、改变 canonical 串、改变校验语义）必须递增主版本号；
新增可选字段递增次版本号。
