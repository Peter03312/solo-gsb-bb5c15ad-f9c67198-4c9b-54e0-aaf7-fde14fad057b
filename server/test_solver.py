"""求解器与超限段检测的测试（含暴力枚举对照，含格值1总数区间）。"""

import itertools
import random
import sys
import time

from solver import solve_repair
from weave import find_violations


def brute_force(rows, cols, k, grid, locks, ones_range=None):
    """暴力枚举所有未锁定格取值，返回 (最少翻转数, 字典序最小展开序列) 或 None。

    ones_range = [下限, 上限] 时仅考虑格值1总数达标的修补稿。
    """
    locked = set(map(tuple, locks))
    free = [(r, c) for r in range(rows) for c in range(cols)
            if (r, c) not in locked]
    best = None
    for bits in itertools.product((0, 1), repeat=len(free)):
        g = [row[:] for row in grid]
        for (r, c), b in zip(free, bits):
            g[r][c] = b
        if find_violations(g, rows, cols, k):
            continue
        if ones_range is not None:
            total = sum(sum(row) for row in g)
            if not ones_range[0] <= total <= ones_range[1]:
                continue
        flips = sum(b != grid[r][c] for (r, c), b in zip(free, bits))
        flat = tuple(v for row in g for v in row)
        if best is None or (flips, flat) < (best[0], best[1]):
            best = (flips, flat)
    return best


def flat(grid):
    return tuple(v for row in grid for v in row)


def check_case(rows, cols, k, grid, locks, label, ones_range=None):
    expected = brute_force(rows, cols, k, grid, locks, ones_range)
    got = solve_repair(rows, cols, k, grid, locks, ones_range)
    tag = f"{label} 区间{ones_range}" if ones_range else label
    if expected is None:
        assert got is None, f"{tag}: 应无解但解出 {got}"
        print(f"  [OK] {tag}: 无可行修补（与暴力一致）")
        return
    assert got is not None, f"{tag}: 应有解但报无解"
    assert len(got["flips"]) == expected[0], (
        f"{tag}: 翻转数 {len(got['flips'])} != 最优 {expected[0]}")
    assert flat(got["repaired"]) == expected[1], (
        f"{tag}: 字典序不一致\n  got {flat(got['repaired'])}\n  exp {expected[1]}")
    # 解必须合法、尊重锁定且总数达标
    assert not find_violations(got["repaired"], rows, cols, k)
    for (r, c) in locks:
        assert got["repaired"][r][c] == grid[r][c]
    if ones_range is not None:
        total = sum(flat(got["repaired"]))
        assert ones_range[0] <= total <= ones_range[1], (
            f"{tag}: 格值1总数 {total} 不在区间 {ones_range}")
    print(f"  [OK] {tag}: 翻转 {expected[0]} 格（与暴力一致）")


