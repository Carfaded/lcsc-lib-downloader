@echo off
chcp 65001 >nul
REM ============================================================
REM  Gitee 推送脚本（解决"hidden email"钩子拦截）
REM
REM  Gitee 默认开启「隐藏邮箱保护」：如果提交的邮箱未在 Gitee
REM  公开，推送会被服务端钩子拒绝（hook declined）。
REM
REM  首次使用请先完成一次网页确认（见下方说明），之后本脚本可直接用。
REM ============================================================

cd /d "%~dp0"

echo ============================================
echo  Gitee 推送 - lcsc-lib-downloader
echo ============================================
echo.

REM --- 检查钩子是否已解除：试探性推送 ---
echo [1/2] 尝试推送到 Gitee...
set GIT_TERMINAL_PROMPT=0
git push gitee main --tags 2>&1 | findstr /C:"hook declined" >nul
if errorlevel 1 goto :done

echo.
echo [X] 仍被 Gitee 的「隐藏邮箱保护」钩子拦截
echo.
echo 需要你做一次性确认（二选一）：
echo.
echo   方案 A - 公开邮箱（推荐，最简单）
echo     1. 打开 https://gitee.com/settings/profile
echo     2. 找到「隐藏邮箱」设置，改为「不隐藏」
echo        （或直接关闭该开关）
echo     3. 回来重新运行本脚本
echo.
echo   方案 B - 换用 Gitee 提供的提交邮箱
echo     1. 在 https://gitee.com/settings/profile 查看你的 Gitee 邮箱
echo     2. 执行: git config user.email "你的Gitee邮箱"
echo     3. 如果历史提交也要改邮箱:
echo        git rebase --exec 'git commit --amend --reset-author' -i v1.0.0
echo        （较慢，约 7 个提交）
echo.
echo 详细说明见 docs\PUBLISH_GUIDE.md
echo.
pause
exit /b 1

:done
echo.
echo [2/2] 推送成功！
echo.
echo   仓库: https://gitee.com/DunnPP/lcsc-lib-downloader
echo.
echo 接下来在 Gitee 网页端创建 Release:
echo   1. 打开仓库 -^> 右上角「发行版」-^> 「创建发行版」
echo   2. 标签选 v1.2.0
echo   3. 标题: v1.2.0 - AD库合并 + 手动合并库 + 日志清理
echo   4. 描述粘贴 docs\RELEASE_NOTES.md 内容
echo   5. 上传附件: dist\立创3D封装下载器.exe
echo      (建议改名为 lcsc-lib-downloader-v1.2.0.exe，浏览器端兼容性更好)
echo   6. 发布
echo.
pause
