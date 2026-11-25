#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""校验公开检查点链的自洽性 + 外部见证锚点是否落在本仓公开历史里。

为什么必须有 CI（而不是"靠人记得核对"）：
``checkpoints/prod-state-roots.jsonl`` 是**默克尔状态根的外部见证**，
它的全部价值在于"不可篡改"。如果这个文件被改坏（哈希链断裂、epoch_no 不连续、
``anchor_commit`` 指向仓库里根本不存在的提交），**必须立刻红** ——
否则"网关说它被见证过"就退化成一句无法证伪的话。

只依赖标准库（不引第三方依赖），任何人都能本地复算：

    python3 scripts/verify_checkpoints.py

退出码：0 = 全绿；1 = 有校验失败项。
"""

from __future__ import print_function

import hashlib
import io
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
CKPT = os.path.join(ROOT, "checkpoints", "prod-state-roots.jsonl")
ANCHORS = os.path.join(ROOT, "checkpoints", "anchors.jsonl")

REQUIRED = (
    "epoch_no", "state_root", "ledger_root", "revenue_root",
    "ledger_leaf_count", "revenue_leaf_count",
    "prev_epoch_hash", "epoch_hash", "created_at",
)

failures = []


def fail(msg):
    failures.append(msg)
    print("[FAIL] %s" % msg)


def ok(msg):
    print("[ok]   %s" % msg)


def canonical(d):
    """epoch_hash 的 canonical 口径（见 checkpoints/README.md）。

    金额/时间一律定点字符串 ⇒ 跨平台逐字节可复现。
    """
    return "|".join([
        "epoch",
        str(d["epoch_no"]),
        str(d["state_root"]),
        str(d["ledger_root"]),
        str(d["revenue_root"]),
        str(d["ledger_leaf_count"]),
        str(d["revenue_leaf_count"]),
        str(d["prev_epoch_hash"]),
        "%.6f" % float(d["created_at"]),
    ])


def load_jsonl(path):
    rows = []
    if not os.path.exists(path):
        fail("缺少文件: %s" % path)
        return rows
    with io.open(path, "r", encoding="utf-8") as fh:
        for lineno, line in enumerate(fh, 1):
            line = line.strip()
            if not line:
                continue
            try:
                rows.append((lineno, json.loads(line)))
            except ValueError as exc:
                fail("%s 第 %d 行不是合法 JSON: %s" % (path, lineno, exc))
    return rows


def git_has_commit(sha):
    """该 commit 是否存在于本仓公开历史里（git 本地对象库即可判定）。"""
    try:
        p = subprocess.Popen(
            ["git", "cat-file", "-e", "%s^{commit}" % sha],
            cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        p.communicate()
        return p.returncode == 0
    except OSError as exc:
        print("[warn] 无法调用 git: %s" % exc)
        return False


def main():
    print("== 校验公开检查点链 ==")

    rows = load_jsonl(CKPT)
    if not rows:
        print("[FATAL] 检查点文件为空或缺失")
        return 1
    ok("检查点行数: %d" % len(rows))

    by_epoch = {}
    prev_hash = ""
    for lineno, d in rows:
        missing = [k for k in REQUIRED if k not in d]
        if missing:
            fail("第 %d 行缺字段: %s" % (lineno, ",".join(missing)))
            continue

        epoch_no = d["epoch_no"]
        if epoch_no != len(by_epoch) + 1:
            fail("epoch_no 不连续: 期望 %d 实得 %r" % (len(by_epoch) + 1, epoch_no))
        by_epoch[epoch_no] = d

        # 1) 链式衔接
        if str(d["prev_epoch_hash"]) != prev_hash:
            fail("epoch #%s 的 prev_epoch_hash 与前序 epoch_hash 对不上" % epoch_no)
        else:
            ok("epoch #%s 链式衔接正确" % epoch_no)

        # 2) 自哈希
        expect = hashlib.sha256(canonical(d).encode("utf-8")).hexdigest()
        if expect != str(d["epoch_hash"]):
            fail("epoch #%s 的 epoch_hash 不自洽（实得 %s，应为 %s）"
                 % (epoch_no, d["epoch_hash"], expect))
        else:
            ok("epoch #%s epoch_hash 自洽" % epoch_no)

        # 3) 叶子数不能为负
        for k in ("ledger_leaf_count", "revenue_leaf_count"):
            if int(d[k]) < 0:
                fail("epoch #%s 的 %s 为负" % (epoch_no, k))

        prev_hash = str(d["epoch_hash"])

    # 4) anchors.jsonl：每个见证都必须指向真实存在、且与检查点一致的提交
    print("== 校验外部见证锚点 ==")
    anchors = load_jsonl(ANCHORS)
    if not anchors:
        print("[FATAL] 见证文件为空或缺失")
        return 1
    ok("见证条数: %d" % len(anchors))

    for lineno, a in anchors:
        for k in ("epoch_no", "anchor_commit", "state_root", "epoch_hash"):
            if k not in a:
                fail("见证第 %d 行缺字段: %s" % (lineno, k))
                continue
        epoch_no = a["epoch_no"]
        ck = by_epoch.get(epoch_no)
        if ck is None:
            fail("见证第 %d 行指向不存在的 epoch #%s" % (lineno, epoch_no))
            continue
        if str(a["state_root"]) != str(ck["state_root"]):
            fail("见证第 %d 行的 state_root 与 epoch #%s 不符" % (lineno, epoch_no))
        if str(a["epoch_hash"]) != str(ck["epoch_hash"]):
            fail("见证第 %d 行的 epoch_hash 与 epoch #%s 不符" % (lineno, epoch_no))
        sha = str(a["anchor_commit"])
        if len(sha) != 40 or any(c not in "0123456789abcdef" for c in sha.lower()):
            fail("见证第 %d 行的 anchor_commit 不是 40 位十六进制 SHA: %r" % (lineno, sha))
            continue
        if not git_has_commit(sha):
            fail("见证第 %d 行的 anchor_commit %s 不在本仓公开历史里" % (lineno, sha))
        else:
            ok("epoch #%s 的见证提交 %s 在本仓公开历史里" % (epoch_no, sha[:8]))

    print("")
    if failures:
        print("[FATAL] 公开检查点校验失败 %d 项" % len(failures))
        for f in failures:
            print("  - %s" % f)
        return 1
    print("[ok] 公开检查点链与外部见证锚点全部自洽（%d 个 epoch）" % len(by_epoch))
    return 0


if __name__ == "__main__":
    sys.exit(main())
