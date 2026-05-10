# HiDream Photo Studio

HiDream Photo Studio is a simple local web app for generating and editing images with HiDream O1 through ComfyUI. It hides the ComfyUI workflow complexity behind a compact photo-generation interface, while still running ComfyUI in the background as the model engine.

This repository contains only the app and launcher scripts. The heavy runtime pieces, including ComfyUI, the Python virtual environment, model files, caches, output images, logs, and pid files, are installed into a local runtime folder that is ignored by git.

## Features

- One command setup for the local runtime.
- One command start for both ComfyUI and the simple web app.
- One command stop for both services.
- Persistent model process: the model is loaded once and stays warm until the app/ComfyUI are stopped.
- Startup warmup screen/status while the model loads.
- Prompt-based image generation.
- Collapsed negative prompt field.
- Single or multiple reference photo uploads.
- Aspect ratio and resolution presets:
  - Square: `1:1`, `2048x2048`
  - Landscape: `16:9`, `2560x1440`
  - Portrait: `9:16`, `1440x2560`
  - Wide: `2.37:1`, `3104x1312`
- Fixed landscape preview frame with centered, contained images.
- Recent images popup.
- Persistent history across browser reloads.
- Reconnects to an in-progress generation after browser reload.
- Download button for the currently selected image.
- Generation duration is saved for newly generated images.
- Configurable ports, runtime path, mount path, state path, output path, and model name.

## Requirements

Recommended environment:

- Windows with WSL2, or a Linux machine.
- NVIDIA GPU with CUDA support.
- Around 12 GB VRAM minimum for the default Dev FP8 model.
- Enough disk space for the runtime image, ComfyUI, dependencies, model files, output images, and cache. The default runtime image size is `85G`.
- Internet access during setup.

Expected command-line tools:

- `bash`
- `git`
- `curl`
- `python3`
- `python3-venv`
- `pip`
- `ss`
- `mount`
- `swapon`
- `mkfs.ext4`
- `truncate`

On Debian/Ubuntu/WSL, `setup.sh` tries to install common missing packages with `apt-get` unless `HIDREAM_SKIP_APT=1` is set.

## Quick Start

From the repository folder:

```bash
./setup.sh
./start.sh
```

Then open:

- Photo Studio: http://127.0.0.1:7860
- ComfyUI: http://127.0.0.1:8188

To stop everything:

```bash
./stop.sh
```

To check whether services are running:

```bash
./scripts/hidream.sh status
```

To restart both services:

```bash
./scripts/hidream.sh restart
```

## Commands

### `./setup.sh`

Installs or updates the runtime. It is safe to run again if setup was interrupted or if dependencies need to be refreshed.

What it does:

- Creates a local ext4 runtime image if it does not already exist.
- Mounts the runtime image.
- Creates/enables a 32 GB swap file inside the runtime.
- Installs Linux packages with `apt-get` when available.
- Clones ComfyUI.
- Creates the ComfyUI Python virtual environment.
- Installs PyTorch CUDA wheels.
- Installs ComfyUI Python requirements.
- Clones the HiDream O1 ComfyUI custom node.
- Installs the HiDream custom node requirements.
- Writes the small warmup custom node used by the web app.
- Downloads the default HiDream O1 Dev FP8 model if it is missing.

### `./start.sh`

Starts both services:

- ComfyUI on port `8188`
- HiDream Photo Studio on port `7860`

The command starts both services detached in the background, records pid files in the runtime folder, and waits until the HTTP endpoints respond.

### `./stop.sh`

Stops both services:

- HiDream Photo Studio
- ComfyUI

It first tries a normal process stop. If a process does not stop, it is force-killed.

### `./scripts/hidream.sh status`

Shows whether each service is running and which local URL it is using.

### `./scripts/hidream.sh restart`

Runs stop, then start.

## How It Works

The app is a small `aiohttp` web server in `app/app.py`.

ComfyUI does the actual model execution. The web app sends ComfyUI API workflows to:

```text
http://127.0.0.1:8188
```

The browser talks only to the simple web app:

```text
http://127.0.0.1:7860
```

When the app starts:

1. The launcher mounts the runtime image.
2. The launcher enables swap.
3. The launcher starts ComfyUI if it is not already running.
4. The launcher starts the Photo Studio web app.
5. The web app checks ComfyUI.
6. The web app warms the HiDream model into GPU memory using a tiny custom ComfyUI node.
7. Once warm, generations avoid the cold model-load delay until ComfyUI is stopped.

Generated image files are stored in the ComfyUI output folder inside the runtime. The app also keeps a lightweight `history.json` in the configured state directory so recent jobs and selected images can survive browser reloads and app restarts.

## Runtime Folder

By default, the heavy runtime is stored under:

```bash
./.hidream-runtime
```

That folder is ignored by git.

Inside it, the scripts create:

```text
.hidream-runtime/
  hidream-runtime.ext4.img
  mount/
  logs/
  comfyui.pid
  simple-hidream.pid
```

Inside the mounted runtime image, the scripts use:

```text
runtime/
  ComfyUI/
  simple-hidream-state/
  hidream-swapfile
  .cache/
```

Do not commit the runtime folder, mounted runtime contents, model files, output images, logs, pid files, or caches.

