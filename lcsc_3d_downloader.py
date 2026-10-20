#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
立创商城 元件库批量下载器 (命令行版)
=====================================
按立创编号 (Cxxxxx) 一次下载四类元件数据:
  1. 3D 模型    -> {编号}_{封装}.step             纯元器件 STEP, 不含 PCB 基板
  2. 原理图符号 -> {编号}_{器件名}.symbol.json     立创EDA 格式
  3. PCB 封装   -> {编号}_{封装名}.footprint.json  立创EDA 格式
  4. AD 库      -> {编号}_{器件名}.SchLib + {编号}_{封装名}.PcbLib
                   Altium Designer 原生库(默认内嵌3D模型), AD 中直接打开使用
                   加 --merge 则批次内所有器件合并为单个 LCSC3D.SchLib + LCSC3D.PcbLib
                   (封装自动去重, 符号引用最终封装名)

符号/封装 JSON 可在立创EDA(标准版/专业版)中导入使用。

用法:
  python lcsc_3d_downloader.py C131443 C25804 C14663
  python lcsc_3d_downloader.py -f codes.txt
  python lcsc_3d_downloader.py C131443 --types 3d            # 只下3D模型
  python lcsc_3d_downloader.py C131443 --types symbol,footprint
  python lcsc_3d_downloader.py C131443 --types ad            # 只生成AD库(SchLib/PcbLib)
  python lcsc_3d_downloader.py -f codes.txt --merge --types ad   # AD库合并为单个库文件
  python lcsc_3d_downloader.py -f codes.txt -o D:/step --force

