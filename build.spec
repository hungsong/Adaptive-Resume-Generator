# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 打包配置：pyinstaller build.spec

产物在 dist\自适应简历生成器\ 下，双击 exe 即可运行。
注意：data / logs / config.json 会生成在 exe 同目录，不会打进包里。
"""

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=['openai', 'docx', 'pypdf'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'tkinter', 'matplotlib', 'numpy', 'pandas',
        # 当前应用只使用 PyQt5；避免打包机同时安装 PySide6/PyQt6 时误收集多套 Qt。
        'PySide6', 'shiboken6', 'PyQt6',
        # 开发/测试工具不属于运行时依赖，避免进入用户发布包。
        'IPython', 'ipykernel', 'jupyter_client', 'jupyter_core', 'jupyterlab',
        'notebook', 'nbconvert', 'nbformat', 'jedi', 'parso', 'pygments',
        'pytest', '_pytest', 'dill', 'zmq',
    ],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='自适应简历生成器',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name='自适应简历生成器',
)
