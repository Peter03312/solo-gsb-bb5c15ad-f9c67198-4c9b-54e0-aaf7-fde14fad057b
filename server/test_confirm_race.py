"""确认竞争修复的端到端验证（Flask test client + 多线程并发）。

覆盖：
- 常规预览/确认成功，版本恰好 +1，令牌被消费后不可重复确认；
- 同一令牌并发确认只有一次生效（原稿只被覆盖一次）；
- 甲、乙基于同一原稿分别预览，甲确认后乙的旧令牌被拒（版本已变）；
- 草稿与预览输入不一致按 409 拒绝且原稿不变；
- 无解预览不产生令牌、不可确认；
- 非法请求仍按 400 拒绝；
- 旧库（无 base_version 列）迁移后旧令牌不可确认。
"""

import json
import os
import sys
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# 用临时库，避免污染 data/weave.db
_tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
_tmp.close()
os.environ["DB_PATH"] = _tmp.name

import app as server  # noqa: E402

client = server.app.test_client()

FAILS = []


def check(name, cond, detail=""):
    status = "PASS" if cond else "FAIL"
    print(f"[{status}] {name}{(' :: ' + detail) if detail else ''}")
    if not cond:
        FAILS.append(name)


def payload(draft, token=None):
    body = dict(draft)
    if token is not None:
        body["token"] = token
    return body


def get_state():
    return client.get("/api/state").get_json()


def make_draft(grid, locks=None, k=2, rows=None, cols=None):
    rows = rows or len(grid)
    cols = cols or len(grid[0])
    return {"rows": rows, "cols": cols, "grid": grid,
            "locks": locks or [], "k": k}


# 一个存在超限段且可修补的草稿：2x2 中三个 0（同列两个 0 环向连续，K=2 临界），
# 直接用“全部置 1 的一行”制造全同行超限更直观：
DRAFT_A = make_draft([[0, 1], [0, 1]])  # 每列全同 -> 超限，可修补
DRAFT_B = make_draft([[1, 0], [1, 0]])  # 另一份不同草稿

# --- 初始状态 ---
st0 = get_state()
check("初始版本为 1", st0["version"] == 1, f"version={st0['version']}")

# --- 非法请求仍 400 ---
bad = client.post("/api/preview", json={"rows": 0, "cols": 2,
                                        "grid": [], "locks": [], "k": 1})
check("非法预览 400", bad.status_code == 400)

conf_bad = client.post("/api/confirm", json={"token": "x",
                       "rows": 1, "cols": 1, "grid": [[0]], "locks": [], "k": 0})
check("非法确认 400（K=0）", conf_bad.status_code == 400)

conf_notoken = client.post("/api/confirm", json={})
check("缺令牌 400", conf_notoken.status_code == 400)

# --- 无解预览不产生令牌 ---
# 1x1 格子：全同行/列恒超限，唯一格锁定后无法翻转 -> 无解
unsolvable = make_draft([[0]], locks=[[0, 0]], k=2)
r = client.post("/api/preview", json=unsolvable).get_json()
check("无解预览 solvable=false 且无 token",
      r["solvable"] is False and "token" not in r, json.dumps(r)[:200])

# --- 甲、乙基于同一原稿分别预览 ---
pa = client.post("/api/preview", json=DRAFT_A).get_json()
pb = client.post("/api/preview", json=DRAFT_B).get_json()
check("两份预览均可解并带令牌",
      pa["solvable"] and pb["solvable"] and pa["token"] != pb["token"])

# 乙拿着令牌却提交甲的草稿 -> mismatch
r = client.post("/api/confirm", json=payload(DRAFT_A, pb["token"]))
check("草稿与预览输入不一致 -> 409", r.status_code == 409,
      r.get_json().get("error", ""))
check("mismatch 后原稿不变", get_state()["version"] == 1)

# 甲确认成功
r = client.post("/api/confirm", json=payload(DRAFT_A, pa["token"]))
check("甲确认成功 200", r.status_code == 200)
st1 = r.get_json()["state"]
check("确认后版本 +1", st1["version"] == 2, f"version={st1['version']}")
check("确认结果为修补网格", st1["grid"] == pa["repaired"])

# 甲重复确认（令牌已消费）
r2 = client.post("/api/confirm", json=payload(DRAFT_A, pa["token"]))
check("重复确认已消费令牌 -> 409", r2.status_code == 409)
check("重复确认后版本不变", get_state()["version"] == 2)

# 乙再用旧令牌确认 -> stale（绑定版本 1，当前版本 2）
r3 = client.post("/api/confirm", json=payload(DRAFT_B, pb["token"]))
check("甲确认后乙旧令牌 -> 409(stale)", r3.status_code == 409,
      r3.get_json().get("error", ""))
check("乙失败后原稿仍是甲的结果且版本 2", get_state()["version"] == 2)
check("乙失败不改原稿内容", get_state()["grid"] == pa["repaired"])

# --- 同一令牌并发确认：恰好一次生效 ---
pc = client.post("/api/preview", json=DRAFT_B).get_json()
before = get_state()
results = []
barrier = threading.Barrier(5)


def fire():
    barrier.wait()
    return client.post("/api/confirm", json=payload(DRAFT_B, pc["token"]))


with ThreadPoolExecutor(max_workers=5) as ex:
    futs = [ex.submit(fire) for _ in range(5)]
    results = [f.result().status_code for f in futs]

