import os

_ICON = os.environ.get('FNAUTO_ICON', '')
_VERSION_FILE = os.environ.get('FNAUTO_VERSION_FILE', 'version_info.txt')


a = Analysis(
    ['qt_app.py'],
    pathex=[],
    binaries=[],
    datas=[('icon.ico', '.'), ('assets', 'assets'), ('assets', 'assets_default')],
    hiddenimports=['PySide6.QtSvg', 'keyboard', 'PIL.Image'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter', '_tkinter', 'tkinter.ttk', 'tkinter.messagebox', 'PIL.ImageTk', 'PySide6.QtWebEngine', 'PySide6.QtWebEngineCore', 'PySide6.QtWebEngineWidgets', 'PySide6.QtWebEngineQuick', 'PySide6.Qt3DCore', 'PySide6.Qt3DRender', 'PySide6.Qt3DInput', 'PySide6.Qt3DLogic', 'PySide6.Qt3DAnimation', 'PySide6.Qt3DExtras', 'PySide6.QtQuick', 'PySide6.QtQuickWidgets', 'PySide6.QtQuickControls2', 'PySide6.QtQuick3D', 'PySide6.QtMultimedia', 'PySide6.QtMultimediaWidgets', 'PySide6.QtCharts', 'PySide6.QtPdf', 'PySide6.QtPdfWidgets', 'PySide6.QtSql', 'PySide6.QtTest', 'PySide6.QtDesigner', 'PySide6.QtHelp', 'PySide6.QtBluetooth', 'PySide6.QtNfc', 'PySide6.QtPositioning', 'PySide6.QtLocation', 'PySide6.QtSerialPort', 'PySide6.QtSensors', 'PySide6.QtWebSockets', 'PySide6.QtWebChannel', 'PySide6.QtRemoteObjects', 'PySide6.QtScxml', 'PySide6.QtStateMachine', 'PySide6.QtOpenGL', 'PySide6.QtOpenGLWidgets', 'PySide6.QtSvgWidgets', 'PySide6.QtNetwork', 'PySide6.QtPrintSupport', 'PySide6.QtXml', 'PySide6.QtConcurrent', 'PySide6.QtDBus', 'PySide6.QtGraphs', 'PySide6.QtGraphsWidgets', 'PySide6.QtTextToSpeech', 'PySide6.QtUiTools', 'PySide6.QtSpatialAudio', 'PySide6.QtSerialBus'],
    noarchive=False,
    optimize=0,
)

_DROP_QT = (
    'qt6quick', 'qt6qml', 'qt6pdf', 'qt6opengl', 'qt6network',
    'qtnetwork.pyd', 'qtpdf.pyd', 'qtopengl.pyd', 'qt6virtualkeyboard',
    '/qml/', 'platforminputcontexts/', 'networkinformation/', 'opengl32sw.dll',
)


def _drop_qt(entry):
    dest = entry[0].replace('\\', '/').lower()
    return any(token in dest for token in _DROP_QT)


a.binaries = [entry for entry in a.binaries if not _drop_qt(entry)]
a.datas = [entry for entry in a.datas if not _drop_qt(entry)]

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='FNauto',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    version=_VERSION_FILE,
    icon=[_ICON] if _ICON else [],
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='FNauto',
)
