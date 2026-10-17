"""CSDN 文章发布脚本（内部 API 方式）。

用法:
    1. 浏览器登录 CSDN
    2. 打开 https://editor.csdn.net/md/?not_checkout=1
    3. F12 → Network → 保存一次草稿 → 找到 saveArticle 请求
    4. 从请求头复制 Cookie 和 x-ca-key，填入下方 CONFIG
    5. python docs/publish_csdn.py

依赖: 仅标准库
"""
import base64
import hashlib
import hmac
import json
import os
import ssl
import sys
import time
import urllib.request
import uuid

# ==================== 配置区 ====================
COOKIE = ""          # 从浏览器复制的完整 Cookie 字符串
X_CA_KEY = ""        # 请求头里的 x-ca-key
API_KEY = "203803574"  # CSDN 阿里云网关默认 key（通常固定）
BASE = os.path.dirname(os.path.abspath(__file__))
# ================================================

SAVE_URL = "https://bizapi.csdn.net/blog-console-api/v1/postedit/saveArticle"
CTX = ssl.create_default_context()


def sign(path, body, api_key, secret=None):
    """生成 x-ca-signature（阿里云网关 HMAC-SHA256）。"""
    nonce = str(uuid.uuid4())
    content = json.dumps(body, ensure_ascii=False).encode("utf-8")
    md5 = hashlib.md5(content).hexdigest()
    # 签名串: POST\n*/*\n\napplication/json\n\nmd5\nx-ca-key:KEY\nx-ca-nonce:NONCE\n\npath
    string_to_sign = (
        f"POST\n*/*\n\napplication/json\n\n{md5}\n"
        f"x-ca-key:{api_key}\nx-ca-nonce:{nonce}\n\n{path}"
    )
    if secret:
        sig = base64.b64encode(
            hmac.new(secret.encode(), string_to_sign.encode(), hashlib.sha256).digest()
        ).decode()
    else:
        # 无密钥时用空密钥（部分内部接口接受）
        sig = base64.b64encode(
            hmac.new(b"", string_to_sign.encode(), hashlib.sha256).digest()
        ).decode()
    return nonce, sig, md5


def publish(title, markdown, tags, description, article_type="original",
            pub_status="publish", creation_statement="0"):
    """发布文章，返回 (ok, url_or_error)。"""
    if not COOKIE or not X_CA_KEY:
        return False, "请先在配置区填入 COOKIE 和 X_CA_KEY"

    # Markdown -> CSDN 兼容 HTML
    html = markdown_to_html(markdown)

    body = {
        "title": title,
        "content": html,
        "markdowncontent": markdown,
        "pubStatus": pub_status,
        "readType": "public",
        "type": article_type,
        "tags": ",".join(tags[:5]),
        "categories": ["硬件"],
        "description": description[:256],
        "creation_statement": creation_statement,
        "status": 0,
        "authorized_status": False,
        "is_new": 1,
        "source": "pc_mdeditor",
        "cover_type": 1,
    }

    path = "/blog-console-api/v1/postedit/saveArticle"
    nonce, sig, md5 = sign(path, body, X_CA_KEY)
    headers = {
        "Cookie": COOKIE,
        "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                       "AppleWebKit/537.36 (KHTML, like Gecko) "
                       "Chrome/120.0.0.0 Safari/537.36"),
        "Accept": "*/*",
        "Accept-Language": "zh-CN,zh;q=0.9",
        "Content-Type": "application/json;charset=UTF-8",
        "Origin": "https://editor.csdn.net",
        "Referer": "https://editor.csdn.net/md/",
        "x-ca-key": X_CA_KEY,
        "x-ca-nonce": nonce,
        "x-ca-signature": sig,
        "x-ca-signature-headers": "x-ca-key,x-ca-nonce",
        "x-ca-stage": "PROD",
    }

    req = urllib.request.Request(
        f"https://bizapi.csdn.net{path}",
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=60, context=CTX) as r:
            result = json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        return False, f"HTTP {e.code}: {e.read().decode()[:300]}"
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"

    if result.get("code") == 200:
        return True, result.get("data", {}).get("url", "")
    return False, json.dumps(result, ensure_ascii=False)[:300]


def markdown_to_html(md):
    """简易 Markdown -> HTML（够用即可，保留代码块/表格/标题）。"""
    import re
    out, in_code, code = [], False, []

    def inline(t):
        t = re.sub(r"`([^`]+)`", r'<code>\1</code>', t)
        t = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", t)
        t = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', t)
        return t

    for line in md.split("\n"):
        if line.startswith("```"):
            if in_code:
                out.append("<pre><code>" + "\n".join(code) + "</code></pre>")
                code, in_code = [], False
            else:
                in_code = True
            continue
        if in_code:
            code.append(line)
            continue
        s = line.strip()
        if not s:
            continue
        m = re.match(r"^(#{1,6})\s+(.*)", s)
        if m:
            lv = min(len(m.group(1)), 6)
            out.append(f"<h{lv}>{inline(m.group(2))}</h{lv}>")
        elif s.startswith(("- ", "* ")):
            out.append(f"<li>{inline(s[2:])}</li>")
        elif re.match(r"^\d+\.\s+", s):
            out.append(f"<li>{inline(re.sub(r'^\d+\.\s+', '', s))}</li>")
        elif s.startswith("|"):
            out.append(f"<p>{inline(s)}</p>")
        elif s.startswith(">"):
            out.append(f"<blockquote>{inline(s.lstrip('> '))}</blockquote>")
        elif s == "---":
            out.append("<hr>")
        else:
            out.append(f"<p>{inline(s)}</p>")
    return "\n".join(out)


def main():
    if not COOKIE or not X_CA_KEY:
        print(__doc__)
        print("=" * 60)
        print("当前状态: 未配置 Cookie / x-ca-key")
        print("请按上方步骤从浏览器 F12 复制后填入配置区。")
        print()
        print("如果你不想折腾，直接用手动方式也很快:")
        print("  1. 打开 docs/csdn-blog.html 全选复制")
        print("  2. 粘贴到 https://editor.csdn.net/md/?not_checkout=1")
        print("  3. 上传 docs/csdn-image-1-ui.png 和 csdn-image-2-merge.png")
        print("  4. 点发布（3 分钟搞定）")
        return 2

    md_path = os.path.join(BASE, "csdn-blog.md")
    with open(md_path, encoding="utf-8") as f:
        md = f.read()

    title = "立创商城元件库批量下载工具：3D模型/原理图符号/PCB封装/AD原生库一键生成（含3D内嵌）"
    desc = ("做硬件开发时，元件的3D模型、原理图符号、PCB封装、AD库都要从立创商城手动下载。"
            "本文介绍一个开源小工具：输入立创编号，一键批量下载4类数据，"
            "直接生成AD原生SchLib/PcbLib并内嵌3D模型，还能把几十个器件合并成一个库文件。")
    tags = ["立创", "AltiumDesigner", "PCB", "开源", "Python"]

    print("正在发布到 CSDN ...")
    ok, result = publish(title, md, tags, desc)
    if ok:
        print(f"✓ 发布成功: {result}")
    else:
        print(f"✗ 发布失败: {result}")
        print("\n常见原因:")
        print("  - Cookie 过期 -> 重新复制")
        print("  - 签名算法需匹配该接口版本 -> 需从实际请求头抓取 x-ca-* 参数")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
