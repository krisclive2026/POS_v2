# Packaging POS for Raspberry Pi (Cross-Compilation via Docker)

You requested to turn this web application into a single executable that you can run on the Raspberry Pi, and you understandably want the final executable ready to go, rather than having to compile it yourself on the Pi.

## The Revised Strategy

Since your Windows laptop has Docker installed, we can use Docker's multi-architecture support (QEMU) to emulate an ARM64 Linux environment (the Raspberry Pi architecture) right here on your laptop. 

We will run PyInstaller *inside* this emulated ARM container to bundle the Python interpreter, FastAPI, and the HTML/CSS into a single ARM Linux executable. When the container finishes, it will deposit the final executable into a `dist/` folder on your laptop, which you can then just copy to your Pi via a USB drive or network.

## User Review Required

Does this cross-compilation approach sound better? It completely handles the building process for you.

## Proposed Changes

### [NEW] `pos_poc/Dockerfile.build`
A special Dockerfile starting with `--platform=linux/arm64 python:3.11-slim`. It will:
1. Install PyInstaller.
2. Run PyInstaller to bundle the application into a single binary.

### [NEW] `pos_poc/build_executable.bat`
A Windows batch script that you can double-click to:
1. Build the ARM container.
2. Run the container to extract the final `pos_app` binary to your local `c:\Users\ssk-ssd\Documents\AntiGravity\pos_poc\dist\` folder.

### [MODIFY] `pos_poc/app/main.py`
When PyInstaller bundles static files, they are extracted to a temporary directory at runtime (`sys._MEIPASS`). We need to add a small pathing check to the FastAPI app so it knows how to find the static files when it is running as a packaged executable.

## Verification Plan
1. I will execute `build_executable.bat` using the terminal.
2. I will verify that an ARM64 binary named `pos_app` appears in your `dist/` folder.
