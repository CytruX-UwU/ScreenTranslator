#!/usr/bin/env python3
"""
ONNX Runtime + CUDA diagnostic for Screen Translator.
Run from repo root: uv run python tools/diagnose_ort_cuda.py

检查 ORT 是否识别 GPU、与 RapidOCR 条件是否一致，并尝试用 RapidOCR 自带 det 模型建 Session。
"""

from __future__ import annotations

import importlib.util
import os
import platform
import subprocess
import sys
from pathlib import Path


def _section(title: str) -> None:
    print()
    print("=" * 60)
    print(title)
    print("=" * 60)


def _try_nvidia_smi() -> None:
    for cmd in (["nvidia-smi"], ["nvidia-smi", "-L"]):
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
            print(r.stdout or "(no stdout)")
            if r.stderr:
                print("stderr:", r.stderr)
            return
        except FileNotFoundError:
            print("nvidia-smi not found in PATH.")
            return
        except subprocess.TimeoutExpired:
            print("nvidia-smi timed out.")
            return
        except OSError as e:
            print(f"nvidia-smi error: {e}")
            return


def _rapidocr_det_model() -> Path | None:
    spec = importlib.util.find_spec("rapidocr_onnxruntime")
    if not spec or not spec.origin:
        return None
    root = Path(spec.origin).resolve().parent
    p = root / "models" / "ch_PP-OCRv4_det_infer.onnx"
    return p if p.is_file() else None


def main() -> int:
    _section("Environment / 环境")
    print("Python:", sys.version.replace("\n", " "))
    print("Executable:", sys.executable)
    print("Platform:", platform.platform())

    _section("NVIDIA driver (nvidia-smi) / NVIDIA 驱动")
    _try_nvidia_smi()

    _section("Import onnxruntime / 导入 ORT")
    try:
        import onnxruntime as ort
    except Exception as e:
        print("FAILED:", repr(e))
        return 1

    print("onnxruntime file:", Path(ort.__file__).resolve())
    print("Version:", ort.__version__)

    try:
        print("get_build_info():\n", ort.get_build_info())
    except Exception as e:
        print("get_build_info() unavailable:", e)

    try:
        pkg, ver, cuda_ver = ort.capi.onnxruntime_validation.get_package_name_and_version_info()
        print("validation package_name:", pkg, "version:", ver, "cuda_version:", cuda_ver)
    except Exception as e:
        print("get_package_name_and_version_info:", e)

    try:
        from onnxruntime.capi import build_and_package_info as bpi

        print("build_and_package_info:", getattr(bpi, "package_name", "?"), getattr(bpi, "cuda_version", "?"))
    except Exception as e:
        print("build_and_package_info import:", e)

    ap = ort.get_available_providers()
    allp = ort.get_all_providers()
    dev = ort.get_device()

    print()
    print("get_device():", repr(dev), "<- RapidOCR uses (dev == 'GPU') AND CUDA in providers")
    print("get_available_providers():", ap)
    print("get_all_providers():", allp)

    try:
        epd = ort.get_ep_devices()
        print("get_ep_devices():", epd)
    except Exception as e:
        print("get_ep_devices():", e)

    cuda_in_avail = "CUDAExecutionProvider" in ap
    dml_in_avail = "DmlExecutionProvider" in ap
    dev_is_gpu = dev == "GPU"

    _section("Checks matching screen_translator/ort_ep.py / 与 ort_ep 一致")
    print("CUDAExecutionProvider in get_available_providers():", cuda_in_avail)
    print("get_device() == 'GPU':", dev_is_gpu)
    print("ort_ep current rule (both True):", cuda_in_avail and dev_is_gpu)

    _section("Checks matching RapidOCR OrtInferSession._check_cuda / 与 RapidOCR 内部一致")
    print("RapidOCR enables CUDA only if BOTH hold / RapidOCR 需同时满足:")
    print("  - CUDAExecutionProvider in had_providers (same as available at import time)")
    print("  - get_device() == 'GPU'")
    rapidocr_cuda = cuda_in_avail and dev_is_gpu
    print("=> RapidOCR would use CUDA:", rapidocr_cuda)

    if cuda_in_avail and not dev_is_gpu:
        print()
        print("*** MISMATCH / 不一致 ***")
        print("CUDA EP is listed as available but get_device() is not 'GPU'.")
        print("This often happens with mixed installs or ORT build quirks.")
        print("Try: pip uninstall onnxruntime onnxruntime-gpu onnxruntime-directml -y")
        print("     pip install onnxruntime-gpu  (one variant only)")
        print("Update GPU driver; ensure CUDA runtime expected by this ORT build is present.")

    _section("Env vars (optional) / 环境变量（节选）")
    for k in ("CUDA_PATH", "CUDA_HOME", "PATH"):
        v = os.environ.get(k)
        if v:
            print(f"{k}={v[:200]}{'...' if len(v) > 200 else ''}")

    det = _rapidocr_det_model()
    session_used_cuda = False
    if det:
        _section("Trial: InferenceSession with RapidOCR det ONNX / 试用 det 模型建会话")
        print("Model:", det)
        try:
            so = ort.SessionOptions()
            so.log_severity_level = 4
            sess = ort.InferenceSession(
                str(det),
                sess_options=so,
                providers=["CUDAExecutionProvider", "CPUExecutionProvider"],
            )
            first = sess.get_providers()[0]
            session_used_cuda = first == "CUDAExecutionProvider"
            print("Session created. get_providers():", sess.get_providers())
            print("First (primary) provider:", first)
            if first != "CUDAExecutionProvider":
                print()
                print("*** CUDA was REQUESTED first but did NOT become the active provider. ***")
                print("*** 已优先请求 CUDA，但实际会话主 EP 不是 CUDA。***")
                print("Typical causes / 常见原因:")
                print("  - Missing CUDA 12.x runtime DLLs (e.g. cublasLt64_12.dll). See import stderr above.")
                print("  - onnxruntime-gpu 1.24.x expects CUDA 12.x + cuDNN 9.x per ORT docs; CUDA_PATH=11.x is too old.")
                print("  - Install CUDA Toolkit 12.x (matching ORT), add its bin to PATH, or fix DLL load errors.")
        except Exception as e:
            print("InferenceSession(CUDA first) FAILED:", repr(e))
            try:
                sess2 = ort.InferenceSession(str(det), sess_options=so, providers=["CPUExecutionProvider"])
                print("Fallback CPU-only session OK; first provider:", sess2.get_providers()[0])
            except Exception as e2:
                print("CPU-only session also failed:", repr(e2))
    else:
        _section("Trial: ONNX model / 试用模型")
        print("rapidocr det model not found; skip InferenceSession test.")
        print("Expected:", "site-packages/rapidocr_onnxruntime/models/ch_PP-OCRv4_det_infer.onnx")

    _section("Summary / 小结")

    if session_used_cuda:
        print("CUDA is the active InferenceSession provider — OCR can use GPU.")
    elif rapidocr_cuda and det:
        print("Providers list looks OK, but InferenceSession did NOT use CUDA (see trial section).")
        print("Fix CUDA 12.x/cuDNN DLLs on PATH; align CUDA toolkit with onnxruntime-gpu build (see build cuda_version).")
    elif cuda_in_avail and not dev_is_gpu:
        print("Fix get_device() vs CUDA availability first (see MISMATCH above).")
    elif not cuda_in_avail:
        print("Install onnxruntime-gpu matching your driver/CUDA; avoid mixing onnxruntime CPU+GPU.")
    else:
        print("Unexpected state; share this full log.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
