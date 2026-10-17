"""把 docs/csdn-blog.md 转成 CSDN 可直接粘贴的 HTML。

CSDN 的 Markdown 编辑器粘贴 HTML 时会保留内联样式，因此这里生成
带内联样式的 HTML；图片位置用醒目标记占位，上传后替换即可。

用法: python docs/make_csdn_html.py
输出: docs/csdn-blog.html
"""
import html
import os
import re

BASE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(BASE, "csdn-blog.md")
DST = os.path.join(BASE, "csdn-blog.html")

# ---------- 内联样式（CSDN 粘贴后可保留） ----------
STYLE = {
    "h1": "font-size:26px;font-weight:700;color:#2b2b2b;margin:28px 0 16px;padding-bottom:10px;border-bottom:2px solid #e8e8e8;line-height:1.4;",
    "h2": "font-size:21px;font-weight:700;color:#1f1f1f;margin:30px 0 14px;padding-left:11px;border-left:5px solid #409eff;line-height:1.4;",
    "h3": "font-size:17px;font-weight:700;color:#333;margin:24px 0 12px;line-height:1.5;",
    "p": "font-size:15px;color:#3b3b3b;line-height:1.85;margin:14px 0;",
    "li": "font-size:15px;color:#3b3b3b;line-height:1.85;margin:7px 0;",
    "code": "font-family:Consolas,Monaco,monospace;font-size:13.5px;background:#f6f8fa;color:#c7254e;padding:2px 6px;border-radius:4px;",
    "pre": "background:#282c34;color:#abb2bf;padding:16px 18px;border-radius:6px;overflow-x:auto;font-size:13px;line-height:1.6;",
    "blockquote": "border-left:4px solid #dfe2e5;background:#fafafa;color:#6a737d;padding:12px 18px;margin:18px 0;font-size:14.5px;line-height:1.8;border-radius:0 4px 4px 0;",
    "table": "border-collapse:collapse;width:100%;margin:18px 0;font-size:14px;display:block;overflow-x:auto;",
    "th": "border:1px solid #dfe2e5;background:#f6f8fa;padding:9px 13px;text-align:left;font-weight:600;color:#24292e;",
    "td": "border:1px solid #dfe2e5;padding:9px 13px;color:#3b3b3b;",
    "img": "max-width:100%;border-radius:6px;box-shadow:0 2px 12px rgba(0,0,0,.10);margin:18px auto;display:block;",
    "a": "color:#409eff;text-decoration:none;",
    "strong": "font-weight:700;color:#1f1f1f;",
}


def inline(text):
    """处理行内 markdown: 代码/粗体/链接。"""
    text = html.escape(text)
    # 行内代码
    text = re.sub(r"`([^`]+)`",
                  lambda m: f'<code style="{STYLE["code"]}">{m.group(1)}</code>', text)
    # 粗体
    text = re.sub(r"\*\*([^*]+)\*\*",
                  lambda m: f'<strong style="{STYLE["strong"]}">{m.group(1)}</strong>', text)
    # 链接
    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)",
                  lambda m: f'<a href="{m.group(2)}" style="{STYLE["a"]}">{m.group(1)}</a>', text)
    return text


