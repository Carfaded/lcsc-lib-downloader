# -*- coding: utf-8 -*-
"""STEP 模型"纯元件/含PCB"检查工具
================================
用法:
    python verify_step.py 文件.step [更多文件.step ...]

检查项:
  1. 内部 PRODUCT 名称列表
  2. PCB/board/substrate 等关键词命中
  3. 实体数量 (MANIFOLD_SOLID_BREP)
  4. 实体真实包围盒(仅统计被 EDGE_CURVE 引用的顶点,
     避免大半径小弧段倒圆角的圆心点干扰导致误判)
"""
import re
import sys

try:
    sys.stdout.reconfigure(errors="replace")
except Exception:  # noqa: BLE001
    pass


def check(path):
    try:
        text = open(path, encoding="utf-8", errors="ignore").read()
    except OSError as e:
        print(f"[读取失败] {path}: {e}")
        return False

    prods = sorted(set(re.findall(r"PRODUCT\s*\(\s*'([^']*)'", text)))
    solids = len(re.findall(r"MANIFOLD_SOLID_BREP", text))
    low = text.lower()
    hits = [w for w in ("pcb", "board", "substrate", "panel") if w in low]

    used_vp = set()
    for m in re.finditer(r"EDGE_CURVE\s*\(\s*'[^']*'\s*,\s*#(\d+)\s*,\s*#(\d+)", text):
        used_vp.add(m.group(1))
        used_vp.add(m.group(2))
    vp2pt = {m.group(1): m.group(2) for m in re.finditer(
        r"#(\d+)\s*=\s*VERTEX_POINT\s*\(\s*'[^']*'\s*,\s*#(\d+)", text)}
    coord = {}
    for m in re.finditer(
            r"#(\d+)\s*=\s*CARTESIAN_POINT\s*\(\s*'[^']*'\s*,\s*\(\s*"
            r"([-+0-9.eE]+)\s*,\s*([-+0-9.eE]+)\s*,\s*([-+0-9.eE]+)\s*\)", text):
        coord[m.group(1)] = (float(m.group(2)), float(m.group(3)), float(m.group(4)))

    pts = [coord[vp2pt[v]] for v in used_vp if v in vp2pt and vp2pt[v] in coord]
    dims = "?"
    big = False
    if pts:
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        zs = [p[2] for p in pts]
        span = max(max(xs) - min(xs), max(ys) - min(ys), max(zs) - min(zs))
        dims = f"{max(xs) - min(xs):.2f} x {max(ys) - min(ys):.2f} x {max(zs) - min(zs):.2f} mm"
        big = span > 250

    print(f"== {path} ==")
    print(f"   PRODUCT   : {' | '.join(prods) if prods else '(无)'}")
    print(f"   实体数量  : {solids}")
    print(f"   实体尺寸  : {dims}")
    ok = True
    if hits:
        print(f"   !! 关键词命中: {','.join(hits)}  <-- 疑似含PCB/板体字样")
        ok = False
    if big:
        print("   !! 尺寸异常大(>250mm), 疑似包含板体或异常几何")
        ok = False
    if not prods:
        print("   !! 未解析到 PRODUCT 名称, 文件可能不是标准 STEP")
        ok = False
    print("   结论      : " + ("OK, 疑似纯元器件模型" if ok else "需人工用CAD打开确认"))
    return ok


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    all_ok = True
    for f in sys.argv[1:]:
        all_ok &= check(f)
        print()
    sys.exit(0 if all_ok else 2)