def main():
    print("== 固定用例 ==")
    check_case(2, 2, 1, [[0, 0], [0, 0]], [], "2x2 全0 K=1")
    check_case(2, 2, 1, [[0, 0], [0, 0]], [[0, 0], [0, 1]], "2x2 行锁定 -> 无解")
    check_case(4, 4, 1, [[0, 1, 0, 1], [1, 0, 1, 0],
                         [0, 1, 0, 1], [1, 0, 1, 0]], [], "4x4 平纹 K=1 已合法")
    check_case(4, 4, 2, [[0] * 4 for _ in range(4)], [], "4x4 全0 K=2")
    check_case(4, 4, 2, [[0] * 4 for _ in range(4)],
               [[0, 0], [1, 1], [2, 2], [3, 3]], "4x4 全0 K=2 对角锁定")
    check_case(1, 1, 1, [[0]], [], "1x1 必无解")
    check_case(1, 3, 1, [[0, 1, 0]], [], "1x3 必无解（列全同）")
    check_case(3, 1, 1, [[0], [1], [0]], [], "3x1 必无解（行全同）")
    check_case(4, 4, 100, [[0, 1, 0, 1], [1, 0, 1, 0],
                           [0, 1, 0, 1], [1, 0, 1, 0]], [], "K 极大时已合法")
    check_case(3, 3, 1, [[0, 1, 0], [1, 0, 1], [0, 1, 0]], [], "3x3 K=1 奇数环")

    print("== 格值1总数区间 ==")
    # 4x4 K=2 的可行修补总数恒为 8：区间不含 8 即无解，含 8 则与无区间同解
    check_case(4, 4, 2, [[0] * 4 for _ in range(4)], [], "4x4 全0 K=2",
               ones_range=[8, 8])
    check_case(4, 4, 2, [[0] * 4 for _ in range(4)], [], "4x4 全0 K=2",
               ones_range=[4, 4])
    check_case(4, 4, 2, [[0] * 4 for _ in range(4)], [], "4x4 全0 K=2",
               ones_range=[0, 7])
    # 区间迫使放弃翻转最少的解，选总数达标者
    check_case(3, 3, 2, [[0] * 3 for _ in range(3)], [], "3x3 全0 K=2",
               ones_range=[6, 9])
    check_case(3, 3, 2, [[0] * 3 for _ in range(3)], [], "3x3 全0 K=2",
               ones_range=[0, 0])
    # 锁定格使区间无解：全锁的合法平纹总数固定为 8
    check_case(4, 4, 2, [[0, 1, 0, 1], [1, 0, 1, 0],
                         [0, 1, 0, 1], [1, 0, 1, 0]],
               [[r, c] for r in range(4) for c in range(4)],
               "4x4 平纹全锁", ones_range=[9, 16])
    check_case(4, 4, 2, [[0, 1, 0, 1], [1, 0, 1, 0],
                         [0, 1, 0, 1], [1, 0, 1, 0]],
               [[r, c] for r in range(4) for c in range(4)],
               "4x4 平纹全锁", ones_range=[8, 8])
    # 区间含端点边界
    check_case(2, 3, 2, [[0, 0, 1], [1, 0, 0]], [], "2x3 K=2",
               ones_range=[0, 6])
    check_case(2, 3, 2, [[0, 0, 1], [1, 0, 0]], [[0, 0]], "2x3 K=2 锁1",
               ones_range=[3, 3])

    print("== 超限段检测 ==")
    # 环向跨界：0 的段 {2,0} 长度为 2
    v = find_violations([[0, 1, 0]], 1, 3, 1)
    row_segs = [s for s in v if s["kind"] == "row"]
    assert len(row_segs) == 1 and sorted(map(tuple, row_segs[0]["cells"])) == [(0, 0), (0, 2)], v
    assert len([s for s in v if s["kind"] == "col"]) == 3  # 单列全同=无限
    # 全同行 -> 无限
    v = find_violations([[1, 1, 1]], 1, 3, 5)
    assert any(s["length"] is None for s in v if s["kind"] == "row")
    # 合法平纹无超限
    assert not find_violations([[0, 1], [1, 0]], 2, 2, 1)
    print("  [OK] 超限段检测（含跨界、全同、合法）")

    print("== 随机小网格对照暴力 ==")
    rng = random.Random(42)
    for i in range(60):
        rows = rng.randint(2, 5)
        cols = rng.randint(2, 4)
        k = rng.randint(1, 4)
        grid = [[rng.randint(0, 1) for _ in range(cols)] for _ in range(rows)]
        locks = [[r, c] for r in range(rows) for c in range(cols)
                 if rng.random() < 0.25]
        check_case(rows, cols, k, grid, locks,
                   f"随机#{i} {rows}x{cols} K={k} 锁{len(locks)}")

    print("== 随机小网格 + 区间对照暴力 ==")
    for i in range(60):
        rows = rng.randint(2, 5)
        cols = rng.randint(2, 4)
        k = rng.randint(1, 4)
        grid = [[rng.randint(0, 1) for _ in range(cols)] for _ in range(rows)]
        locks = [[r, c] for r in range(rows) for c in range(cols)
                 if rng.random() < 0.25]
        total = rows * cols
        lo = rng.randint(0, total)
        hi = rng.randint(lo, total)
        check_case(rows, cols, k, grid, locks,
                   f"区间随机#{i} {rows}x{cols} K={k} 锁{len(locks)}",
                   ones_range=[lo, hi])

    print("== 大网格性能 ==")
    for k in (1, 2, 3, 5, 8, 16, 1000):
        rows, cols = 16, 8
        grid = [[rng.randint(0, 1) for _ in range(cols)] for _ in range(rows)]
        t0 = time.time()
        got = solve_repair(rows, cols, k, grid, [])
        dt = time.time() - t0
        assert got is not None
        assert not find_violations(got["repaired"], rows, cols, k)
        print(f"  [OK] 16x8 K={k}: 翻转 {len(got['flips'])} 格, {dt:.2f}s")
        assert dt < 10, "求解超时"

    # 大量锁定 + 大网格
    grid = [[rng.randint(0, 1) for _ in range(8)] for _ in range(16)]
    locks = [[r, c] for r in range(16) for c in range(8) if rng.random() < 0.5]
    t0 = time.time()
    got = solve_repair(16, 8, 3, grid, locks)
    dt = time.time() - t0
    if got is not None:
        assert not find_violations(got["repaired"], 16, 8, 3)
        for (r, c) in locks:
            assert got["repaired"][r][c] == grid[r][c]
        print(f"  [OK] 16x8 K=3 半锁定: 翻转 {len(got['flips'])} 格, {dt:.2f}s")
    else:
        print(f"  [OK] 16x8 K=3 半锁定: 无解, {dt:.2f}s")

    # 大网格 + 区间性能
    for lo, hi in ((0, 128), (48, 80), (64, 64), (96, 128)):
        grid = [[rng.randint(0, 1) for _ in range(8)] for _ in range(16)]
        t0 = time.time()
        got = solve_repair(16, 8, 3, grid, [], [lo, hi])
        dt = time.time() - t0
        if got is not None:
            total = sum(flat(got["repaired"]))
            assert lo <= total <= hi
            assert not find_violations(got["repaired"], 16, 8, 3)
            print(f"  [OK] 16x8 K=3 区间[{lo},{hi}]: 翻转 {len(got['flips'])} 格,"
                  f" 总数 {total}, {dt:.2f}s")
        else:
            print(f"  [OK] 16x8 K=3 区间[{lo},{hi}]: 无解, {dt:.2f}s")
        assert dt < 10, "求解超时"

    print("\n全部通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
