<!--
  ============================================================================
  CSDN 发布用正文(Markdown 模式)
  ---------------------------------------------------------------------------
  使用方法:
    1. 本文件全选复制(注意: 不要复制上面这段注释)
    2. 粘贴到 CSDN 编辑器正文区
    3. 找到两处「⬇⬇⬇ 图片 N」标记, 删掉标记文字, 用工具栏「插入→图片」上传对应图片
    4. 右侧「提取摘要」可自动生成摘要
    5. 设置分类/标签, 点「发布文章」
  ============================================================================
-->

# 立创商城元件库批量下载工具：3D模型/原理图符号/PCB封装/AD原生库一键生成（含3D内嵌）

**一个免安装小工具，输入立创编号，一次拿到 4 类文件，还能直接生成 Altium Designer 原生库。**

**⬇⬇⬇ 图片 1：删除这行文字，然后点工具栏「插入 → 图片」上传 `csdn-image-1-ui.png`（主界面截图）⬇⬇⬇**

---

## 目录

- [一、痛点：画板子人的日常](#一痛点画板子人的日常)
- [二、工具能做什么](#二工具能做什么)
- [三、安装使用](#三安装使用)
- [四、技术拆解（硬核部分）](#四技术拆解硬核部分)
  - [4.1 数据从哪来：立创 API 逆向](#41-数据从哪来立创-api-逆向)
  - [4.2 风控对抗](#42-风控对抗)
  - [4.3 如何保证 3D 模型"不含 PCB"](#43-如何保证-3d-模型不含-pcb)
  - [4.4 最硬的一块：AD 原生二进制库](#44-最硬的一块ad-原生二进制库)
  - [4.5 把 3D 模型内嵌进 PcbLib](#45-把-3d-模型内嵌进-pcblib)
  - [4.6 多库合并](#46-多库合并)
- [五、验证：怎么证明"真的能用"](#五验证怎么证明真的能用)
- [六、开源与许可](#六开源与许可)

---

## 一、痛点：画板子人的日常

硬件工程师的日常里有这么一件事：**在立创商城选完元件后，还要把它们的资料搬进自己的 EDA 环境。**

具体来说，一个器件通常需要 4 样东西：

| 需要的东西 | 用途 | 立创的获取方式 | 痛点 |
|---|---|---|---|
| 3D 模型（STEP） | 装配检查、结构干涉验证 | 立创EDA 专业版逐个导出 | 要开专业版、点导出 |
| 原理图符号 | 画原理图 | 立创EDA 专业版导出 | 同上 |
| PCB 封装 | 画 PCB | 立创EDA 专业版导出 | 同上 |
| AD 库（SchLib/PcbLib） | 给 Altium Designer 用 | 官方导出→AD 提取库文件 | **流程最长** |

其中有两个特别真实的坑：

**坑一：下载到的 3D 模型带着一整块 PCB 基板。**
很多人不知道，立创EDA **PCB 编辑器**里的"导出 3D"会把当前 PCB 板子一起导出，得到的是"元件 + 板子"的模型，而不是纯元件模型。想要纯元件，得走**元件库**路径。

**坑二：批量处理靠手点。**
一个项目用到几十上百个器件，逐个搜索、逐个导出、逐个保存……机械劳动且容易漏。

于是我做了这个工具：**输入编号 → 四类文件一次到位 → 打包成双击即用的 exe**。

---

## 二、工具能做什么

| 功能 | 说明 |
|---|---|
| 🔢 批量下载 | 粘贴多个编号 / 导入 `codes.txt` / 命令行参数，自动去重、跳过注释 |
| 📦 3D 模型 | **纯元器件 STEP**（不含 PCB 基板），并自动做几何校验 |
| 📐 原理图符号 | 立创EDA 标准格式 JSON，可直接导入立创EDA |
| 🧩 PCB 封装 | 立创EDA 标准格式 JSON，含焊盘/丝印/阻焊层 |
| 🅰️ **AD 原生库** | 直接生成 `.SchLib` / `.PcbLib`（**AD 原生二进制格式**），可选内嵌 3D 模型 |
| 🔗 库合并 | 多器件一键合并为单个 SchLib + PcbLib，**相同封装自动去重** |
| 🛠 手动合并 | 已有多个 `.SchLib`/`.PcbLib` 可手动合并成一个（不同来源的库也能合） |
| 🛡 风控对抗 | 请求间隔控制 + 指数退避重试，被断连自动恢复 |
| 📌 断点续传 | 已下载文件自动跳过，支持 `--force` 重下 |
| 🖥️ 免安装 | 单文件 exe，目标电脑**无需装 Python** |

### 亮点一：3D 模型直接内嵌进 AD 封装库

生成的 `PcbLib` 里**内嵌了官方 3D STEP 模型**（zlib 压缩存储），在 Altium Designer 里打开封装库按快捷键 `3`，就能直接看到立体模型——不需要手工挂载 3D 文件。

> 内嵌的模型与官方源文件**逐字节一致**（已通过解压比对验证）。

### 亮点二：几十个器件合并成一个库

批量下载时不再产生几十个 `.SchLib`/`.PcbLib`，而是合并为：

```
LCSC3D.SchLib    # 一个文件，含全部符号
LCSC3D.PcbLib    # 一个文件，含全部封装（相同封装自动去重）
```

比如 20 个不同的 0603 电阻，只保留 1 个 `R0603` 封装条目，符号自动引用它。

---

## 三、安装使用

### 3.1 下载 exe（推荐）

从项目 Releases 下载 `立创3D封装下载器.exe`，双击运行，**不需要装任何环境**。

**⬇⬇⬇ 图片 2：删除这行文字，然后点工具栏「插入 → 图片」上传 `csdn-image-2-merge.png`（合并对话框截图）⬇⬇⬇**

> 💡 **发布提示**：本文有两处图片，发布前需上传到 CSDN 获得图片链接——
> 图片1：`docs/screenshots/ui.png`（主界面）
> 图片2：`docs/screenshots/merge_dialog.png`（合并对话框）
> 上传后把 Markdown 中的占位提示替换成 CSDN 生成的图片 URL。

### 3.2 使用步骤

1. 在文本框粘贴立创编号（如 `C131443`，一行一个）；
2. 选择保存路径（默认 exe 同级 `step\` 目录）；
3. 勾选需要的内容（四类默认全选，AD 库默认内嵌 3D）；
4. 点击 **开始下载**。

### 3.3 命令行版

```bash
# 全量下载（3D + 符号 + 封装 + AD库）
python lcsc_3d_downloader.py C131443 C25804 C14663

# 从文件读编号
python lcsc_3d_downloader.py -f codes.txt -o D:\step

# 只生成 AD 库（默认内嵌 3D；加 --no-ad-3d 关闭）
python lcsc_3d_downloader.py C131443 --types ad

# AD 库合并：所有器件合并为单个 LCSC3D.SchLib + LCSC3D.PcbLib
python lcsc_3d_downloader.py -f codes.txt --merge --types ad
```

### 3.4 输出示例

以 `C131443`（GD32F303RCT6，LQFP-64）为例：

```
C131443_LQFP-64(10x10).step                    12.6 MB   纯元件 3D 模型
C131443_GD32F303RCT6.symbol.json               14 KB     原理图符号(立创格式)
C131443_LQFP-64_..._LS12.0-BL.footprint.json   98 KB     PCB封装(立创格式)
C131443_GD32F303RCT6.SchLib                    31 KB     AD 符号库(64引脚)
C131443_LQFP-64_...-BL.PcbLib                  2.2 MB    AD 封装库(64焊盘+内嵌3D)
```

### 3.5 AD 库里怎么用

两种方式，二选一：

1. **直接打开**：AD 中 `File → Open` 打开 `.SchLib` / `.PcbLib`；
2. **长期使用**：放入库面板 —— `Components 面板 → 菜单 → File-based Libraries Preferences → Add Library`。

查看 3D：打开 `.PcbLib` 后按快捷键 `3`。

---

## 四、技术拆解（硬核部分）

这一节记录完整的技术实现过程，包括走过的弯路。

### 4.1 数据从哪来：立创 API 逆向

立创有两套 API，我用了两条链路。

**① 3D 模型（专业版链路）**

```python
# 按 C 编号搜索商品
POST https://pro.lceda.cn/api/eda/product/search
    keyword=C131443
    → result.productList[0].hasDevice

# 查器件属性，拿 3D 模型 UUID
POST https://pro.lceda.cn/api/devices/searchByIds
    uuids[]=<hasDevice>
    → attributes["3D Model"]

# 查 3D 模型资源标识
POST https://pro.lceda.cn/api/components/searchByIds?forceOnline=1
    → dataStr.model

# 下载 STEP 文本
GET https://modules.lceda.cn/qAxj6KHrDKw4blvCG8QJPs7Y/{model}
```

**② 符号/封装（标准版链路）**

```python
# 一个接口全都有
GET https://lceda.cn/api/products/{编号}/components

result.dataStr               # 原理图符号（明文 JSON）
result.packageDetail.dataStr # PCB 封装（明文 JSON）
```

标准版接口返回的是 EasyEDA 经典明文格式：`shape` 数组里是 `R~`（矩形）、`E~`（椭圆）、`PAD~`（焊盘）、`TRACK~`（走线）这类以 `~` 分隔的记录。

**一个有用的发现**：国际站 `easyeda.com` 在国内经常连不上，而**国内站 `lceda.cn` 直连可用**——所以符号/封装走标准版国内站，是更稳的方案。

### 4.2 风控对抗

立创的接口有风控，实测总结：

| 现象 | 应对 |
|---|---|
| 短时间连续请求被断连（`RemoteDisconnected`） | 请求间隔 ≥1 秒 + 指数退避重试 |
| `curl` 能过、裸 Python `urllib` 被断 | 补齐完整浏览器请求头 |
| 无 UA 的请求被 CDN 拦截 | 携带真实浏览器 `User-Agent` |

所谓"补齐请求头"，指的是把浏览器会发的头都带上：

```python
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) ...",
    "Accept": "*/*",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Origin": "https://lceda.cn",
    "Referer": "https://lceda.cn/editor",
    "Connection": "keep-alive",
}
```

这套策略在实测中稳定有效，几十个编号连着跑不会中断。

### 4.3 如何保证 3D 模型"不含 PCB"

要求很明确：模型必须是**纯元器件**。怎么自动验证？

**最初的错误做法**：解析 STEP 里所有坐标点，算包围盒。尺寸合理就通过。

**然后就翻车了**——以 0603 电容（C14663）为例，算出来包围盒宽 4mm，而 0603 本体只有 1.6mm。

排查发现：STEP 文件里，**倒圆角的圆弧，圆心被放在模型外很远处**（X=±2mm），但圆弧本身很小。用"所有坐标点"统计，圆心就把包围盒撑大了。

**正确做法**：只统计被 `EDGE_CURVE` 引用的 `VERTEX_POINT`（即实体真实的边端点）：

```python
# 收集真正被边引用的顶点
used_points = set()
for m in re.finditer(r"EDGE_CURVE\s*\(\s*'[^']*'\s*,\s*#(\d+)\s*,\s*#(\d+)", text):
    for vid in (m.group(1), m.group(2)):
        pm = re.match(r"VERTEX_POINT\s*\(\s*'[^']*'\s*,\s*#(\d+)", entity[vid])
        if pm:
            used_points.add(pm.group(1))
# 再用这些顶点算包围盒 → 得到实体真实尺寸
```

实测结果：

| 器件 | 顶点法尺寸 | 判定 |
|---|---|---|
| C131443 (LQFP-64) | 12.01 × 12.01 × 1.45 mm | ✓ 引脚跨距 12mm 吻合 |
| C25804 (0603) | 0.81 × 1.62 × 0.45 mm | ✓ |
| C14663 (0603) | 1.60 × 0.80 × 0.80 mm | ✓ |

> 另一个关键结论：**立创EDA 专业版"元件库"里的 3D 模型本身就是纯元件**，不含基板；含基板的是"PCB 编辑器导出 3D"那条路。走对数据源，问题解决一半。

### 4.4 最硬的一块：AD 原生二进制库

这是整个项目最难的部分。目标：生成 **Altium Designer 能直接打开的原生 `.SchLib` / `.PcbLib`**，而不是需要二次转换的中间格式。

#### 弯路：逆向官方导出引擎

用户提示"立创EDA 自己就能导出 AD 格式"，于是我顺着这条线挖了下去，而且挖得很深：

1. 找到立创官方导出 AD 时实际工作的转换引擎 **chameleon**（一个 5MB 扩展包，解开是 7.5MB 的 Node.js 程序）；
2. 发现它**能直接命令行运行**（`node convert-node-server.js --cmd conversion`），还带 HTTP 服务模式，支持 12 种输入格式 × 多种输出格式，其中就有 `altium`；
3. 摸清请求协议，成功把器件数据转成官方同款的 ASCII `.schdoc`/`.pcbdoc`；
4. **结果发现：纯文件转换走不到终点**。官方导出带着"编辑器上下文"（元件实例的放置信息），纯数据只能生成缺元件框架的"裸图元图纸"，在 AD 里提取不出完整的库。

能跑通 90% 却发现最后一步是死胡同——这就是逆向工程的日常。

#### 正路：站在开源项目肩膀上

转去找现成方案，找到了开源项目 **[LCSC3D](https://github.com/Travelerrrrrr/LCSC3D)**——有人已经用 Python 完整实现了"立创数据 → AD 原生二进制库"的转换链，并且逐字段对照过官方导出验证。

AD 库的文件结构是这样的（这也是最难的部分）：

```
PcbLib (OLE 复合文档)
├── FileHeader          # 版本标识
├── SectionKeys         # 封装名 → 存储名 索引
├── Library/Header      # 库头记录数
├── Library/Data        # Board 头记录 + 封装名列表
├── <封装名>/Header     # 该封装的图元数
├── <封装名>/Data       # 实际图元记录（二进制）
├── <封装名>/Parameters # 封装参数
└── Library/Models/*    # 内嵌 3D 模型（zlib 压缩 STEP）
```

其中图元记录的长度前缀、二进制字段布局、`mil` 到内部单位的换算，都要精确复刻。关键换算关系：

```python
# 立创 1 个坐标单位 = 10 mil = 100000 个 AD 内部单位
def to_ad_raw(value):
    return int(Decimal(str(value)) * 100000)
```

我把这个转换链**裁剪成精简版内置进工具**，核心模块十几个，纯 Python 标准库实现（复合文档写入用 Windows 自带的 `ole32`）。

**验证结果**（用独立解析器反向读取生成的文件）：

| 器件 | 符号库 | 封装库 |
|---|---|---|
| C131443 (LQFP-64) | **64 个引脚**（编号 1~64） | **64 个焊盘** + 206 个丝印图元 |
| C25804 (0603) | 2 引脚 | 2 焊盘 |
| C14663 (0603) | 2 引脚 | 2 焊盘 |

LQFP-64 的焊盘尺寸实测 0.30×1.5mm，与标准规格吻合。

### 4.5 把 3D 模型内嵌进 PcbLib

这是最有价值的功能：生成的 PcbLib **内嵌官方 3D STEP**，AD 里按 `3` 键直接看立体模型。

实现里有几个有意思的点：

**① 模型资源要成对下载**

封装数据里的 `SVGNODE` 记录藏着模型编号，用它能下载两个文件：

```python
# STEP（建模用，12MB）
GET https://modules.lceda.cn/qAxj6KHrDKw4blvCG8QJPs7Y/{uuid}
# OBJ（用作放置基准，5MB，6.5 万顶点）
GET https://modules.lceda.cn/3dmodel/{uuid}
```

**为什么要 OBJ？** 因为官方放置 3D 模型时，用的是 **OBJ 的几何基准**（X/Y 包围盒中心 + 最低 Z 点），**不是 STEP 自身的原点**。所以两个文件必须配对使用：下载 OBJ → 算出模型原点 → 结合旋转矩阵推导最终偏移。

```python
# 计算 OBJ 的放置基准（只需扫描 v 顶点行，不用解析面/材质）
def obj_origin(raw):
    low, high = [inf]*3, [-inf]*3
    for match in re.finditer(r'(?m)^[ \t]*v[ \t]+([^\r\n]*)', raw):
        point = tuple(float(v) for v in match[1].split()[:3])
        for i, v in enumerate(point):
            low[i], high[i] = min(low[i], v), max(high[i], v)
    return ((low[0]+high[0])/2, (low[1]+high[1])/2, low[2])  # 中心XY + 最低Z
```

**② 写入格式**

```python
# STEP 用 zlib 压缩后存入 AD 的 Models 流
compressed = zlib.compress(step_bytes)
streams['Library/Models/0'] = compressed
# 同时在封装里写一条 3D 主体记录（旋转角、高度偏移、校验和等 20+ 参数）
```

**③ 验证方式**

粗暴但有效：**把生成的 PcbLib 里的内嵌数据解压出来，和官方源 STEP 逐字节比对**。

```
STEP 源文件: 12610101 bytes | 内嵌解压: 12610101 bytes   ✓ 完全一致
```

### 4.6 多库合并

两种合并场景都支持：

**① 下载时合并**：勾选"AD库合并"，本批器件合并为一个库。构建顺序很讲究——**先建 PcbLib（封装去重），再用最终封装名建 SchLib**，这样符号里的 Footprint 引用才能指向去重后的正确封装名。

**② 手动合并已有库**：界面右上角"合并库…"，选多个 `.SchLib` 或多个 `.PcbLib` 合成一个。规则是**顺序即优先级**——完全重复/同名的条目保留靠前者，不会覆盖已有条目。

> 这个能力很实用：可以把本工具、LCSC3D、官方导出的库文件合并到一起。

---

## 五、验证：怎么证明"真的能用"

工具类项目最怕"看起来能用"。我用了三层验证：

**第一层：独立解析器反向校验**

不看"文件生成了没有"，而是用第三方读取器（`olefile`）解析生成的文件，核对引脚数、焊盘数、封装名索引是否正确。

**第二层：逐字节比对**

内嵌 3D 与官方源文件必须 bit 级一致——解压后比对哈希，不一致就是失败。

**第三层：洁净环境自测**

打包的 exe 内置 `--selftest` 模式，在**最小 PATH + 清空所有 PYTHON 环境变量**的条件下真实下载 + 转换 + 校验：

```bash
PATH="/c/Windows/System32:/c/Windows" PYTHONHOME= PYTHONPATH= ./工具.exe --selftest C131443
# checks={"3d":true,"symbol":true,"footprint":true,"ad":true,"ad3d":true,"ad_merge":true,"manual_merge":true}
# RESULT: PASS
```

另外通过 PE 依赖分析确认：exe 只依赖 5 个 Windows 系统 DLL，运行时自带解压的 Python，**目标电脑什么都不用装**。

---

## 六、开源与许可

项目已开源（**AGPL-3.0**）：

- **GitHub**：https://github.com/Carfaded/lcsc-lib-downloader
- **Gitee**：https://gitee.com/DunnPP/lcsc-lib-downloader（国内访问更快）

**功能一览**：

| 输出 | 格式 |
|---|---|
| 3D 模型 | STEP（纯元件，不含 PCB） |
| 原理图符号 | 立创EDA JSON |
| PCB 封装 | 立创EDA JSON |
| AD 符号库 | `.SchLib`（原生二进制，可内嵌 3D） |
| AD 封装库 | `.PcbLib`（原生二进制，可内嵌 3D） |
| 合并库 | `LCSC3D.SchLib` / `LCSC3D.PcbLib`（封装去重） |

**特别致谢**：

- [LCSC3D](https://github.com/Travelerrrrrr/LCSC3D) —— AD 二进制格式转换链的完整实现，是这个项目的地基；
- [sv_ttk](https://github.com/rdbende/Sun-Valley-ttk-theme) —— 界面用的 Win11 Fluent 风格主题。

**说明**：通过本工具获取的元件数据（3D 模型、符号、封装等）版权归立创/嘉立创及相关厂商所有，请遵守其使用条款，仅用于个人合法的硬件设计工作。

---

## 写在最后

这个项目技术上最有意思的点在于：**真正的难点从来不是"下载"**，而是——

1. 判断下载到的数据**是不是你要的东西**（不含 PCB 的几何校验）；
2. 输出到目标软件能**直接用**的格式（AD 二进制库 + 3D 内嵌）；
3. 对结果做**可验证的证明**（独立解析、逐字节比对、洁净环境自测）。

希望这个小工具能帮画板子的朋友省点时间。如果对你有用，欢迎 Star 和提 Issue；也欢迎在评论区交流你的使用场景，我看看是不是还能加需求。

---

*本文由工具作者撰写。技术细节如有疑问，欢迎评论区交流。*
