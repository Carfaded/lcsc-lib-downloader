# 发布指南

## ✅ 发布状态

| 平台         | 状态                                      | 地址                                                |
| ---------- | --------------------------------------- | ------------------------------------------------- |
| **GitHub** | ✅ **已完成**（代码 + v1.2.0 Release + exe 附件） | <https://github.com/Carfaded/lcsc-lib-downloader> |
| **Gitee**  | ⚠️ 仓库已建，推送被「隐藏邮箱保护」钩子拦截（需一次性网页确认）       | <https://gitee.com/DunnPP/lcsc-lib-downloader>    |
| **CSDN**   | 📝 文章已备好，待发布                            | `docs/csdn-blog.html`                             |

**GitHub Release 下载地址**：  
<https://github.com/Carfaded/lcsc-lib-downloader/releases/tag/v1.2.0>

---

## 一、Gitee 推送被拦截的解决方法

### 问题现象

```
remote: Push will publish a hidden email, make email public or abandon related commits
remote: error: hook declined to update refs/heads/main
 ! [remote rejected] main -> main (hook declined)
```

### 原因

Gitee 默认开启「**隐藏邮箱保护**」：如果 git 提交使用的邮箱**没有在 Gitee 公开过**，  
Gitee 的服务端钩子会拒绝整个推送。

这是**服务端策略**，无法用命令行参数绕过，必须在网页端确认一次。

### 解决方法（二选一）

#### 方案 A：公开邮箱（推荐，最简单）

1. 打开 **<https://gitee.com/settings/profile>**
2. 找到「**隐藏邮箱**」设置，改为「**不隐藏**」（或关闭该开关）
3. 双击仓库里的 **`push_to_gitee.bat`** 完成推送

> 通常 1 分钟搞定，且不影响任何已有提交。

#### 方案 B：换用 Gitee 邮箱并重写提交

如果不想公开真实邮箱：

```bash
# 1. 在 https://gitee.com/settings/profile 复制你的 Gitee 专属邮箱
git config user.email "你的Gitee邮箱"

# 2. 重写历史提交的作者信息（7 个提交，约 1 分钟）
git rebase --exec 'git commit --amend --reset-author' -i v1.0.0

# 3. 强制推送
git push gitee main --tags --force
```

> 仓库里已备好 `push_to_gitee.bat`，处理完邮箱设置后双击即可，  
> 脚本会自动推送并给出 Release 创建指引。

---

## 二、GitHub（已完成）

- 代码仓库：<https://github.com/Carfaded/lcsc-lib-downloader>
- v1.2.0 Release：<https://github.com/Carfaded/lcsc-lib-downloader/releases/tag/v1.2.0>
- exe 附件：`lcsc-lib-downloader-v1.2.0.exe`（11.99 MB）

---

## 三、创建 Gitee Release（Gitee 推送完成后）

1. 打开仓库 → 右上角 **「发行版」** → **「创建发行版」**
2. 标签选 `v1.2.0`
3. 标题：`v1.2.0 - AD库合并 + 手动合并库 + 日志清理`
4. 描述：粘贴 `docs/RELEASE_NOTES.md` 的内容
5. 上传附件：`dist\立创3D封装下载器.exe`  
   （建议改名为 `lcsc-lib-downloader-v1.2.0.exe`，浏览器端兼容性更好）
6. 发布

---

## 四、发布博客到 CSDN

1. 登录 **<https://editor.csdn.net/md/?not_checkout=1>**
2. 新建文章，标题：
   ```
   立创商城元件库批量下载工具：3D模型/原理图符号/PCB封装/AD原生库一键生成（含3D内嵌）
   ```
3. 打开 `docs/csdn-blog.html`，全选复制，粘贴到编辑器
4. 上传两张图片，替换文中的黄色占位块：
   - 图片1：`docs/csdn-image-1-ui.png`（主界面）
   - 图片2：`docs/csdn-image-2-merge.png`（合并对话框）
5. 发布设置：
   - 分类：`硬件` 或 `嵌入式`
   - 标签：`立创`、`Altium Designer`、`PCB`、`硬件设计`、`开源`、`Python`、`电子设计`
   - 原创声明：勾选「原创」
6. 发布

> 文章内容已包含 GitHub / Gitee 仓库地址，可直接发布。

---

## 五、自己推送（备用）

在 `D:\workbuddy\3d\lcsc_3d` 目录：

```bash
# Gitee（需先完成上面的邮箱确认）
git push gitee main --tags

# GitHub
git push origin main --tags
```

或双击 `publish.bat`（推送双平台）。

---

## 六、常见问题

**Q: GitHub 上传中文名附件被截断成 `3D.exe`？**  
A: GitHub API 对非 ASCII 文件名支持不佳。本项目已改用 ASCII 名 `lcsc-lib-downloader-v1.2.0.exe`。  
用网页端上传时也可能乱码，建议同样用英文名。

**Q: 推送时提示 remote rejected（非快进）？**  
A: 远端有初始提交。删掉远端仓库重建（不勾任何模板），或执行 `git push --force`。

**Q: exe 要不要放进 git 仓库？**  
A: 不放。12MB 二进制会让 clone 变慢，放 Release 附件。仓库里有 `build_exe.bat`，用户可自行构建。

**Q: 文档里还有占位符吗？**  
A: 已全部替换为实际地址（GitHub: `Carfaded`，Gitee: `DunnPP`）。

**Q: 令牌安全吗？**  
A: 令牌仅通过命令行临时注入（`http.extraheader`），**未写入 git config、未落盘**。  
项目结束后建议到 <https://github.com/settings/tokens> 撤销该令牌。
