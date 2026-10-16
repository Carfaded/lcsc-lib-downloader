#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
立创商城 元件库批量下载器 (GUI 版)
====================================
按立创编号 (Cxxxxx) 一次下载三类元件数据:
  1. 3D 模型    -> {编号}_{封装}.step            纯元器件 STEP, 不含 PCB 基板
  2. 原理图符号 -> {编号}_{器件名}.symbol.json    立创EDA 格式
  3. PCB 封装   -> {编号}_{封装名}.footprint.json 立创EDA 格式

符号/封装 JSON 可在立创EDA(标准版/专业版)中导入使用;
3D 模型 STEP 可导入 SolidWorks / Altium / FreeCAD 等做 3D 装配。

打包 (Windows):
  pyinstaller --onefile --noconsole --name lcsc3d_gui --icon app.ico --add-data "app.ico;." lcsc_3d_gui.py

自测模式 (打包后验证用):
  lcsc3d_gui.exe --selftest [C131443]
"""
import gzip
import json
import os
import queue
import re
import ssl
import sys
import threading
import time
import traceback
import urllib.parse
import urllib.request

# ---------------- 环境与常量 ----------------
IS_FROZEN = getattr(sys, "frozen", False)
BASE_DIR = os.path.dirname(sys.executable) if IS_FROZEN else os.path.dirname(os.path.abspath(__file__))

if sys.stdout is None:
    sys.stdout = open(os.devnull, "w", encoding="utf-8")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w", encoding="utf-8")
try:
    sys.stdout.reconfigure(errors="replace")
    sys.stderr.reconfigure(errors="replace")
except Exception:  # noqa: BLE001
    pass

APP_TITLE = "立创商城 元件库批量下载器"
HOST_PRO = "https://pro.lceda.cn"          # 专业版接口(3D模型/器件)
HOST_STD = "https://lceda.cn"              # 标准版接口(符号/封装)
CDN_3D = "https://modules.lceda.cn/qAxj6KHrDKw4blvCG8QJPs7Y/"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
RETRY_TIMES = 6
RETRY_DELAY_BASE = 3.0
DEFAULT_DELAY = 1.2

# 配色
C_PRIMARY = "#2563eb"
C_PRIMARY_D = "#1d4ed8"
C_BG = "#f3f5f9"
C_CARD = "#ffffff"
C_BORDER = "#d8dee8"
C_TEXT = "#1f2937"
C_MUTED = "#6b7280"
C_OK = "#0a7a28"
C_ERR = "#c62828"
C_WARN = "#b26a00"
C_HEAD = "#1a4f8a"

# 字体
FONT_FAMILY = "Microsoft YaHei UI"
FONT = (FONT_FAMILY, 9)
FONT_B = (FONT_FAMILY, 9, "bold")
FONT_IN = (FONT_FAMILY, 10)
FONT_TITLE = (FONT_FAMILY, 15, "bold")
FONT_SUB = (FONT_FAMILY, 9)


def _mk_ctx():
    return ssl.create_default_context()


SSL_CTX = _mk_ctx()


def resource_path(name):
    base = getattr(sys, "_MEIPASS", BASE_DIR)
    return os.path.join(base, name)


def headers_for(host):
    return {
        "User-Agent": UA,
        "Accept": "*/*",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Origin": host,
        "Referer": host + "/editor",
        "Connection": "keep-alive",
    }


# ---------------- 网络层 ----------------
def _read_body(resp):
    raw = resp.read()
    if resp.headers.get("Content-Encoding") == "gzip":
        raw = gzip.decompress(raw)
    return raw


def _retry(fn, log=None):
    last = None
    for i in range(RETRY_TIMES):
        try:
            return fn()
        except Exception as e:  # noqa: BLE001
            last = e
            wait = RETRY_DELAY_BASE * (i + 1)
            if log:
                log(f"      接口连接被断开(风控), 第 {i + 1}/{RETRY_TIMES} 次重试, 等待 {wait:.0f}s", "warn")
            time.sleep(wait)
    raise last


def api_post(host, path, data, log=None):
    body = urllib.parse.urlencode(data, doseq=True).encode()
    h = headers_for(host)
    h["Content-Type"] = "application/x-www-form-urlencoded; charset=UTF-8"

    def _do():
        req = urllib.request.Request(host + path, data=body, headers=h)
        with urllib.request.urlopen(req, timeout=30, context=SSL_CTX) as r:
            return json.loads(_read_body(r).decode("utf-8"))

    return _retry(_do, log)


def api_get_json(host, path, log=None):
    def _do():
        req = urllib.request.Request(host + path, headers=headers_for(host))
        with urllib.request.urlopen(req, timeout=30, context=SSL_CTX) as r:
            return json.loads(_read_body(r).decode("utf-8"))

    return _retry(_do, log)


def http_get_bytes(url, log=None):
    def _do():
        req = urllib.request.Request(url, headers=headers_for(HOST_PRO))
        with urllib.request.urlopen(req, timeout=120, context=SSL_CTX) as r:
            return _read_body(r)

    return _retry(_do, log)


# ---------------- 通用 ----------------
def normalize_code(raw):
    s = raw.strip().upper()
    if not s:
        return None
    if s.isdigit():
        s = "C" + s
    if not re.fullmatch(r"C\d+", s):
        return None
    return s


def parse_codes(text):
    codes = []
    for token in re.split(r"[\s,;，；、]+", text):
        token = token.strip()
        if not token or token.startswith("#"):
            continue
        c = normalize_code(token)
        if c:
            codes.append(c)
    seen, out = set(), []
    for c in codes:
        if c not in seen:
            seen.add(c)
            out.append(c)
    return out


def safe_name(s):
    return re.sub(r'[\\/:*?"<>|]', "_", str(s)).strip() or "unnamed"


# ---------------- 下载逻辑 ----------------
def fetch_3d(code, outdir, delay, force, log=None):
    """3D 模型 (STEP, 纯元件不含PCB)。返回 (状态, 文件路径或原因, 型号)"""
    d1 = api_post(HOST_PRO, "/api/eda/product/search", {
        "keyword": code, "needAggs": "true",
        "url": "/api/eda/product/list", "currPage": "1", "pageSize": "10",
    }, log)
    plist = (d1.get("result") or {}).get("productList") or []
    item = next((x for x in plist if str(x.get("code", "")).upper() == code), None)
    if item is None:
        return "fail", "未找到该编号的商品", ""
    model_name = item.get("model") or ""
    std = item.get("standard") or ""
    time.sleep(delay)

    has_device = item.get("hasDevice")
    if not has_device:
        return "fail", f"{model_name} 无关联EDA器件(无3D模型)", model_name
    d2 = api_post(HOST_PRO, "/api/devices/searchByIds", {"uuids[]": has_device, "path": outdir}, log)
    r2 = (d2.get("result") or [])
    if not r2:
        return "fail", "器件查询失败", model_name
    attrs = r2[0].get("attributes") or {}
    model_uuid = attrs.get("3D Model")
    footprint = attrs.get("Supplier Footprint") or std
    if not model_uuid:
        return "fail", f"{model_name} 该器件无3D模型", model_name
    time.sleep(delay)

    d3 = api_post(HOST_PRO, "/api/components/searchByIds?forceOnline=1",
                  {"uuids[]": model_uuid, "dataStr": "yes", "path": outdir}, log)
    r3 = (d3.get("result") or [])
    if not r3:
        return "fail", "3D模型信息查询失败", model_name
    try:
        data_str = json.loads(r3[0].get("dataStr") or "{}")
    except json.JSONDecodeError:
        return "fail", "3D模型数据解析失败", model_name
    model_file = data_str.get("model")
    if not model_file:
        return "fail", "3D模型文件名为空", model_name

    fname = f"{code}_{safe_name(footprint)}.step"
    fpath = os.path.join(outdir, fname)
    if os.path.exists(fpath) and not force:
        return "skip", fpath, model_name

    raw = http_get_bytes(CDN_3D + model_file, log)
    if not raw.lstrip().startswith(b"ISO-10303"):
        preview = raw[:80].decode("utf-8", "ignore").replace("\n", " ")
        return "fail", f"返回内容不是STEP({len(raw)}B): {preview}", model_name
    with open(fpath, "wb") as f:
        f.write(raw)
    return "ok", fpath, model_name


def fetch_std_data(code, log=None):
    """符号+封装数据 (立创EDA标准版格式)。返回 (状态, {symbol, footprint}) 或 (状态, 原因)"""
    try:
        data = api_get_json(HOST_STD, f"/api/products/{urllib.parse.quote(code)}/components", log)
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
    symbol = {
        "title": sym_title,
        "data": sym_ds,
        "elements": len(sym_ds.get("shape") or []),
    }

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
            footprint = {
                "title": pkg.get("title") or "footprint",
                "data": pds,
                "elements": len(shapes),
                "pads": pads,
            }
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


# ---------------- GUI ----------------
try:
    import tkinter as tk
    from tkinter import filedialog, messagebox, scrolledtext, ttk

    TK_AVAILABLE = True
except ImportError:
    TK_AVAILABLE = False

try:
    import sv_ttk  # 现代 Win11 Fluent 风格主题

    SV_TTK_AVAILABLE = True
except ImportError:
    SV_TTK_AVAILABLE = False

# 确保同目录模块可导入(脚本目录/打包目录)
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

try:
    import ad_export  # AD 库导出 (SchLib/PcbLib, 内置 LCSC3D 转换链)

    AD_EXPORT_AVAILABLE = True
except ImportError:
    ad_export = None
    AD_EXPORT_AVAILABLE = False


def enable_dpi_awareness():
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:  # noqa: BLE001
            pass


def install_excepthook(root=None):
    def hook(exc_type, exc, tb):
        msg = "".join(traceback.format_exception(exc_type, exc, tb))
        try:
            with open(os.path.join(BASE_DIR, "error_log.txt"), "w", encoding="utf-8") as f:
                f.write(time.strftime("%Y-%m-%d %H:%M:%S\n") + msg)
        except Exception:  # noqa: BLE001
            pass
        try:
            messagebox.showerror("程序异常", f"发生未处理异常，详情已写入 error_log.txt：\n\n{msg[-1200:]}")
        except Exception:  # noqa: BLE001
            pass

    sys.excepthook = hook
    if root is not None:
        root.report_callback_exception = hook


class DownloaderApp:
    def __init__(self, root):
        self.root = root
        self.q = queue.Queue()
        self.running = False
        self.outdir_var = tk.StringVar(value=os.path.join(BASE_DIR, "step"))
        self.v_3d = tk.BooleanVar(value=True)
        self.v_sym = tk.BooleanVar(value=True)
        self.v_fp = tk.BooleanVar(value=True)
        self.v_ad = tk.BooleanVar(value=True)
        self.v_ad_embed = tk.BooleanVar(value=True)
        self.v_skip = tk.BooleanVar(value=True)
        self.v_verify = tk.BooleanVar(value=True)
        self._build()
        self.root.after(100, self._poll_queue)

    # ---------- 样式 ----------
    def _setup_style(self):
        """使用 sv_ttk (Sun Valley / Win11 Fluent) 主题; 无则回退系统主题"""
        if SV_TTK_AVAILABLE:
            try:
                sv_ttk.set_theme("light")
            except Exception:  # noqa: BLE001
                pass
        else:
            try:
                ttk.Style(self.root).theme_use("vista")
            except Exception:  # noqa: BLE001
                pass
        style = ttk.Style(self.root)
        try:
            style.configure("Header.TLabel", font=(FONT_FAMILY, 16, "bold"))
            style.configure("SubHeader.TLabel", font=(FONT_FAMILY, 9))
            style.configure("Log.TButton", font=(FONT_FAMILY, 9))
        except Exception:  # noqa: BLE001
            pass

    # ---------- UI ----------
    def _build(self):
        self.root.title(APP_TITLE)
        sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        w = min(840, sw - 40)
        h = min(760, sh - 90)
        x = max(0, (sw - w) // 2)
        y = max(0, (sh - h) // 3)
        self.root.geometry(f"{w}x{h}+{x}+{y}")
        self.root.minsize(min(740, sw - 40), min(600, sh - 120))
        try:
            self.root.iconbitmap(resource_path("app.ico"))
        except Exception:  # noqa: BLE001
            pass
        try:
            self.root.option_add("*Font", FONT)
        except Exception:  # noqa: BLE001
            pass
        self._setup_style()

        # ===== 标题区 =====
        header = ttk.Frame(self.root, padding=(20, 16, 14, 4))
        header.pack(fill="x")
        hleft = ttk.Frame(header)
        hleft.pack(side="left", fill="x", expand=True)
        ttk.Label(hleft, text=APP_TITLE, style="Header.TLabel").pack(anchor="w")
        ttk.Label(hleft, text="3D模型(STEP) · 原理图符号 · PCB封装 · AD库(SchLib/PcbLib)     一键从立创编号 Cxxxxx 下载，3D模型为纯元件不含PCB",
                  style="SubHeader.TLabel").pack(anchor="w", pady=(4, 2))
        ttk.Button(header, text="AD 导出指引", command=self._show_ad_help).pack(side="right", anchor="ne", padx=(10, 0), pady=(4, 0))

        # ===== 主体 =====
        body = ttk.Frame(self.root, padding=(14, 12, 14, 12))
        body.pack(fill="both", expand=True)
        body.columnconfigure(0, weight=1)
        body.rowconfigure(2, weight=1)

        # ---- 卡片1: 下载设置 ----
        card1 = ttk.Labelframe(body, text=" 下载设置 ", padding=(14, 8, 14, 14))
        card1.grid(row=0, column=0, sticky="ew")
        card1.columnconfigure(0, weight=1)

        ttk.Label(card1, text="下载编号（每行一个 Cxxxxx，也支持空格/逗号分隔，自动去重）：").grid(
            row=0, column=0, sticky="w", pady=(4, 0))
        tbox = ttk.Frame(card1)
        tbox.grid(row=1, column=0, sticky="ew", pady=(5, 7))
        tbox.columnconfigure(0, weight=1)
        self.txt_codes = tk.Text(tbox, height=6, wrap="word", undo=True, font=FONT_IN,
                                 relief="solid", bd=1, highlightthickness=0,
                                 bg="white", fg=C_TEXT, insertbackground=C_TEXT)
        sb1 = ttk.Scrollbar(tbox, command=self.txt_codes.yview)
        self.txt_codes["yscrollcommand"] = sb1.set
        self.txt_codes.grid(row=0, column=0, sticky="nsew")
        sb1.grid(row=0, column=1, sticky="ns")

        btn_row = ttk.Frame(card1)
        btn_row.grid(row=2, column=0, sticky="w")
        ttk.Button(btn_row, text="导入 codes.txt",
                   command=self._import_file).pack(side="left")
        ttk.Button(btn_row, text="清空编号",
                   command=lambda: self.txt_codes.delete("1.0", "end")).pack(side="left", padx=(8, 0))

        prow = ttk.Frame(card1)
        prow.grid(row=3, column=0, sticky="ew", pady=(10, 0))
        prow.columnconfigure(1, weight=1)
        ttk.Label(prow, text="保存路径：").grid(row=0, column=0)
        ttk.Entry(prow, textvariable=self.outdir_var).grid(row=0, column=1, sticky="ew", padx=(0, 8))
        ttk.Button(prow, text="浏览…",
                   command=self._choose_dir).grid(row=0, column=2)

        crow = ttk.Frame(card1)
        crow.grid(row=4, column=0, sticky="w", pady=(12, 2))
        ttk.Label(crow, text="下载内容：").pack(side="left")
        ttk.Checkbutton(crow, text="3D模型 (STEP)", variable=self.v_3d).pack(side="left", padx=(4, 18))
        ttk.Checkbutton(crow, text="原理图符号", variable=self.v_sym).pack(side="left", padx=(0, 18))
        ttk.Checkbutton(crow, text="PCB封装", variable=self.v_fp).pack(side="left", padx=(0, 18))
        ttk.Checkbutton(crow, text="AD库 (SchLib/PcbLib)", variable=self.v_ad).pack(side="left")

        orow = ttk.Frame(card1)
        orow.grid(row=5, column=0, sticky="w", pady=(6, 2))
        ttk.Label(orow, text="选项：").pack(side="left")
        ttk.Checkbutton(orow, text="跳过已下载的文件", variable=self.v_skip).pack(side="left", padx=(4, 18))
        ttk.Checkbutton(orow, text="校验 3D 模型不含PCB", variable=self.v_verify).pack(side="left", padx=(0, 18))
        ttk.Checkbutton(orow, text="AD库内嵌3D模型", variable=self.v_ad_embed).pack(side="left")

        # ---- 操作行 ----
        act = ttk.Frame(body)
        act.grid(row=1, column=0, sticky="ew", pady=(12, 8))
        act.columnconfigure(2, weight=1)
        self.btn_start = ttk.Button(act, text="开始下载", style="Accent.TButton", command=self._start)
        self.btn_start.grid(row=0, column=0)
        self.btn_open = ttk.Button(act, text="打开输出文件夹",
                                   command=self._open_outdir)
        self.btn_open.grid(row=0, column=1, padx=(10, 16))
        self.pbar = ttk.Progressbar(act, mode="determinate", maximum=100)
        self.pbar.grid(row=0, column=2, sticky="ew")
        self.lbl_status = ttk.Label(act, text="就绪", width=14, anchor="e")
        self.lbl_status.grid(row=0, column=3, padx=(10, 0))

        # ---- 卡片2: 日志 ----
        card2 = ttk.Labelframe(body, text=" 运行日志 ", padding=(10, 6, 10, 10))
        card2.grid(row=2, column=0, sticky="nsew")
        card2.columnconfigure(0, weight=1)
        card2.rowconfigure(0, weight=1)
        self.txt_log = scrolledtext.ScrolledText(card2, height=13, wrap="word", state="disabled",
                                                 relief="flat", bd=0, bg="white", fg=C_TEXT,
                                                 font=FONT)
        self.txt_log.grid(row=0, column=0, sticky="nsew")
        self.txt_log.tag_configure("ok", foreground=C_OK)
        self.txt_log.tag_configure("err", foreground=C_ERR)
        self.txt_log.tag_configure("warn", foreground=C_WARN)
        self.txt_log.tag_configure("info", foreground=C_TEXT)
        self.txt_log.tag_configure("head", foreground=C_HEAD)
        self.txt_log.tag_configure("muted", foreground=C_MUTED)

        self._append("提示：3D模型为STEP格式(纯元件不含PCB)；符号/封装为立创EDA格式(.json)；"
                     "AD库为 Altium 原生 SchLib/PcbLib，AD 中直接打开使用。\n", "muted")

    # ---------- 交互 ----------
    def _show_ad_help(self):
        msg = (
            "【本工具已内置 AD 库导出】\n"
            "  勾选\"AD库 (SchLib/PcbLib)\"即可对每个编号直接生成：\n"
            "  · {编号}_{型号}.SchLib  —— 原理图符号库（AD 原生二进制）\n"
            "  · {编号}_{封装}.PcbLib  —— PCB 封装库（AD 原生二进制）\n"
            "  使用方法（二选一）：\n"
            "   ① AD 中直接 File → Open 打开该 .SchLib/.PcbLib\n"
            "   ② 放入库面板长期使用: Components 面板 → 菜单\n"
            "      \"File-based Libraries Preferences\" → Add Library\n"
            "  说明: 勾选\"AD库内嵌3D模型\"（默认开启）时，官方 3D STEP 会按\n"
            "  官方放置参数内嵌进 PcbLib —— AD 中打开 PcbLib 按快捷键 3\n"
            "  即可查看 3D 立体效果。\n"
            "\n"
            "【备选渠道】\n"
            "  · LCSC3D 开源工具: 可把多个器件合并为一个库并内嵌 3D\n"
            "    github.com/Travelerrrrrr/LCSC3D\n"
            "  · 立创EDA 官方导出: 文件 → 导出 → Altium Designer\n"
        )
        messagebox.showinfo("AD 导出指引", msg)

    def _import_file(self):
        cur = self.outdir_var.get().strip()
        init = cur if os.path.isdir(cur) else BASE_DIR
        path = filedialog.askopenfilename(
            title="选择编号列表文件", initialdir=init,
            filetypes=[("文本文件", "*.txt"), ("所有文件", "*.*")])
        if not path:
            return
        try:
            with open(path, encoding="utf-8-sig") as f:
                content = f.read()
        except UnicodeDecodeError:
            try:
                with open(path, encoding="gbk", errors="replace") as f:
                    content = f.read()
            except OSError as e:
                messagebox.showerror("读取失败", str(e))
                return
        except OSError as e:
            messagebox.showerror("读取失败", str(e))
            return
        self.txt_codes.delete("1.0", "end")
        self.txt_codes.insert("1.0", content)
        n = len(parse_codes(content))
        self._append(f"已导入 {os.path.basename(path)}，识别到 {n} 个编号。\n", "head")
        self._set_status(f"{n} 个编号")

    def _choose_dir(self):
        cur = self.outdir_var.get().strip()
        init = cur if os.path.isdir(cur) else BASE_DIR
        path = filedialog.askdirectory(title="选择保存路径", initialdir=init)
        if path:
            self.outdir_var.set(os.path.normpath(path))

    def _open_outdir(self):
        d = self.outdir_var.get().strip() or os.path.join(BASE_DIR, "step")
        try:
            os.makedirs(d, exist_ok=True)
            os.startfile(d)  # noqa: S606
        except Exception as e:  # noqa: BLE001
            messagebox.showerror("打开失败", str(e))

    def _set_status(self, text):
        self.lbl_status.config(text=text)

    def _append(self, text, tag="info"):
        self.txt_log.configure(state="normal")
        self.txt_log.insert("end", text, tag)
        self.txt_log.see("end")
        self.txt_log.configure(state="disabled")

    def _set_running(self, running):
        self.running = running
        self.btn_start.config(state="disabled" if running else "normal",
                              text="下载中…" if running else "开始下载")

    # ---------- 调度 ----------
    def _start(self):
        if self.running:
            return
        codes = parse_codes(self.txt_codes.get("1.0", "end"))
        if not codes:
            messagebox.showwarning("提示", "请输入至少一个立创编号，如 C131443\n（可从立创商城商品页获取）")
            return
        opts = {"3d": self.v_3d.get(), "symbol": self.v_sym.get(),
                "footprint": self.v_fp.get(), "ad": self.v_ad.get(),
                "ad_embed": self.v_ad_embed.get()}
        if not any(opts.values()):
            messagebox.showwarning("提示", "请至少勾选一项下载内容（3D模型 / 原理图符号 / PCB封装 / AD库）")
            return
        outdir = self.outdir_var.get().strip() or os.path.join(BASE_DIR, "step")
        try:
            os.makedirs(outdir, exist_ok=True)
        except OSError as e:
            messagebox.showerror("路径不可用", f"无法创建保存路径：\n{outdir}\n\n{e}")
            return
        self._set_running(True)
        self.pbar["value"] = 0
        self._append(f"\n====== 开始下载 {len(codes)} 个编号 -> {outdir} ======\n", "head")
        threading.Thread(target=self._worker,
                         args=(codes, outdir, not self.v_skip.get(), opts, self.v_verify.get()),
                         daemon=True).start()

    def _worker(self, codes, outdir, force, opts, do_verify):
        q = self.q
        stats = {"ok": 0, "skip": 0, "fail": 0}
        n_code_ok = n_code_partial = n_code_fail = 0
        failed, suspicious = [], []
        t0 = time.time()

        def log(msg, tag="info"):
            q.put(("log", (msg + "\n", tag)))

        for i, code in enumerate(codes, 1):
            log(f"[{i}/{len(codes)}] {code} ...")
            results = []

            # --- 3D 模型 ---
            if opts["3d"]:
                try:
                    status, info, model = fetch_3d(code, outdir, DEFAULT_DELAY, force, log=log)
                except Exception as e:  # noqa: BLE001
                    status, info, model = "fail", f"网络异常(已重试): {type(e).__name__}", ""
                if status == "ok":
                    detail = ""
                    suspect = False
                    if do_verify:
                        suspect, dims, vinfo = verify_step(info)
                        detail = f"  [{dims} · {vinfo}]"
                        if suspect:
                            detail += "  !! 疑似含PCB/异常，建议用CAD打开检查"
                            suspicious.append(info)
                    size_mb = os.path.getsize(info) / 1048576
                    log(f"    √ 3D模型: {os.path.basename(info)}  ({size_mb:.2f} MB){detail}",
                        "warn" if suspect else "ok")
                    results.append(("3D", "ok", info))
                elif status == "skip":
                    log(f"    - 3D模型已存在，跳过: {os.path.basename(info)}")
                    results.append(("3D", "skip", info))
                else:
                    log(f"    × 3D模型失败: {info}   (型号: {model})", "err")
                    results.append(("3D", "fail", f"{info}"))
                    failed.append((code, "3D模型", info))

            # --- 符号 + 封装 (+ AD 库) ---
            if opts["symbol"] or opts["footprint"] or opts.get("ad"):
                try:
                    s_status, s_data = fetch_std_data(code, log=log)
                except Exception as e:  # noqa: BLE001
                    s_status, s_data = "fail", f"网络异常(已重试): {type(e).__name__}"
                if s_status != "ok":
                    if opts["symbol"]:
                        log(f"    × 原理图符号失败: {s_data}", "err")
                        results.append(("符号", "fail", s_data))
                        failed.append((code, "原理图符号", str(s_data)))
                    if opts["footprint"]:
                        log(f"    × PCB封装失败: {s_data}", "err")
                        results.append(("封装", "fail", s_data))
                        failed.append((code, "PCB封装", str(s_data)))
                    if opts.get("ad"):
                        log(f"    × AD库失败: {s_data}", "err")
                        results.append(("AD库", "fail", s_data))
                        failed.append((code, "AD库", str(s_data)))
                else:
                    if opts["symbol"]:
                        sym = s_data.get("symbol")
                        if not sym:
                            log("    × 原理图符号失败: 该元件无符号数据", "err")
                            results.append(("符号", "fail", "无符号数据"))
                            failed.append((code, "原理图符号", "无符号数据"))
                        else:
                            fpath = os.path.join(outdir, f"{code}_{safe_name(sym['title'])}.symbol.json")
                            if os.path.exists(fpath) and not force:
                                log(f"    - 符号已存在，跳过: {os.path.basename(fpath)}")
                                results.append(("符号", "skip", fpath))
                            else:
                                save_json_doc(sym, fpath)
                                log(f"    √ 原理图符号: {os.path.basename(fpath)}  [{sym['elements']}个图元]", "ok")
                                results.append(("符号", "ok", fpath))
                    if opts["footprint"]:
                        fp = s_data.get("footprint")
                        if not fp:
                            log("    × PCB封装失败: 该元件无封装数据", "err")
                            results.append(("封装", "fail", "无封装数据"))
                            failed.append((code, "PCB封装", "无封装数据"))
                        else:
                            fpath = os.path.join(outdir, f"{code}_{safe_name(fp['title'])}.footprint.json")
                            if os.path.exists(fpath) and not force:
                                log(f"    - 封装已存在，跳过: {os.path.basename(fpath)}")
                                results.append(("封装", "skip", fpath))
                            else:
                                save_json_doc(fp, fpath)
                                log(f"    √ PCB封装: {os.path.basename(fpath)}  "
                                    f"[{fp['elements']}个图元 / {fp['pads']}个焊盘]", "ok")
                                results.append(("封装", "ok", fpath))
                    if opts.get("ad"):
                        if ad_export is None:
                            log("    × AD库失败: 内置转换模块不可用", "err")
                            results.append(("AD库", "fail", "模块不可用"))
                            failed.append((code, "AD库", "模块不可用"))
                        else:
                            try:
                                ad = ad_export.export_altium(
                                    s_data.get("raw") or {}, code, outdir,
                                    skip_existing=not force,
                                    embed_model=opts.get("ad_embed", False),
                                    fetch=lambda url: http_get_bytes(url, log),
                                    log=log)
                            except Exception as e:  # noqa: BLE001
                                log(f"    × AD库失败: {e}", "err")
                                results.append(("AD库", "fail", str(e)))
                                failed.append((code, "AD库", str(e)))
                            else:
                                if ad["status"] == "skip":
                                    log(f"    - AD库已存在，跳过: {os.path.basename(ad['schlib'])}")
                                    results.append(("AD库", "skip", ad["schlib"]))
                                else:
                                    log(f"    √ AD库: {os.path.basename(ad['schlib'])} + "
                                        f"{os.path.basename(ad['pcblib'])}  "
                                        f"[SchLib {ad['schlib_size'] / 1024:.0f}KB / "
                                        f"PcbLib {ad['pcblib_size'] / 1024:.0f}KB"
                                        + ("，含内嵌3D" if ad.get("embedded") else "")
                                        + "]", "ok")
                                    results.append(("AD库", "ok", ad["schlib"]))

            n_fail = sum(1 for _, s, _ in results if s == "fail")
            n_ok = sum(1 for _, s, _ in results if s == "ok")
            n_skip = sum(1 for _, s, _ in results if s == "skip")
            stats["ok"] += n_ok
            stats["skip"] += n_skip
            stats["fail"] += n_fail
            if n_fail == 0:
                n_code_ok += 1
            elif n_fail == len(results) and n_ok == 0 and n_skip == 0:
                n_code_fail += 1
            else:
                n_code_partial += 1

            q.put(("progress", (i, len(codes))))
            time.sleep(0.5)

        q.put(("done", {
            "stats": stats, "code_ok": n_code_ok, "code_partial": n_code_partial,
            "code_fail": n_code_fail, "failed": failed, "suspicious": suspicious,
            "elapsed": time.time() - t0, "outdir": outdir,
        }))

    def _poll_queue(self):
        try:
            while True:
                kind, payload = self.q.get_nowait()
                if kind == "log":
                    text, tag = payload
                    self._append(text, tag)
                elif kind == "progress":
                    done, total = payload
                    self.pbar["maximum"] = total
                    self.pbar["value"] = done
                    self._set_status(f"{done}/{total}")
                elif kind == "done":
                    self._finish(payload)
        except queue.Empty:
            pass
        self.root.after(100, self._poll_queue)

    def _finish(self, res):
        st = res["stats"]
        self._set_running(False)
        self._set_status(f"完成 {res['code_ok']} 个")
        self._append(
            f"\n====== 完成: 编号 {res['code_ok']} 个成功"
            + (f" / {res['code_partial']} 个部分失败" if res["code_partial"] else "")
            + (f" / {res['code_fail']} 个失败" if res["code_fail"] else "")
            + f" | 文件 {st['ok']} 成功 / {st['skip']} 跳过 / {st['fail']} 失败"
            f" | 用时 {res['elapsed']:.0f}s ======\n", "head")
        self._append(f"输出目录: {res['outdir']}\n", "info")
        if res["failed"]:
            self._append("失败清单:\n", "err")
            for code, kind, reason in res["failed"]:
                self._append(f"  {code} {kind}: {reason}\n", "err")
        if res["suspicious"]:
            self._append("注意: 以下 3D 文件存在疑似特征，建议用CAD打开确认:\n", "warn")
            for s in res["suspicious"]:
                self._append("  " + s + "\n", "warn")
        elif st["ok"] and self.v_verify.get():
            self._append("✓ 3D模型均未发现PCB特征(关键词+实体尺寸检查通过)\n", "ok")
        summary = (f"编号成功 {res['code_ok']} 个"
                   + (f"，部分失败 {res['code_partial']} 个" if res["code_partial"] else "")
                   + (f"，失败 {res['code_fail']} 个" if res["code_fail"] else "")
                   + f"\n文件：成功 {st['ok']}，跳过 {st['skip']}，失败 {st['fail']}"
                   + f"\n输出目录：{res['outdir']}")
        if res["code_fail"] + res["code_partial"] > 0 and st["ok"] + st["skip"] == 0:
            messagebox.showwarning("下载完成（有失败）", summary)
        else:
            messagebox.showinfo("下载完成", summary)

    def on_close(self):
        if self.running:
            if not messagebox.askyesno("退出", "下载任务正在进行，确定要退出吗？"):
                return
        self.root.destroy()


# ---------------- 入口 ----------------
def run_gui():
    enable_dpi_awareness()
    root = tk.Tk()
    install_excepthook(root)
    app = DownloaderApp(root)
    root.protocol("WM_DELETE_WINDOW", app.on_close)
    root.mainloop()


def run_selftest(argv):
    """打包后自测: 下载 3D+符号+封装+AD库 并写结果文件, 不启动GUI"""
    code = "C131443"
    for a in argv:
        c = normalize_code(a)
        if c:
            code = c
            break
    outdir = os.path.join(BASE_DIR, "selftest_out")
    os.makedirs(outdir, exist_ok=True)
    lines = []

    def log(msg, tag="info"):
        lines.append(str(msg))

    checks = {}
    # 3D
    try:
        status, info, model = fetch_3d(code, outdir, 1.0, True, log=log)
        lines.append(f"3D status={status}")
        if status == "ok":
            suspect, dims, vinfo = verify_step(info)
            lines.append(f"3D file={info}")
            lines.append(f"3D size={os.path.getsize(info)}")
            lines.append(f"3D suspect={suspect} dims={dims} info={vinfo}")
            checks["3d"] = not suspect
        else:
            lines.append(f"3D info={info} model={model}")
            checks["3d"] = False
    except Exception as e:  # noqa: BLE001
        lines.append("3D EXCEPTION: " + repr(e))
        checks["3d"] = False

    # 符号 + 封装
    s_status, s_data = "fail", None
    try:
        s_status, s_data = fetch_std_data(code, log=log)
        lines.append(f"STD status={s_status}")
        if s_status == "ok":
            sym = s_data.get("symbol")
            fp = s_data.get("footprint")
            if sym:
                fpath = os.path.join(outdir, f"{code}_{safe_name(sym['title'])}.symbol.json")
                save_json_doc(sym, fpath)
                lines.append(f"symbol file={fpath} elements={sym['elements']}")
                checks["symbol"] = sym["elements"] > 0
            else:
                checks["symbol"] = False
            if fp:
                fpath = os.path.join(outdir, f"{code}_{safe_name(fp['title'])}.footprint.json")
                save_json_doc(fp, fpath)
                lines.append(f"footprint file={fpath} elements={fp['elements']} pads={fp['pads']}")
                checks["footprint"] = fp["pads"] >= 0 and fp["elements"] > 0
            else:
                checks["footprint"] = False
        else:
            lines.append(f"STD info={s_data}")
            checks["symbol"] = checks["footprint"] = False
    except Exception as e:  # noqa: BLE001
        lines.append("STD EXCEPTION: " + repr(e))
        checks["symbol"] = checks["footprint"] = False

    # AD 库 (SchLib + PcbLib, 内嵌3D)
    try:
        if ad_export is None:
            raise RuntimeError("ad_export 模块不可用")
        r = ad_export.export_altium((s_data or {}).get("raw") or {}, code, outdir,
                                    skip_existing=False, embed_model=True,
                                    fetch=lambda url: http_get_bytes(url, log),
                                    log=log)
        magic = open(r["schlib"], "rb").read(4)
        pcb_raw = open(r["pcblib"], "rb").read()
        lines.append(f"AD schlib={r['schlib']} size={r['schlib_size']}")
        lines.append(f"AD pcblib={r['pcblib']} size={r['pcblib_size']} embedded={r['embedded']}")
        lines.append(f"AD model_diag={r['model_diagnostics']}")
        checks["ad"] = (r["status"] == "ok" and r["schlib_size"] > 0
                        and r["pcblib_size"] > 0 and magic == b"\xd0\xcf\x11\xe0")
        checks["ad3d"] = bool(r["embedded"]) and b"|EMBED=TRUE" in pcb_raw
    except Exception as e:  # noqa: BLE001
        lines.append("AD EXCEPTION: " + repr(e))
        checks["ad"] = False
        checks["ad3d"] = False

    ok = all(checks.values())
    lines.append("checks=" + json.dumps(checks, ensure_ascii=False))
    lines.append("RESULT: " + ("PASS" if ok else "FAIL"))
    with open(os.path.join(BASE_DIR, "selftest_result.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    sys.exit(0 if ok else 1)


def main():
    argv = sys.argv[1:]
    if "--selftest" in argv:
        run_selftest(argv)
        return
    if not TK_AVAILABLE:
        sys.exit("缺少 tkinter 图形库，无法启动界面")
    run_gui()


if __name__ == "__main__":
    main()
