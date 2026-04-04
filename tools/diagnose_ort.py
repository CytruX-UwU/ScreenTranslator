#!/usr/bin/env python3
"""
ONNX Runtime diagnostics: DirectML (default on Windows) and optional CUDA.
Run: uv run python tools/diagnose_ort.py

检查 DML / CUDA EP、与 ort_ep / RapidOCR 条件，并用 RapidOCR det 模型试建 Session。
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
    try:
        r = subprocess.run(["nvidia-smi"], capture_output=True, text=True, timeout=15)
        print(r.stdout or "(no stdout)")
        if r.stderr:
            print("stderr:", r.stderr)
    except FileNotFoundError:
        print("nvidia-smi not found (OK for DirectML-only).")
    except (subprocess.TimeoutExpired, OSError) as e:
        print(f"nvidia-smi: {e}")


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

    _section("GPU driver (optional) / 显卡驱动（可选）")
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
    dev = ort.get_device()

    print()
    print("get_device():", repr(dev))
    print("get_available_providers():", ap)

    cuda_ok = "CUDAExecutionProvider" in ap and dev == "GPU"
    dml_ok = "DmlExecutionProvider" in ap and sys.platform == "win32" and int(platform.release().split(".")[0]) >= 10

    _section("Match screen_translator/ort_ep.py / 与 ort_ep 一致")
    print("CUDA usable (ort_ep rule):", cuda_ok)
    print("DirectML usable (ort_ep rule):", dml_ok)

    _section("Env vars (optional) / 环境变量（节选）")
    for k in ("CUDA_PATH", "CUDA_HOME", "PATH"):
        v = os.environ.get(k)
        if v:
            print(f"{k}={v[:200]}{'...' if len(v) > 200 else ''}")

    det = _rapidocr_det_model()
    session_dml = False
    session_cuda = False
    if det:
        so = ort.SessionOptions()
        so.log_severity_level = 4

        if "DmlExecutionProvider" in ap:
            _section("Trial: InferenceSession — DML first / 试用 DML 优先")
            print("Model:", det)
            try:
                sess = ort.InferenceSession(
                    str(det),
                    sess_options=so,
                    providers=["DmlExecutionProvider", "CPUExecutionProvider"],
                )
                first = sess.get_providers()[0]
                session_dml = first == "DmlExecutionProvider"
                print("get_providers():", sess.get_providers())
                print("First provider:", first)
                if not session_dml:
                    print("*** DML requested first but primary EP is not DmlExecutionProvider. ***")
            except Exception as e:
                print("DML session FAILED:", repr(e))

        if "CUDAExecutionProvider" in ap:
            _section("Trial: InferenceSession — CUDA first / 试用 CUDA 优先")
            print("Model:", det)
            try:
                sess = ort.InferenceSession(
                    str(det),
                    sess_options=so,
                    providers=["CUDAExecutionProvider", "CPUExecutionProvider"],
                )
                first = sess.get_providers()[0]
                session_cuda = first == "CUDAExecutionProvider"
                print("get_providers():", sess.get_providers())
                print("First provider:", first)
            except Exception as e:
                print("CUDA session FAILED:", repr(e))
    else:
        _section("Trial / 试用")
        print("rapidocr det ONNX not found; skip session tests.")

    _section("Summary / 小结")
    if sys.platform == "win32" and "DmlExecutionProvider" in ap:
        if session_dml:
            print("DirectML is active for a test session — default Screen Translator setup should use GPU via DML.")
        else:
            print("DML listed but test session did not use DML; update GPU driver (WDDM, DX12) or check ORT logs.")
    elif "CUDAExecutionProvider" in ap and session_cuda:
        print("CUDA session test used CUDA EP.")
    else:
        print("Using CPU EP for OCR.")
        if sys.platform == "win32":
            print("If you expect DirectML: run `uv run screen-translator-repair-ort` (rapidocr may overwrite ORT DLLs).")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
