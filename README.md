# Screen Translator

Screen Translator captures your display (full virtual desktop or a chosen rectangle), runs **on-screen text recognition (OCR)** on Chinese text, translates it to **English**, and shows the result as an **overlay** on top of a copy of the screenshot. It is intended for **Windows** and uses global hotkeys plus a tray icon.

## How it works

1. **Global hotkeys (Windows)**  
   Hotkeys are registered with the Win32 API **`RegisterHotKey`**. They run in a small background thread that processes **`WM_HOTKEY`** messages. This does **not** attach to, inject into, or read memory from other applications (including games).

2. **Screen capture**  
   The image comes from **`mss`**: it grabs pixels from the **monitor / desktop output** (full screen or a user-selected region). That is the same image you would see on screen—it is **not** read from another process’s address space.

3. **OCR**  
   **RapidOCR** with **ONNX Runtime** detects text regions and recognizes characters. On Windows, **DirectML** can be used when available. All processing happens on the **bitmap** produced by the capture step.

4. **Translation**  
   Recognized Chinese segments are translated to English via **`deep-translator`** (Google’s web translation endpoint). Multiple lines can be **batched** into fewer HTTP requests (see `TRANSLATE_BATCH_*` in `screen_translator/config.py`).

5. **Result window**  
   A **tkinter** window shows the screenshot with English text drawn over the detected boxes. You can use **fullscreen** or **windowed** mode (e.g. double-click to toggle). Processing runs on a **background thread** so the UI stays responsive.

6. **Tray**  
   **`pystray`** provides a tray icon; you can exit the app from there.

End-to-end data flow:

```text
Hotkey → capture pixels (mss) → OCR (RapidOCR / ONNX) → translate (HTTPS) → draw overlay → show window
```

## Why this does not interact with game memory (and what “safe” means here)

From a **technical** standpoint, this application:

- Does **not** call **`OpenProcess`**, **`ReadProcessMemory`**, or similar APIs on a game or any other third-party process.
- Does **not** inject DLLs or code into a game.
- Does **not** hook the game’s graphics API to read internal render targets; it only samples **what is already displayed** on the monitor.

**In that sense**, using Screen Translator while playing a game does **not** work by reading or modifying the game’s memory, which is the usual concern for “memory cheats” and related bans.

## Requirements

- **Windows** (global hotkeys use `user32.RegisterHotKey` only).
- Python **3.10+** and dependencies listed in `pyproject.toml` (e.g. `mss`, `Pillow`, `rapidocr-onnxruntime`, `onnxruntime-directml` on Windows, `deep-translator`, `pystray`).

## Running from source

```bash
uv sync
uv run python main.py
```

If DirectML / ONNX Runtime DLLs conflict after install, on Windows you can try:

```bash
uv run screen-translator-repair-ort
```

## Packaging (PyInstaller)

The repo includes `main.spec` (one-folder, console for debugging) and `main-onefile.spec` (single executable). Build with PyInstaller using the corresponding `.spec` file.

## Default hotkeys

These are defined in `screen_translator/config.py` and must stay consistent with `screen_translator/hotkeys.py` on Windows:

| Shortcut | Action |
|----------|--------|
| **Ctrl+Shift+1** | Capture the full virtual desktop and translate |
| **Ctrl+Shift+2** | Select a region, then translate |

## License

Add your license here if applicable.
