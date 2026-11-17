@echo off
chcp 65001 >nul
cd /d "%~dp0"
where pythonw >nul 2>nul && (start "" pythonw "main.py" & goto :eof)
if exist "E:\python\pythonw.exe" (start "" "E:\python\pythonw.exe" "main.py" & goto :eof)
echo 未找到 Python，请先安装 Python 3.10 以上版本，或修改本文件里的 Python 路径。
pause
