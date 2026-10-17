# v1.2.0 发布说明

## 立创商城元件库批量下载器

输入立创编号（C131443），一键批量下载 **3D 模型 / 原理图符号 / PCB 封装 / Altium Designer 原生库**，
并可直接生成 **内嵌 3D 模型的 PcbLib**、把多个器件 **合并为单个库文件**。

---

## 下载

**Windows 用户**：下载 `lcsc-lib-downloader-v1.2.0.exe`，双击即用。
**无需安装 Python**，无需任何运行库，单文件即全部。

> 首次运行如被杀毒软件提示（PyInstaller 打包程序的常见误报），添加信任即可。
> 运行环境要求：Windows 7 及以上（64 位）。

---

## v1.2.0 新增

### 手动合并已有 AD 库文件
界面右上角「**合并库…**」按钮：选择多个 `.SchLib` 或多个 `.PcbLib` 合并为一个。

- **顺序即优先级**：完全重复 / 同名的条目保留靠前者，不覆盖已有条目
- **PcbLib 按内容去重**，3D 模型表自动合并
- 适用于合并不同来源的库文件（本工具 / LCSC3D / 官方导出）

### 运行日志一键清空
- 日志区右上角「**清空日志**」按钮
- 每轮下载开始时**自动清空**，多批次不堆积

### 多器件 AD 库合并（下载时）
勾选「**AD库合并**」后，不再生成 N 个单器件库文件，整批合并为：

```
LCSC3D.SchLib    # 含全部符号
LCSC3D.PcbLib    # 含全部封装（相同封装自动去重，符号引用自动指向最终封装名）
```

命令行对应：`--merge`

### 其他
- 新增 `--no-ad-3d`（不内嵌 3D，生成更小的 PcbLib）
- 修复标题栏按钮文字被截断的问题

---

## 完整功能

| 功能 | 说明 |
|---|---|
| 3D 模型 (STEP) | **纯元器件，不含 PCB 基板**，自动几何校验 |
| 原理图符号 | 立创EDA 标准格式 JSON |
| PCB 封装 | 立创EDA 标准格式 JSON |
| AD 符号库 (.SchLib) | AD 原生二进制，可选内嵌 3D |
| AD 封装库 (.PcbLib) | AD 原生二进制，可选内嵌 3D |
| 库合并 | 多器件 → 单个库；已有库 → 手动合并 |
| 批量下载 | 界面粘贴 / codes.txt / 命令行，自动去重 |
| 风控重试 | 请求间隔 + 指数退避，断连自动恢复 |
| 断点续传 | 已下载自动跳过，`--force` 重下 |
| 免安装 | 单文件 exe，无需 Python |

---

## 使用

### 图形界面

1. 粘贴立创编号（一行一个，如 `C131443`）
2. 选择保存路径
3. 勾选需要的内容（默认全选）
4. 点击「开始下载」

### 命令行

```bash
# 全量下载
python lcsc_3d_downloader.py C131443 C25804 C14663

# 从文件读编号
python lcsc_3d_downloader.py -f codes.txt -o D:\step

# 只生成 AD 库（默认内嵌 3D）
python lcsc_3d_downloader.py C131443 --types ad

# 合并为单个库
python lcsc_3d_downloader.py -f codes.txt --merge --types ad

# 不内嵌 3D（体积更小）
python lcsc_3d_downloader.py C131443 --types ad --no-ad-3d
```

### AD 中使用生成的库

- **直接打开**：`File → Open` 打开 `.SchLib` / `.PcbLib`
- **长期使用**：`Components 面板 → 菜单 → File-based Libraries Preferences → Add Library`
- **查看 3D**：打开 `.PcbLib` 后按快捷键 `3`

---

## 从源码构建

需要 Python 3.10+（含 tkinter）：

```bat
build_exe.bat
```

或手动：

```bash
pip install pyinstaller sv_ttk olefile
pyinstaller --onefile --noconsole --clean --name lcsc3d_gui \
  --icon app.ico --add-data "app.ico;." \
  --collect-all sv_ttk --paths . --collect-submodules lcsc3d \
  lcsc_3d_gui.py
```

---

## 校验说明

`{编号}_{符号名}.SchLib` / `{编号}_{封装名}.PcbLib` / `LCSC3D.SchLib` / `LCSC3D.PcbLib`

---

## 致谢

- [LCSC3D](https://github.com/Travelerrrrrr/LCSC3D) —— AD 二进制格式转换链的完整实现
- [sv_ttk](https://github.com/rdbende/Sun-Valley-ttk-theme) —— Win11 Fluent 风格主题

元件数据版权归立创/嘉立创及相关厂商所有。
