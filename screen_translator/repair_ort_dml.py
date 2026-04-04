"""
Reinstall onnxruntime-directml so its onnxruntime/ tree wins over rapidocr's onnxruntime (CPU).

rapidocr-onnxruntime depends on the PyPI package "onnxruntime"; uv installs both, and the CPU
wheel can overwrite DLLs. Run after `uv sync` if DmlExecutionProvider is missing:

  uv run python -m screen_translator.repair_ort_dml

rapidocr 会拉取 onnxruntime（CPU），与 onnxruntime-directml 同时安装时可能覆盖动态库；
若导入后没有 DmlExecutionProvider，请在 sync 后执行上述命令。
"""

from __future__ import annotations

import subprocess
import sys


def main() -> None:
    subprocess.check_call(
        [
            sys.executable,
            "-m",
            "uv",
            "pip",
            "install",
            "--reinstall",
            "onnxruntime-directml>=1.20.0,<1.21.0",
        ]
    )


if __name__ == "__main__":
    main()