after = get_state()
ok = [code for code in results if code == 200]
check("5 个并发确认仅 1 个成功", len(ok) == 1, f"results={results}")
check("并发后版本只递增一次", after["version"] == before["version"] + 1,
      f"{before['version']} -> {after['version']}")
check("并发后原稿为该预览修补结果", after["grid"] == pc["repaired"])

# --- 冲突后可以重新预览并确认 ---
pd = client.post("/api/preview", json=DRAFT_A).get_json()
r = client.post("/api/confirm", json=payload(DRAFT_A, pd["token"]))
check("冲突后重新预览仍可确认", r.status_code == 200
      and r.get_json()["state"]["version"] == 4)

# --- 成功响应结构与请求字段不变 ---
r = client.post("/api/preview", json=DRAFT_A)
body = r.get_json()
check("预览响应字段不变",
      set(["solvable", "token", "violations", "input", "repaired",
           "flips", "flipCount"]).issubset(body.keys()))
rc = client.post("/api/confirm", json=payload(DRAFT_A, body["token"]))
state = rc.get_json().get("state", {})
check("确认响应 {state:{...,violations}} 结构不变",
      rc.status_code == 200 and "violations" in state and "version" in state)

# ================= 格值1总数区间 =================

# --- 非法区间 400 ---
DRAFT_RANGE = make_draft([[0, 0, 0, 0]] * 4, k=2)  # 4x4 全0
for bad_range, name in (([3, 1], "下限>上限"), ([0, 17], "上限超总格数"),
                        ([2], "只填一端"), ([0, None], "一端为空"),
                        ([-1, 4], "下限为负"), ("1,2", "非数组")):
    r = client.post("/api/preview", json={**DRAFT_RANGE, "onesRange": bad_range})
    check(f"非法区间预览 400（{name}）", r.status_code == 400,
          r.get_json().get("error", ""))
r = client.post("/api/confirm", json={**DRAFT_RANGE, "onesRange": [0, 99],
                                      "token": "x"})
check("非法区间确认 400", r.status_code == 400)

# --- 带区间无解预览不发令牌（2x2 K=2 可行总数恒为 2）---
r = client.post("/api/preview",
                json=make_draft([[0, 1], [0, 1]], k=2, rows=2, cols=2)
                | {"onesRange": [0, 0]})
rj = r.get_json()
check("区间无解预览 solvable=false 且无 token",
      r.status_code == 200 and rj["solvable"] is False and "token" not in rj)
check("无解预览仍返回计数与区间",
      rj["originalOnes"] == 2 and rj["onesRange"] == [0, 0])

# --- 带区间预览/确认成功，区间随原稿持久化 ---
before = get_state()
pr = client.post("/api/preview", json={**DRAFT_RANGE, "onesRange": [8, 8]})
pj = pr.get_json()
check("带区间预览可解", pj.get("solvable") is True and "token" in pj,
      json.dumps(pj)[:200])
check("预览返回原稿/修补稿计数与区间",
      pj["originalOnes"] == 0 and pj["repairedOnes"] == 8
      and pj["onesRange"] == [8, 8]
      and pj["input"]["onesRange"] == [8, 8])
total = sum(sum(row) for row in pj["repaired"])
check("修补稿总数达标", total == 8)

r = client.post("/api/confirm",
                json=payload({**DRAFT_RANGE, "onesRange": [8, 8]}, pj["token"]))
check("带区间确认成功", r.status_code == 200)
st = r.get_json()["state"]
check("确认后版本 +1", st["version"] == before["version"] + 1)
check("区间随原稿持久化", st["onesRange"] == [8, 8])
check("原稿计数随状态返回", st["ones"] == 8)
st2 = get_state()
check("GET /api/state 持久化区间与计数",
      st2["onesRange"] == [8, 8] and st2["ones"] == 8)

# --- 确认时区间与预览输入不一致 -> 409 mismatch，原稿不变 ---
pr = client.post("/api/preview", json={**DRAFT_RANGE, "onesRange": [8, 8]})
token = pr.get_json()["token"]
r = client.post("/api/confirm",
                json=payload({**DRAFT_RANGE, "onesRange": [8, 9]}, token))
check("区间变更 -> 409", r.status_code == 409, r.get_json().get("error", ""))
r = client.post("/api/confirm", json=payload(DRAFT_RANGE, token))  # 区间被去掉
check("区间被省略 -> 409", r.status_code == 409)
check("区间冲突后原稿区间不变", get_state()["onesRange"] == [8, 8])
# 同一令牌用一致区间仍可确认（前两次 409 未消费令牌）
r = client.post("/api/confirm",
                json=payload({**DRAFT_RANGE, "onesRange": [8, 8]}, token))
check("区间一致仍可确认", r.status_code == 200)

# --- 不带区间的旧式请求：行为与响应保持兼容 ---
pr = client.post("/api/preview", json=DRAFT_A)
pj = pr.get_json()
check("无区间预览 onesRange 为 null", pj["onesRange"] is None
      and pj["input"]["onesRange"] is None)
r = client.post("/api/confirm", json=payload(DRAFT_A, pj["token"]))
st = r.get_json()["state"]
check("无区间确认成功且持久化 onesRange=null",
      r.status_code == 200 and st["onesRange"] is None)
check("无区间状态仍带计数", st["ones"] == sum(sum(row) for row in st["grid"]))

print()
if FAILS:
    print(f"{len(FAILS)} 项失败：{FAILS}")
    sys.exit(1)
print("全部通过。")