参数:
  -f, --file FILE    从文本文件读取编号列表 (一行一个, 支持 # 注释)
  -o, --out DIR      输出目录 (默认: 脚本同级 step/ 目录)
  --types TYPES      下载内容: all(默认) 或 3d,symbol,footprint,ad 的组合
  --force            已存在也重新下载
  --delay SEC        接口请求间隔秒数 (默认 1.2, 立创有风控, 不建议调太小)
  --no-verify        跳过 3D 模型的无PCB校验
  --no-ad-3d         AD库不内嵌3D模型 (默认内嵌)
  --merge            AD库合并模式: 所有器件合并为单个 LCSC3D.SchLib / LCSC3D.PcbLib

依赖: 仅 Python 标准库 (3.8+)
"""
import argparse
import gzip
import json
import os
import re
import ssl
import sys
import time
import urllib.parse
import urllib.request

HOST_PRO = "https://pro.lceda.cn"
HOST_STD = "https://lceda.cn"
CDN_3D = "https://modules.lceda.cn/qAxj6KHrDKw4blvCG8QJPs7Y/"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
RETRY_TIMES = 6
RETRY_DELAY_BASE = 3.0
SSL_CTX = ssl.create_default_context()

try:
    sys.stdout.reconfigure(errors="replace")
except Exception:  # noqa: BLE001
    pass


def headers_for(host):
    return {
        "User-Agent": UA, "Accept": "*/*",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Origin": host, "Referer": host + "/editor", "Connection": "keep-alive",
    }


# ---------------- 网络层 ----------------
def _read_body(resp):
    raw = resp.read()
    if resp.headers.get("Content-Encoding") == "gzip":
        raw = gzip.decompress(raw)
    return raw


def _retry(fn, desc=""):
    last = None
    for i in range(RETRY_TIMES):
        try:
            return fn()
        except Exception as e:  # noqa: BLE001
            last = e
            wait = RETRY_DELAY_BASE * (i + 1)
            print(f"      [重试 {i + 1}/{RETRY_TIMES}] {type(e).__name__} {desc} -> 等待 {wait:.0f}s")
            time.sleep(wait)
    raise last


def api_post(host, path, data):
    body = urllib.parse.urlencode(data, doseq=True).encode()
    h = headers_for(host)
    h["Content-Type"] = "application/x-www-form-urlencoded; charset=UTF-8"

    def _do():
        req = urllib.request.Request(host + path, data=body, headers=h)
        with urllib.request.urlopen(req, timeout=30, context=SSL_CTX) as r:
            return json.loads(_read_body(r).decode("utf-8"))

    return _retry(_do, path)


def api_get_json(host, path):
    def _do():
        req = urllib.request.Request(host + path, headers=headers_for(host))
        with urllib.request.urlopen(req, timeout=30, context=SSL_CTX) as r:
            return json.loads(_read_body(r).decode("utf-8"))

    return _retry(_do, path)


def http_get_bytes(url):
    def _do():
        req = urllib.request.Request(url, headers=headers_for(HOST_PRO))
        with urllib.request.urlopen(req, timeout=120, context=SSL_CTX) as r:
            return _read_body(r)

    return _retry(_do, url)


# ---------------- 核心逻辑 ----------------
def normalize_code(raw):
    s = raw.strip().upper()
    if not s:
        return None
    if s.isdigit():
        s = "C" + s
    if not re.fullmatch(r"C\d+", s):
        return None
    return s


def safe_name(s):
    return re.sub(r'[\\/:*?"<>|]', "_", str(s)).strip() or "unnamed"


def _svgnode_uuid(pkg_detail):
    """从标准版封装数据(SVGNODE)提取 3D 模型资源编号。

    该编号与专业版链路 dataStr.model 为同一个值, 可直连 CDN 取 STEP。
    """
    try:
        doc = pkg_detail.get("dataStr") if isinstance(pkg_detail, dict) else None
        if isinstance(doc, str):
            doc = json.loads(doc)
        for shape in (doc or {}).get("shape") or []:
            if not (isinstance(shape, str) and shape.startswith("SVGNODE~")):
                continue
            attrs = (json.loads(shape.partition("~")[2]) or {}).get("attrs") or {}
            if attrs.get("c_etype") in (None, "outline3D") and attrs.get("uuid"):
                return attrs["uuid"]
    except (ValueError, TypeError, AttributeError):
        pass
    return None


def _same_model(code, item):
    """搜索结果是否为该编号的换号同型号。

    仅在数字部分完全相等时成立, 避免 C8299 误配到 C82993 这类风险。
    """
    digits = re.sub(r"\D", "", str(code or ""))
    if not digits:
        return False
    return digits == re.sub(r"\D", "", str(item.get("model") or ""))


def _fetch_3d_by_std(code, outdir, force, alt_codes=()):
    """回退路径: 用标准版封装资源里的 3D 编号直连 CDN 下载 STEP。

    按顺序尝试目标编号与候选新编号(立创改号时旧号仍保留封装数据)。
    """
    last = ""
    for target in (code, *alt_codes):
        if not target or (target == code and last):
            continue
        try:
            data = api_get_json(HOST_STD, f"/api/products/{urllib.parse.quote(target)}/components")
        except Exception as e:  # noqa: BLE001
            last = f"标准版接口异常({type(e).__name__})"
            continue
        if not data.get("success") or data.get("code") != 0:
            last = data.get("message") or "标准版接口无该编号数据"
            continue
        res = data.get("result") or {}
        pkg = res.get("packageDetail") or {}
        uuid = _svgnode_uuid(pkg)
        if not uuid:
            last = "标准版封装数据中无 3D 模型"
            continue
        footprint = pkg.get("title") or "Footprint"
        fpath = os.path.join(outdir, f"{code}_{safe_name(footprint)}.step")
        if os.path.exists(fpath) and not force:
            return "skip", fpath, footprint
        raw = http_get_bytes(CDN_3D + uuid)
        if not raw.lstrip().startswith(b"ISO-10303"):
            last = f"回退下载内容不是STEP({len(raw)}B)"
            continue
        with open(fpath, "wb") as f:
            f.write(raw)
        return "ok", fpath, footprint
    return "fail", last, ""


def fetch_3d(code, outdir, delay, force):
    """3D 模型 STEP。返回 (状态, 文件路径或原因, 型号)

    优先走专业版器件链路; 任一环节拿不到模型时自动回退:
      1) 编号被更换时, 用搜索到的同型号新编号重试;
      2) 标准版封装资源里的 3D 编号直连 CDN (与专业版同源)。
    """
    try:
        d1 = api_post(HOST_PRO, "/api/eda/product/search", {
            "keyword": code, "needAggs": "true",
            "url": "/api/eda/product/list", "currPage": "1", "pageSize": "10",
        })
    except Exception as e:  # noqa: BLE001
        return "fail", f"接口请求失败({type(e).__name__})", ""
    plist = (d1.get("result") or {}).get("productList") or []
    item = next((x for x in plist if str(x.get("code", "")).upper() == code), None)
    renamed = ""
    if item is None:
        # 编号被更换时用同型号新编号继续(仅数字部分完全一致才采纳, 避免拿到别的器件)
        alt = next((x for x in plist if _same_model(code, x)), None)
        if alt is not None:
            item = alt
            renamed = str(alt.get("code") or "")
    if item is None:
        return _fallback_3d(code, outdir, force, "专业版未找到该编号的商品", renamed)
    model_name = item.get("model") or ""
    std = item.get("standard") or ""
    time.sleep(delay)

    has_device = item.get("hasDevice")
    if not has_device:
        return _fallback_3d(code, outdir, force, f"{model_name} 无关联EDA器件", renamed)
    d2 = api_post(HOST_PRO, "/api/devices/searchByIds", {"uuids[]": has_device, "path": outdir})
    r2 = (d2.get("result") or [])
    if not r2:
        return _fallback_3d(code, outdir, force, "器件查询失败", renamed)
    attrs = r2[0].get("attributes") or {}
    model_uuid = attrs.get("3D Model")
    footprint = attrs.get("Supplier Footprint") or std
    if not model_uuid:
        return _fallback_3d(code, outdir, force, f"{model_name} 该器件无3D模型", renamed)
    time.sleep(delay)

    d3 = api_post(HOST_PRO, "/api/components/searchByIds?forceOnline=1",
                  {"uuids[]": model_uuid, "dataStr": "yes", "path": outdir})
    r3 = (d3.get("result") or [])
    if not r3:
        return _fallback_3d(code, outdir, force, "3D模型信息查询失败", renamed)
    try:
        data_str = json.loads(r3[0].get("dataStr") or "{}")
    except json.JSONDecodeError:
        return _fallback_3d(code, outdir, force, "3D模型数据解析失败", renamed)
    model_file = data_str.get("model")
    if not model_file:
        return _fallback_3d(code, outdir, force, "3D模型文件名为空", renamed)

    fpath = os.path.join(outdir, f"{code}_{safe_name(footprint)}.step")
    if os.path.exists(fpath) and not force:
        return "skip", fpath, model_name
    raw = http_get_bytes(CDN_3D + model_file)
    if not raw.lstrip().startswith(b"ISO-10303"):
        preview = raw[:80].decode("utf-8", "ignore").replace("\n", " ")
        return _fallback_3d(code, outdir, force,
                            f"专业版返回非STEP({len(raw)}B): {preview}", renamed)
    with open(fpath, "wb") as f:
        f.write(raw)
    return "ok", fpath, model_name


def _fallback_3d(code, outdir, force, reason, renamed=""):
    """专业版链路失败 -> 回退标准版 3D 资源; 仍失败则返回明确原因。"""
    if renamed:
        reason = f"{reason} (编号已变更为 {renamed})"
    print(f"      · 专业版链路不可用({reason})，改用标准版 3D 资源")
    status, path, name = _fetch_3d_by_std(code, outdir, force,
                                           (renamed,) if renamed else ())
    if status == "fail":
        print(f"      · 标准版回退也失败: {path}")
        return "fail", f"{reason}; 标准版回退失败({path})", name
    return status, path, name


def fetch_std_data(code):
    """符号+封装数据 (立创EDA标准版格式)。返回 (状态, dict 或 原因)"""
    try:
        data = api_get_json(HOST_STD, f"/api/products/{urllib.parse.quote(code)}/components")
    except Exception as e:  # noqa: BLE001
        return "fail", f"网络异常({type(e).__name__})"
    if not data.get("success") or data.get("code") != 0:
        return "fail", data.get("message") or "接口返回失败"
    res = data.get("result") or {}
    if not res.get("dataStr"):
        return "fail", "未找到该编号数据"

    sym_ds = res["dataStr"]
    if not isinstance(sym_ds, dict):
        try:
            sym_ds = json.loads(sym_ds)
        except (json.JSONDecodeError, TypeError):
            return "fail", "符号数据格式异常"
    sym_title = res.get("title") or (sym_ds.get("head", {}).get("c_para", {}) or {}).get("name") or "symbol"
    symbol = {"title": sym_title, "data": sym_ds, "elements": len(sym_ds.get("shape") or [])}

    footprint = None
    pkg = res.get("packageDetail")
    if pkg and pkg.get("dataStr"):
        pds = pkg["dataStr"]
        if not isinstance(pds, dict):
            try:
                pds = json.loads(pds)
            except (json.JSONDecodeError, TypeError):
                pds = None
        if isinstance(pds, dict):
            shapes = pds.get("shape") or []
            pads = sum(1 for s in shapes if isinstance(s, str) and s.startswith(("PAD", "VIA")))
            footprint = {"title": pkg.get("title") or "footprint", "data": pds,
                         "elements": len(shapes), "pads": pads}
    return "ok", {"symbol": symbol, "footprint": footprint, "raw": res}


def save_json_doc(doc, fpath):
    with open(fpath, "w", encoding="utf-8") as f:
        json.dump(doc["data"], f, ensure_ascii=False, indent=1)


def verify_step(path):
    """校验 3D STEP: PCB关键词 + PRODUCT名 + 实体数 + 实体真实包围盒(顶点法)"""
    try:
        text = open(path, encoding="utf-8", errors="ignore").read()
    except OSError as e:
        return True, "读取失败", str(e)
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
    dims, big = "?", False
    pts = [coord[vp2pt[v]] for v in used_vp if v in vp2pt and vp2pt[v] in coord]
    if pts:
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        zs = [p[2] for p in pts]
        span = max(max(xs) - min(xs), max(ys) - min(ys), max(zs) - min(zs))
        dims = f"{max(xs) - min(xs):.2f} x {max(ys) - min(ys):.2f} x {max(zs) - min(zs):.2f} mm"
        big = span > 250
    info = (" | ".join(prods) if prods else "(无PRODUCT名)") + f" · {solids}个实体"
    if hits:
        info += f" · 命中关键词:{','.join(hits)}"
    if big:
        info += " · 尺寸异常大"
    return (bool(hits) or big), dims, info


def load_codes_from_file(path):
    codes = []
    with open(path, encoding="utf-8-sig") as f:
        for line in f:
            line = line.split("#", 1)[0].strip()
            if not line:
                continue
            for token in re.split(r"[,\s;]+", line):
                c = normalize_code(token)
                if c:
                    codes.append(c)
    return codes


def parse_types(s):
    s = (s or "all").strip().lower()
    if s == "all":
        return {"3d", "symbol", "footprint", "ad"}
    out = set()
    for t in re.split(r"[,\s]+", s):
        t = t.strip()
        if t in ("3d", "step", "model"):
            out.add("3d")
        elif t in ("symbol", "sch", "原理图"):
            out.add("symbol")
        elif t in ("footprint", "pcb", "封装"):
            out.add("footprint")
        elif t in ("ad", "altium", "adlib", "ad库"):
            out.add("ad")
    return out


def main():
    ap = argparse.ArgumentParser(
        description="立创商城 元件库批量下载器 - 3D模型/原理图符号/PCB封装",
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("codes", nargs="*", help="立创商城编号, 如 C131443 C25804")
    ap.add_argument("-f", "--file", help="编号列表文件(一行一个, 支持#注释)")
    ap.add_argument("-o", "--out", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "step"),
                    help="输出目录 (默认: 脚本同级 step/ 目录)")
    ap.add_argument("--types", default="all",
                    help="下载内容: all(默认) 或 3d,symbol,footprint,ad 组合")
    ap.add_argument("--force", action="store_true", help="已存在也重新下载")
    ap.add_argument("--delay", type=float, default=1.2, help="接口请求间隔秒数(默认1.2)")
    ap.add_argument("--no-verify", action="store_true", help="跳过3D模型无PCB校验")
    ap.add_argument("--no-ad-3d", action="store_true", help="AD库不内嵌3D模型(默认内嵌)")
    ap.add_argument("--merge", action="store_true",
                    help="AD库合并模式: 所有器件合并为单个 LCSC3D.SchLib / LCSC3D.PcbLib")
    args = ap.parse_args()

    types = parse_types(args.types)
    if not types:
        print("--types 参数无效, 可选: all / 3d / symbol / footprint / ad")
        sys.exit(1)
    if args.merge and "ad" not in types:
        types.add("ad")
        print("提示: --merge 需要 AD库内容, 已自动加入\n")

    codes = [c for c in (normalize_code(x) for x in args.codes) if c]
    if args.file:
        codes += load_codes_from_file(args.file)
    seen, uniq = set(), []
    for c in codes:
        if c not in seen:
            seen.add(c)
            uniq.append(c)
    codes = uniq
    if not codes:
        ap.print_help()
        sys.exit(1)

    os.makedirs(args.out, exist_ok=True)
    type_cn = {"3d": "3D模型", "symbol": "原理图符号", "footprint": "PCB封装", "ad": "AD库(SchLib/PcbLib)"}
    print(f"共 {len(codes)} 个编号 -> {os.path.abspath(args.out)}")
    print(f"下载内容: {' + '.join(type_cn[t] for t in ('3d', 'symbol', 'footprint', 'ad') if t in types)}\n")

    stats = {"ok": 0, "skip": 0, "fail": 0}
    failed = []
    t0 = time.time()

    # 合并模式: 批次内所有器件的 AD 库最后合并为单个 SchLib/PcbLib
    merger = None
    if args.merge:
        try:
            from ad_export import AdLibraryMerger
            merger = AdLibraryMerger(embed_model=not args.no_ad_3d, fetch=http_get_bytes,
                                     log=lambda m: print(m))
        except Exception as e:  # noqa: BLE001
            print(f"! 合并模式不可用, 改为生成单器件库: {e}")

    for i, code in enumerate(codes, 1):
        print(f"[{i}/{len(codes)}] {code} ...")

        if "3d" in types:
            try:
                status, info, model = fetch_3d(code, args.out, args.delay, args.force)
            except Exception as e:  # noqa: BLE001
                status, info, model = "fail", f"网络异常(已重试): {type(e).__name__}", ""
            if status == "ok":
                detail = ""
                if not args.no_verify:
                    suspect, dims, vinfo = verify_step(info)
                    detail = f"  [{dims} · {vinfo}]"
                    if suspect:
                        detail += "  !! 疑似含PCB/异常"
                size_mb = os.path.getsize(info) / 1048576
                print(f"    √ 3D模型: {os.path.basename(info)}  ({size_mb:.2f} MB){detail}")
                stats["ok"] += 1
            elif status == "skip":
                print(f"    - 3D模型已存在跳过: {os.path.basename(info)}")
                stats["skip"] += 1
            else:
                print(f"    × 3D模型失败: {info}   (型号: {model})")
                stats["fail"] += 1
                failed.append((code, "3D模型", info))

        if "symbol" in types or "footprint" in types or "ad" in types:
            try:
                s_status, s_data = fetch_std_data(code)
            except Exception as e:  # noqa: BLE001
                s_status, s_data = "fail", f"网络异常(已重试): {type(e).__name__}"
            if s_status != "ok":
                for t in ("symbol", "footprint", "ad"):
                    if t in types:
                        print(f"    × {type_cn[t]}失败: {s_data}")
                        stats["fail"] += 1
                        failed.append((code, type_cn[t], str(s_data)))
            else:
                if "symbol" in types:
                    sym = s_data.get("symbol")
                    if not sym:
                        print("    × 原理图符号失败: 该元件无符号数据")
                        stats["fail"] += 1
                        failed.append((code, "原理图符号", "无符号数据"))
                    else:
                        fpath = os.path.join(args.out, f"{code}_{safe_name(sym['title'])}.symbol.json")
                        if os.path.exists(fpath) and not args.force:
                            print(f"    - 符号已存在跳过: {os.path.basename(fpath)}")
                            stats["skip"] += 1
                        else:
                            save_json_doc(sym, fpath)
                            print(f"    √ 原理图符号: {os.path.basename(fpath)}  [{sym['elements']}个图元]")
                            stats["ok"] += 1
                if "footprint" in types:
                    fp = s_data.get("footprint")
                    if not fp:
                        print("    × PCB封装失败: 该元件无封装数据")
                        stats["fail"] += 1
                        failed.append((code, "PCB封装", "无封装数据"))
                    else:
                        fpath = os.path.join(args.out, f"{code}_{safe_name(fp['title'])}.footprint.json")
                        if os.path.exists(fpath) and not args.force:
                            print(f"    - 封装已存在跳过: {os.path.basename(fpath)}")
                            stats["skip"] += 1
                        else:
                            save_json_doc(fp, fpath)
                            print(f"    √ PCB封装: {os.path.basename(fpath)}  "
                                  f"[{fp['elements']}个图元 / {fp['pads']}个焊盘]")
                            stats["ok"] += 1
                if "ad" in types:
                    if merger is not None:
                        try:
                            minfo = merger.add(s_data.get("raw") or {}, code)
                        except Exception as e:  # noqa: BLE001
                            print(f"    × AD库(合并)失败: {e}")
                            stats["fail"] += 1
                            failed.append((code, "AD库", str(e)))
                        else:
                            print("    √ AD库: 已加入合并库"
                                  + ("（含3D）" if minfo.get("embedded") else ""))
                            stats["ok"] += 1
                    else:
                        try:
                            from ad_export import export_altium
                            adr = export_altium(s_data.get("raw") or {}, code, args.out,
                                                skip_existing=not args.force,
                                                embed_model=not args.no_ad_3d,
                                                fetch=http_get_bytes,
                                                log=lambda m: print(m))
                        except Exception as e:  # noqa: BLE001
                            print(f"    × AD库失败: {e}")
                            stats["fail"] += 1
                            failed.append((code, "AD库", str(e)))
                        else:
                            if adr["status"] == "skip":
                                print(f"    - AD库已存在跳过: {os.path.basename(adr['schlib'])}")
                                stats["skip"] += 1
                            else:
                                print(f"    √ AD库: {os.path.basename(adr['schlib'])} + "
                                      f"{os.path.basename(adr['pcblib'])}  "
                                      f"[SchLib {adr['schlib_size'] / 1024:.0f}KB / "
                                      f"PcbLib {adr['pcblib_size'] / 1024:.0f}KB"
                                      + ("，含内嵌3D" if adr.get("embedded") else "")
                                      + "]")
                                stats["ok"] += 1
        time.sleep(args.delay * 0.4)

    # ---- 合并构建 ----
    if merger is not None and merger.parts:
        print(f"\n正在构建合并库（{len(merger.parts)} 个器件）...")
        try:
            mr = merger.build(args.out)
        except Exception as e:  # noqa: BLE001
            print(f"    × 合并库失败: {e}")
            stats["fail"] += 1
            failed.append(("-", "合并库", str(e)))
        else:
            print(f"    ★ 合并库: {os.path.basename(mr['schlib'])} + {os.path.basename(mr['pcblib'])}"
                  f"  [{mr['count']} 个器件 / SchLib {mr['schlib_size'] / 1024:.0f}KB / "
                  f"PcbLib {mr['pcblib_size'] / 1024:.0f}KB]")
    elif merger is not None:
        print("! 没有成功加入合并库的器件")

    elapsed = time.time() - t0
    print("\n" + "=" * 62)
    print(f"完成: 文件 {stats['ok']} 成功 / {stats['skip']} 跳过 / {stats['fail']} 失败  用时 {elapsed:.0f}s")
    print(f"输出目录: {os.path.abspath(args.out)}")
    if failed:
        print("失败清单:")
        for code, kind, reason in failed:
            print(f"  {code} {kind}: {reason}")
    sys.exit(0 if stats["fail"] == 0 else 2)


if __name__ == "__main__":
    main()
