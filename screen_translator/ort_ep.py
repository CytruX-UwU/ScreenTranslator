"""Pick CUDA vs DirectML flags for RapidOCR from env + onnxruntime. 根据环境与 ORT 解析 CUDA / DirectML 开关。"""

from __future__ import annotations

import platform
import sys
from typing import Tuple

_CUDA = "CUDAExecutionProvider"
_DML = "DmlExecutionProvider"


def resolve_ocr_ep_flags(want_cuda: bool, want_dml: bool) -> Tuple[bool, bool]:
    """
    Return (use_cuda, use_dml) actually passed to RapidOCR.
    返回将传给 RapidOCR 的 (use_cuda, use_dml)。

    If both backends are wanted and available, CUDA wins (DirectML disabled).
    若两者均为 True 且均可用，优先 CUDA并关闭 DirectML（默认依赖为 DML，通常仅其一为 True）。
    """
    try:
        from onnxruntime import get_available_providers, get_device
    except ImportError:
        if want_cuda or want_dml:
            print("OCR: onnxruntime not importable; CUDA/DirectML disabled.", flush=True)
        return False, False

    providers = get_available_providers()
    cuda_runtime_ok = _CUDA in providers and get_device() == "GPU"
    dml_runtime_ok = (
        _DML in providers
        and sys.platform == "win32"
        and int(platform.release().split(".")[0]) >= 10
    )

    if want_cuda and not cuda_runtime_ok:
        print("OCR: CUDA requested but unavailable; using CPU for OCR.", flush=True)
    if want_dml and not dml_runtime_ok:
        if sys.platform != "win32":
            print("OCR: DirectML is Windows-only; skipped.", flush=True)
        else:
            print(
                "OCR: DirectML requested but unavailable; using CPU.",
                flush=True,
            )

    use_cuda = bool(want_cuda and cuda_runtime_ok)
    use_dml = bool(want_dml and dml_runtime_ok)

    if use_cuda and use_dml:
        print(
            "OCR: CUDA and DirectML both available; using CUDA only (DirectML off).",
            flush=True,
        )
        use_dml = False

    return use_cuda, use_dml
