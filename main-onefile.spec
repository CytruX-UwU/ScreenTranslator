# -*- mode: python ; coding: utf-8 -*-
# One-file bundle (单文件一体包): output dist/ScreenTranslator.exe

from PyInstaller.utils.hooks import collect_all, collect_submodules

_pystray_datas, _pystray_binaries, _pystray_hiddenimports = collect_all('pystray')
_ort_datas, _ort_binaries, _ort_hiddenimports = collect_all('onnxruntime')
_rapid_datas, _rapid_binaries, _rapid_hiddenimports = collect_all('rapidocr_onnxruntime')

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=_pystray_binaries + _ort_binaries + _rapid_binaries,
    datas=_pystray_datas + _ort_datas + _rapid_datas,
    hiddenimports=_pystray_hiddenimports
    + _ort_hiddenimports
    + _rapid_hiddenimports
    + collect_submodules('screen_translator')
    + collect_submodules('rapidocr_onnxruntime'),
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='ScreenTranslator',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
