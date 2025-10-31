# -*- mode: python ; coding: utf-8 -*-

import certifi
import os

# certifi의 CA 인증서 번들 경로
certifi_path = os.path.dirname(certifi.where())
cacert_file = os.path.join(certifi_path, 'cacert.pem')

a = Analysis(
    ['qt_main_app.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('loading.jpg', '.'),
        (cacert_file, 'certifi'),  # certifi CA 인증서 포함
    ],
    hiddenimports=[
        'certifi',
        'hanja',  # ✅ [추가] 한자 변환 라이브러리 (EXE 환경에서 누락 방지)
    ],
    hookspath=['.'],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

# --onefile 옵션: 모든 것을 단일 EXE 파일로 번들링
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='qt_main_app',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,  # --windowed 옵션
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='M.ico',  # --icon 옵션
)
