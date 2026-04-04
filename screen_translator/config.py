"""App-level constants (override via env or a config file if needed). 应用级常量（可改为环境变量或配置文件）。"""

# If you change hotkeys, update _VK_* / _MOD_* in hotkeys.py (RegisterHotKey) too.
# 若修改快捷键，请同步改 hotkeys.py 中 Windows 的 _VK_* / _MOD_*（RegisterHotKey）。
HOTKEY_FULL = "<ctrl>+<shift>+<1>"
HOTKEY_REGION = "<ctrl>+<shift>+<2>"
OCR_MIN_SCORE = 0.35
FONT_MAX = 22
FONT_MIN = 10

# RapidOCR / ONNXRuntime — same defaults as rapidocr_onnxruntime config.yaml; tune here later.
# RapidOCR / ONNXRuntime — 与 rapidocr_onnxruntime 默认一致，后续可在此调参。
OCR_USE_CLS = False  # Skip angle classifier when text is mostly upright. 文字基本正向时跳过方向分类。
OCR_MAX_SIDE_LEN = 2000  # Global max side before resize. 全局缩图前长边上限。
OCR_DET_LIMIT_SIDE_LEN = 736  # Det limit_side_len. 检测模型输入边长限制。

OCR_INTRA_OP_NUM_THREADS = -1  # -1: use ORT default. ONNXRuntime intra-op threads / 线程数，-1 为库默认。
OCR_INTER_OP_NUM_THREADS = -1  # ONNXRuntime inter-op threads / 并行算子间线程数。

# Prefer CUDA (onnxruntime-gpu) / DirectML (onnxruntime-directml); runtime may turn off if unavailable.
# 是否优先使用 CUDA / Windows DirectML；启动时检测 EP，不可用则自动关闭。
OCR_USE_CUDA = True
OCR_USE_DML = True
