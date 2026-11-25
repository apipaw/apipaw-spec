# 生产状态根检查点（Prod State-Root Checkpoints）

本目录是 **APIPaw 云端网关默克尔状态根的公开外部见证**。

---

## 为什么需要这个目录

云端网关通过 `GET /api/v1/network/state-root` 公布状态根，但那是**网关自己
公布自己的状态根** —— 属于「可变视图」：只要网关改了库，它照样能算出一个
新的、同样"自洽"的根，历史因此**不可验证、不可追责**。

本目录给出**网关之外的第三方见证**：每个检查点都写进本仓库的公开历史，
任何人（在任何时间、即使网关被攻破）都能拿到这些行来核对：

1. 某个状态根**曾经**被公开见证过；
2. 检查点之间是**哈希链**（`prev_epoch_hash` → `epoch_hash`），
   任何一格被改，它自己的哈希与后继的 `prev_epoch_hash` 会同时对不上；
3. 网关若想悄悄改状态根，就必须同时改掉本仓库的公开历史 —— **那是有痕的**。

---

## 文件格式

### `prod-state-roots.jsonl`（**只追加**，每行一个检查点）

| 字段 | 含义 |
|---|---|
| `epoch_no` | 检查点序号（从 1 开始，**连续**） |
| `state_root` | `sha256("ledger:" + ledger_root + "\|revenue:" + revenue_root)` |
| `ledger_root` | `balance_ledger` 的默克尔根（SHA256 二叉树，十六进制文本域拼接） |
| `revenue_root` | `revenue_ledger` 的默克尔根 |
| `ledger_leaf_count` / `revenue_leaf_count` | 两棵树的叶子数（= 账本行数） |
| `prev_epoch_hash` | 上一个检查点的 `epoch_hash`（**首格为空**） |
| `epoch_hash` | `sha256(canonical)`，canonical 口径见下 |
| `created_at` | 落库时间（Unix 秒） |
| `anchor_ref` | 外部见证引用（回填字段，见下） |

### `anchors.jsonl`（**只追加**，每行一条"哪个提交见证了哪个检查点"）

| 字段 | 含义 |
|---|---|
| `epoch_no` | 被见证的检查点序号 |
| `anchor_commit` | 见证该检查点的 **Git Commit SHA**（本仓公开历史） |
| `state_root` | 该检查点的状态根（便于不查库也能核对） |

> ⚠️ **为什么 `anchor_ref` 与 `anchor_commit` 是两个字段、两次提交**：
> 提交 A 里写入检查点数据；提交 A 的 SHA 只有在提交完成后才知道，
> 因此"哪个提交见证了它"只能**事后**补记（提交 B 写进 `anchors.jsonl`）。
> 两次提交都是**只追加**，不改历史 —— 这是公开见证该有的形态。

---

## `epoch_hash` 的 canonical 口径

```
epoch|{epoch_no}|{state_root}|{ledger_root}|{revenue_root}|{ledger_leaf_count}|{revenue_leaf_count}|{prev_epoch_hash}|{created_at:.6f}
```

`epoch_hash = sha256(canonical)`（UTF-8 编码，小写十六进制）。
金额/时间一律定点字符串 ⇒ **跨平台逐字节可复现**，任何人都能独立复算。

---

## 怎么独立验证（不信任网关）

```bash
# 1. 取网关当前公示的状态根
curl -s https://cloud.apipaw.com/api/v1/network/state-root | jq .state_root

# 2. 取公开检查点链
curl -s https://cloud.apipaw.com/api/v1/network/state-epochs | jq '.epochs[] | {epoch_no, state_root, epoch_hash}'

# 3. 用本目录的行独立复算哈希链（示例脚本见仓库 README）
python - <<'EOF'
import hashlib, json, io
prev = ""
ok = True
for line in io.open("checkpoints/prod-state-roots.jsonl", encoding="utf-8"):
    d = json.loads(line)
    c = "|".join([
        "epoch", str(d["epoch_no"]), d["state_root"], d["ledger_root"],
        d["revenue_root"], str(d["ledger_leaf_count"]), str(d["revenue_leaf_count"]),
        d["prev_epoch_hash"], "%.6f" % float(d["created_at"]),
    ])
    h = hashlib.sha256(c.encode("utf-8")).hexdigest()
    ok = ok and h == d["epoch_hash"] and d["prev_epoch_hash"] == prev
    prev = d["epoch_hash"]
print("chain_valid =", ok)
EOF
```

若网关公示的 `state_root` **不在**本目录的历史里 ⇒ 该状态根**未经外部见证**。

---

## 许可证

MIT，见仓库根目录 [`LICENSE`](../LICENSE)。
