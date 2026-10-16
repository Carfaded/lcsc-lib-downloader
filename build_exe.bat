@echo off
chcp 65001 >nul
REM ============================================================
REM  立创商城元件库批量下载器 - 一键打包脚本 (Windows)
REM  需要: Python 3.10+ (含 tkinter) 以及 pip
REM  产物: dist\lcsc3d_gui.exe
REM ============================================================

cd /d "%~dp0"

echo [1/3] 安装打包依赖 (pyinstaller / sv_ttk)...
python -m pip install --upgrade pyinstaller sv_ttk -i https://pypi.tuna.tsinghua.edu.cn/simple
if errorlevel 1 goto :fail

echo.
echo [2/3] PyInstaller 打包中...
pyinstaller --onefile --noconsole --clean --name lcsc3d_gui ^
  --icon app.ico --add-data "app.ico;." ^
  --collect-all sv_ttk --paths "%~dp0" --collect-submodules lcsc3d ^
  --distpath dist --workpath build --specpath build lcsc_3d_gui.py
if errorlevel 1 goto :fail

echo.
echo [3/3] 完成! 输出: dist\lcsc3d_gui.exe
echo      (可自由改名, 如: 立创3D封装下载器.exe)
pause
exit /b 0

:fail
echo.
echo 打包失败, 请检查上方错误信息。
pause
exit /b 1
