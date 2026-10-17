@echo off
chcp 65001 >nul
REM ============================================================
REM  一键推送到 GitHub / Gitee
REM  用法: publish.bat
REM  需先在仓库根目录配置 remote:
REM     git remote add origin  https://github.com/<用户名>/<仓库名>.git
REM     git remote add gitee   https://gitee.com/<用户名>/<仓库名>.git
REM ============================================================

cd /d "%~dp0"

echo [1/3] 检查 remote 配置...
git remote -v
if errorlevel 1 (
  echo 未配置 remote, 请先执行:
  echo   git remote add origin https://github.com/^<用户名^>/^<仓库名^>.git
  echo   git remote add gitee  https://gitee.com/^<用户名^>/^<仓库名^>.git
  pause
  exit /b 1
)

echo.
echo [2/3] 推送到 Gitee (国内访问更快)...
git push gitee main
if errorlevel 1 (
  echo Gitee 推送失败, 请检查凭据
) else (
  echo Gitee 推送成功
)

echo.
echo [3/3] 推送到 GitHub...
git push origin main
if errorlevel 1 (
  echo GitHub 推送失败, 请检查凭据/Token
) else (
  echo GitHub 推送成功
)

echo.
echo ============================================================
echo 推送流程结束。
echo 记得给两个平台都创建 v1.2.0 Release 并上传 exe:
echo   立创3D封装下载器.exe
echo Release 说明见 docs\RELEASE_NOTES.md
echo ============================================================
pause