def convert(md):
    out, i = [], 0
    lines = md.split("\n")
    in_code = False
    code_buf = []
    while i < len(lines):
        line = lines[i]

        # 代码块
        if line.startswith("```"):
            if in_code:
                out.append(f'<pre style="{STYLE["pre"]}"><code>{html.escape(chr(10).join(code_buf))}</code></pre>')
                code_buf, in_code = [], False
            else:
                in_code = True
            i += 1
            continue
        if in_code:
            code_buf.append(line)
            i += 1
            continue

        stripped = line.strip()

        # 空行
        if not stripped:
            i += 1
            continue

        # 图片
        m = re.match(r"^!\[(.*?)\]\((.*?)\)$", stripped)
        if m:
            alt, src = m.group(1), m.group(2)
            if any(k in alt or k in src for k in ("上传图片", "替换", "占位")):
                out.append(
                    f'<p style="text-align:center;color:#c0392b;background:#fff3cd;'
                    f'border:2px dashed #e0a800;padding:16px;border-radius:6px;'
                    f'font-size:14px;font-weight:600;">'
                    f'📷 【在此处上传图片】{html.escape(alt)}<br>'
                    f'<span style="font-weight:400;font-size:13px;color:#7d6608;">'
                    f'本地文件: {html.escape(src)}</span></p>')
            else:
                out.append(f'<img src="{html.escape(src)}" alt="{html.escape(alt)}" style="{STYLE["img"]}">')
            i += 1
            continue

        # 标题
        m = re.match(r"^(#{1,6})\s+(.*)$", stripped)
        if m:
            level, text = min(len(m.group(1)), 3), m.group(2)
            out.append(f'<h{level} style="{STYLE[f"h{level}"]}">{inline(text)}</h{level}>')
            i += 1
            continue

        # 水平线
        if stripped in ("---", "***", "___"):
            out.append('<hr style="border:none;border-top:1px solid #e8e8e8;margin:28px 0;">')
            i += 1
            continue

        # 表格
        if stripped.startswith("|"):
            block = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                block.append(lines[i].strip())
                i += 1
            out.append(render_table(block))
            continue

        # 引用块
        if stripped.startswith(">"):
            block = []
            while i < len(lines) and (lines[i].strip().startswith(">") or not lines[i].strip()):
                block.append(lines[i].strip().lstrip(">").strip())
                i += 1
            inner = "<br>".join(inline(b) for b in block if b)
            out.append(f'<blockquote style="{STYLE["blockquote"]}">{inner}</blockquote>')
            continue

        # 有序列表
        if re.match(r"^\d+\.\s+", stripped):
            items = []
            while i < len(lines) and re.match(r"^\s*\d+\.\s+", lines[i]):
                items.append(re.sub(r"^\s*\d+\.\s+", "", lines[i]).strip())
                i += 1
            lis = "".join(
                f'<li style="{STYLE["li"]}">{inline(x)}</li>' for x in items)
            out.append(f'<ol style="padding-left:26px;margin:14px 0;">{lis}</ol>')
            continue

        # 无序列表
        if stripped.startswith(("- ", "* ", "+ ")):
            items = []
            while i < len(lines) and re.match(r"^\s*[-*+]\s+", lines[i]):
                items.append(re.sub(r"^\s*[-*+]\s+", "", lines[i]).strip())
                i += 1
            lis = "".join(
                f'<li style="{STYLE["li"]}">{inline(x)}</li>' for x in items)
            out.append(f'<ul style="padding-left:26px;margin:14px 0;">{lis}</ul>')
            continue

        # 段落
        out.append(f'<p style="{STYLE["p"]}">{inline(stripped)}</p>')
        i += 1

    return "\n".join(out)


def render_table(rows):
    cells = [[c.strip() for c in r.strip("|").split("|")] for r in rows]
    cells = [c for c in cells if not all(re.fullmatch(r":?-{2,}:?", x) for x in c)]
    if not cells:
        return ""
    head, *body = cells
    ths = "".join(f'<th style="{STYLE["th"]}">{inline(h)}</th>' for h in head)
    trs = "".join(
        "<tr>" + "".join(f'<td style="{STYLE["td"]}">{inline(c)}</td>' for c in row) + "</tr>"
        for row in body)
    return f'<table style="{STYLE["table"]}"><thead><tr>{ths}</tr></thead><tbody>{trs}</tbody></table>'


def main():
    with open(SRC, encoding="utf-8") as f:
        md = f.read()
    # 去掉开头的引用摘要（CSDN 有独立的摘要输入框）
    md = re.sub(r"^> \*\*摘要\*\*.*?(?=\n\n# )", "", md, flags=re.S)
    body = convert(md)
    doc = f"""<!--
  CSDN 发布用 HTML
  生成命令: python docs/make_csdn_html.py
  发布步骤:
    1. 登录 https://editor.csdn.net/md/?not_checkout=1 新建文章
    2. 标题: 立创商城元件库批量下载工具：3D模型/原理图符号/PCB封装/AD原生库一键生成（含3D内嵌）
    3. 摘要框: 粘贴下方"摘要"一节的内容
    4. 正文框: 全选本文件内容直接粘贴
    5. 上传图片后替换两处黄色占位块
    6. 分类选"硬件"，标签: 立创/Altium Designer/PCB/开源/Python
    7. 勾选"原创"后发布
-->
{body}
"""
    with open(DST, "w", encoding="utf-8") as f:
        f.write(doc)
    print(f"已生成: {DST}")
    print(f"大小: {os.path.getsize(DST) / 1024:.1f} KB")
    print(f"摘要开头: {md[:200]}")


if __name__ == "__main__":
    main()
