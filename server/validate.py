"""设计稿（尺寸、格值、锁定格、K、格值1总数区间）的合法性校验。"""

MAX_ROWS = 16
MAX_COLS = 8


class ValidationError(ValueError):
    """输入不合法，携带面向用户的中文错误信息。"""


def _is_int(v):
    # JSON 里 bool 是 int 的子类，需排除；不接受浮点/字符串
    return isinstance(v, int) and not isinstance(v, bool)


def validate_design(payload):
    """校验并规范化设计稿，返回 (rows, cols, grid, locks, k, ones_range)。

    ones_range 为 [下限, 上限] 或 None（未指定，修补不约束格值1总数）。
    不合法时抛出 ValidationError。
    """
    if not isinstance(payload, dict):
        raise ValidationError("请求体必须是 JSON 对象")

    rows, cols, k = payload.get("rows"), payload.get("cols"), payload.get("k")
    if not _is_int(rows) or not 1 <= rows <= MAX_ROWS:
        raise ValidationError(f"行数必须是 1~{MAX_ROWS} 的整数")
    if not _is_int(cols) or not 1 <= cols <= MAX_COLS:
        raise ValidationError(f"列数必须是 1~{MAX_COLS} 的整数")
    if not _is_int(k) or k < 1:
        raise ValidationError("最大浮长 K 必须是正整数")

    grid = payload.get("grid")
    if (not isinstance(grid, list) or len(grid) != rows
            or any(not isinstance(row, list) or len(row) != cols
                   for row in grid)):
        raise ValidationError("交织格必须是与尺寸一致的矩形数组")
    for r in range(rows):
        for c in range(cols):
            v = grid[r][c]
            if not _is_int(v) or v not in (0, 1):
                raise ValidationError(f"格值只能为 0 或 1（第 {r + 1} 行第 {c + 1} 列不合法）")

    locks = payload.get("locks")
    if not isinstance(locks, list):
        raise ValidationError("锁定格必须是坐标数组")
    norm_locks = set()
    for item in locks:
        if (not isinstance(item, list) or len(item) != 2
                or not _is_int(item[0]) or not _is_int(item[1])):
            raise ValidationError("锁定格坐标必须是 [行, 列] 整数对")
        r, c = item
        if not (0 <= r < rows and 0 <= c < cols):
            raise ValidationError(f"锁定格 ({r + 1}, {c + 1}) 越界")
        norm_locks.add((r, c))

    grid = [[int(v) for v in row] for row in grid]
    locks = sorted(norm_locks)
    ones_range = _validate_ones_range(payload.get("onesRange"), rows, cols)
    return rows, cols, grid, locks, k, ones_range


def _validate_ones_range(value, rows, cols):
    """格值1总数区间：缺省/null 表示不约束；否则两端都必填且 0≤下限≤上限≤总格数。

    越界（上限超过行数×列数）直接拒绝并提示调整，不做截断。
    """
    if value is None:
        return None
    total = rows * cols
    if (not isinstance(value, list) or len(value) != 2
            or not _is_int(value[0]) or not _is_int(value[1])):
        raise ValidationError("格值1总数区间必须是 [下限, 上限] 两个整数，两端都必填")
    lo, hi = value
    if not 0 <= lo <= hi:
        raise ValidationError("格值1总数区间须满足 0 ≤ 下限 ≤ 上限")
    if hi > total:
        raise ValidationError(
            f"格值1总数区间上限 {hi} 超过总格数 {total}（行数×列数），请调整区间")
    return [lo, hi]


def canonical(rows, cols, grid, locks, k, ones_range=None):
    """规范化后的可哈希表示，用于预览一致性比对（含格值1总数区间）。"""
    return {
        "rows": rows,
        "cols": cols,
        "grid": [list(row) for row in grid],
        "locks": [list(p) for p in sorted(map(tuple, locks))],
        "k": k,
        "onesRange": list(ones_range) if ones_range is not None else None,
    }
