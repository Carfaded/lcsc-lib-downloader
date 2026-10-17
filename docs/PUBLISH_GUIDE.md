# 发布指南

代码已就绪（6 个提交 / 48 个文件 / 1.3 MB）。按下面步骤发布到两个平台。

---

## 一、创建 Gitee 仓库（3 分钟）

### 第 1 步：打开创建页面

浏览器访问：**https://gitee.com/projects/new**

### 第 2 步：填写仓库信息

| 字段 | 填什么 |
|---|---|
| 仓库路径（必填） | `lcsc-lib-downloader` |
| 仓库描述（建议填） | `立创商城元件库批量下载器：3D模型(STEP)/原理图符号/PCB封装/Altium原生库(SchLib+PcbLib，可内嵌3D、可合并)` |
| 仓库归属 | 个人 → 选择 `DunnPP` |
| 仓库可见性 | **公开**（开源项目） |
| 设置默认分支 | `main` |
| 模板 | ⚠️ **三个都不要勾** |
| ⚪️ 使用 .gitignore 模板 | **不要勾** |
| ⚪️ 使用 Readme 文件初始化 | **不要勾** |
| ⚪️ 许可文件 | **不要勾** |

> **关键**：不要勾任何初始化模板，否则会产生独立提交导致推送冲突。

### 第 3 步：创建后复制仓库地址

创建成功后会跳转到仓库页面，地址栏类似：

```
https://gitee.com/DunnPP/lcsc-lib-downloader
```

HTTPS 地址为：

```
https://gitee.com/DunnPP/lcsc-lib-downloader.git
```

**把这个地址发给我**，我就能直接推送。

---

## 二、创建 GitHub 仓库（3 分钟）

### 第 1 步：打开创建页面

浏览器访问：**https://github.com/new**

### 第 2 步：填写仓库信息

| 字段 | 填什么 |
|---|---|
| Owner | 选择你的账号 |
| Repository name | `lcsc-lib-downloader` |
| Description | `立创商城元件库批量下载器：3D模型/符号/封装/Altium原生库(可内嵌3D、可合并)` |
| Visibility | **Public** |
| ⚪️ Add a README file | **不要勾** |
| ⚪️ Add .gitignore | **不要勾** |
| ⚪️ Choose a license | **不要选** |

### 第 3 步：生成访问令牌

1. 访问：**https://github.com/settings/tokens**
2. 点 **Generate new token (classic)**
3. 填写：
   - Note：`lcsc-lib-downloader`
   - Expiration：`90 days`（或 30 days）
   - Scopes：勾选 **`repo`**（勾它下面自动全选）
4. 点底部 **Generate token**
5. **复制令牌**（形如 `ghp_xxxxxxxxxxxx`，只显示一次）

> ⚠️ **安全提示**：这个令牌等同于你的账号密码，不要发给任何人。直接在本对话中提供给我即可，我只会用它执行推送。

---

## 三、把信息发我，我来执行

发我这两样：

```
Gitee 仓库地址：https://gitee.com/DunnPP/lcsc-lib-downloader.git
GitHub Token：ghp_xxxxxxxxxxxx
```

我会执行：
1. 配置两个 remote
2. 推送到 Gitee 和 GitHub
3. 打 v1.2.0 标签

---

## 四、你自己推送（替代方案）

如果你不想提供 Token，在 `D:\workbuddy\3d\lcsc_3d` 目录执行：

```bash
# 配置 remote
git remote add origin https://github.com/你的用户名/lcsc-lib-downloader.git
git remote add gitee  https://gitee.com/DunnPP/lcsc-lib-downloader.git

# 打标签
git tag -a v1.2.0 -m "v1.2.0: AD库合并 + 手动合并库 + 日志清理"

# 推送
git push gitee main --tags
git push origin main --tags
```

或者直接运行仓库里的 **`publish.bat`**（双击即可）。

推送时 GitHub 会要求认证：
- 用户名：你的 GitHub 用户名
- 密码：**粘贴 Token**（不是账号密码）

---

## 五、创建 Release（推送后）

两个平台各做一次：

### Gitee

1. 打开仓库页面 → 右上角 **「发行版」** → **「创建发行版」**
2. 标签选 `v1.2.0`
3. 标题：`v1.2.0 - AD库合并 + 手动合并库 + 日志清理`
4. 描述：粘贴 `docs/RELEASE_NOTES.md` 内容
5. 上传附件：`dist\立创3D封装下载器.exe（上传时建议改名 lcsc-lib-downloader-v1.2.0.exe）`
6. 发布

### GitHub

1. 打开仓库 → 右侧 **Releases** → **Draft a new release**
2. 选择标签 `v1.2.0`
3. 标题：`v1.2.0 - AD库合并 + 手动合并库 + 日志清理`
4. 描述：粘贴 `docs/RELEASE_NOTES.md` 内容
5. 上传 `lcsc-lib-downloader-v1.2.0.exe`
6. **Publish release**

---

## 六、发布博客到 CSDN

1. 登录 **https://editor.csdn.net/md/?not_checkout=1**
2. 新建文章，标题：

   ```
   立创商城元件库批量下载工具：3D模型/原理图符号/PCB封装/AD原生库一键生成（含3D内嵌）
   ```

3. 打开 `docs/csdn-blog.html`，全选复制，粘贴到编辑器
4. 上传两张图片并替换占位符：
   - 图片1：`docs/screenshots/ui.png`
   - 图片2：`docs/screenshots/merge_dialog.png`
5. 发布设置建议：
   - 分类：`硬件` 或 `嵌入式`
   - 标签：`立创`、`Altium Designer`、`PCB`、`硬件设计`、`开源`、`Python`、`电子设计`
   - 原创声明：勾选「原创」
6. 发布

---

## 常见问题

**Q: 推送时提示 Authentication failed？**
A: GitHub 用户名填 GitHub 用户名，密码位置粘贴 Token（不是账号密码）。

**Q: 推送时提示 remote rejected（非快进）？**
A: 远端有初始提交。删掉远端重建（不勾模板），或执行：
```bash
git push --force origin main
```

**Q: exe 要不要放进仓库？**
A: 不放。12MB 二进制文件进仓库会让 clone 变慢，放 Release 附件里，用户点击下载即可。仓库里已有 `build_exe.bat`，用户可自行构建。

**Q: 代码里的占位链接？**
A: `README.md` 和 `CHANGELOG.md` 里有少量 `<你的仓库地址>` 占位，推送后自行替换即可（不影响使用）。