## Configuration

All important machine-specific values can be changed with environment variables.

### Runtime Location

Use this if you want the heavy runtime somewhere outside the repo folder:

```bash
HIDREAM_RUNTIME_ROOT=/path/to/runtime ./setup.sh
HIDREAM_RUNTIME_ROOT=/path/to/runtime ./start.sh
```

### Runtime Image Path

```bash
HIDREAM_IMAGE=/path/to/hidream-runtime.ext4.img ./setup.sh
```

### Runtime Image Size

```bash
HIDREAM_IMAGE_SIZE=120G ./setup.sh
```

Default:

```text
85G
```

### Mount Path

```bash
HIDREAM_MOUNT=/path/to/mount ./start.sh
```

### Ports

```bash
HIDREAM_APP_PORT=7860 HIDREAM_COMFY_PORT=8188 ./start.sh
```

### Model Name

The default model is:

```text
HiDream-O1-Image-Dev-FP8
```

Override it with:

```bash
HIDREAM_MODEL_NAME=HiDream-O1-Image-Dev-FP8 ./start.sh
```

The default setup downloads:

```text
drbaph/HiDream-O1-Image-Dev-FP8
```

This is the practical default for GPUs around 12 GB VRAM. Larger BF16/FP16 variants require much more VRAM.

### App State Directory

```bash
HIDREAM_STATE_DIR=/path/to/state ./start.sh
```

This controls where `history.json` is stored.

### Output Directory

```bash
HIDREAM_OUTPUT_DIR=/path/to/ComfyUI/output ./start.sh
```

The launcher sets this automatically to the ComfyUI output directory in the runtime.

### Skip Apt

Use this if you do not want setup to run `apt-get`:

```bash
HIDREAM_SKIP_APT=1 ./setup.sh
```

## Typical Workflow

1. Run setup once:

   ```bash
   ./setup.sh
   ```

2. Start the app:

   ```bash
   ./start.sh
   ```

3. Open Photo Studio:

   ```text
   http://127.0.0.1:7860
   ```

4. Wait for the model to finish warming up.

5. Enter a prompt and choose an aspect ratio.

6. Optionally add one or more reference photos.

7. Click `Generate Photo`.

8. Use `Recent` to browse generated images.

9. Use `Download` to download the selected image.

10. Stop both services when finished:

    ```bash
    ./stop.sh
    ```

## Reference Photo Behavior

- No reference photo: standard text-to-image generation.
- One reference photo: image edit/transform style workflow.
- Multiple reference photos: the images are passed as references for the new output.
- `Keep first photo aspect` can preserve the first reference image aspect when one reference is used.

Reference image workflows can be slower and use more VRAM than pure text generation.

## History and Reload Behavior

The app stores recent job metadata in:

```text
history.json
```

The exact location depends on `HIDREAM_STATE_DIR`.

History allows:

- recent images to appear after browser reload,
- the app to reconnect to running jobs,
- completed image duration to be shown for newly generated images,
- old output files to be discovered from the ComfyUI output directory.

Older images that existed before duration tracking was added may not show a generation time.

## Logs

Logs are written under the runtime root:

```text
logs/
  comfyui.log
  photo-studio.log
```

Check these files if startup fails or if generation errors are not clear in the UI.

## Troubleshooting

### The app is not accessible

Check status:

```bash
./scripts/hidream.sh status
```

Check logs:

```bash
tail -n 100 ./.hidream-runtime/logs/photo-studio.log
tail -n 100 ./.hidream-runtime/logs/comfyui.log
```

If you use a custom `HIDREAM_RUNTIME_ROOT`, check the logs under that runtime folder instead.

### Port already in use

Use different ports:

```bash
HIDREAM_APP_PORT=7861 HIDREAM_COMFY_PORT=8189 ./start.sh
```

### Setup cannot mount the runtime image

Mounting an ext4 image requires root privileges. The script uses `sudo` when it is not already running as root.

If your environment does not support loop mounts, set `HIDREAM_MOUNT` to a real Linux filesystem path and adapt the runtime setup accordingly.

### Warmup takes a long time

Cold loading can take several minutes depending on disk speed, RAM, VRAM, and GPU. Once ComfyUI has loaded the model, later generations avoid the cold loading delay until ComfyUI is stopped.

### CUDA out of memory

Try:

- close other GPU-heavy apps,
- use the default Dev FP8 model,
- generate without reference photos,
- restart ComfyUI,
- reduce other GPU memory usage.

### Browser still shows old UI

The app sends no-cache headers, but if a browser still shows stale UI, force-refresh once:

```text
Ctrl+F5
```

## Repository Hygiene

Commit:

- `README.md`
- `.gitignore`
- `setup.sh`
- `start.sh`
- `stop.sh`
- `scripts/hidream.sh`
- `app/app.py`

Do not commit:

- `.hidream-runtime/`
- ext4 runtime images
- model files
- ComfyUI checkout
- virtual environments
- generated images
- logs
- caches
- pid files
- `history.json`

## Notes

This project is intentionally a thin local wrapper around ComfyUI. ComfyUI remains available at its own URL for advanced workflows, but the main day-to-day interface is the simpler Photo Studio app.
