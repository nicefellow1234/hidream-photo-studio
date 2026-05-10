#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

RUNTIME_ROOT="${HIDREAM_RUNTIME_ROOT:-$PROJECT_DIR/.hidream-runtime}"
IMAGE="${HIDREAM_IMAGE:-$RUNTIME_ROOT/hidream-runtime.ext4.img}"
IMAGE_SIZE="${HIDREAM_IMAGE_SIZE:-85G}"
MOUNT="${HIDREAM_MOUNT:-$RUNTIME_ROOT/mount}"
APP_ROOT="$MOUNT/runtime"
COMFY_DIR="$APP_ROOT/ComfyUI"
COMFY_VENV="$COMFY_DIR/.venv"
CUSTOM_NODE_DIR="$COMFY_DIR/custom_nodes/HiDream_O1-ComfyUI"
WARMUP_NODE_DIR="$COMFY_DIR/custom_nodes/simple_hidream_warmup"
MODEL_DIR="$COMFY_DIR/models/diffusion_models/HiDream-O1-Image-Dev-fp8"
STATE_DIR="$APP_ROOT/simple-hidream-state"
SWAP_FILE="$APP_ROOT/hidream-swapfile"
LOG_DIR="$RUNTIME_ROOT/logs"
COMFY_PID_FILE="$RUNTIME_ROOT/comfyui.pid"
APP_PID_FILE="$RUNTIME_ROOT/simple-hidream.pid"
COMFY_PORT="${HIDREAM_COMFY_PORT:-8188}"
APP_PORT="${HIDREAM_APP_PORT:-7860}"

log() {
  printf '[hidream] %s\n' "$*"
}

die() {
  printf '[hidream] ERROR: %s\n' "$*" >&2
  exit 1
}

as_root() {
  if [[ "${EUID:-$(id -u)}" -eq 0 ]]; then
    "$@"
  elif command -v sudo >/dev/null 2>&1; then
    sudo "$@"
  else
    die "Need root privileges for: $*"
  fi
}

need_command() {
  command -v "$1" >/dev/null 2>&1 || die "Missing command: $1"
}

ensure_host_deps() {
  if [[ "${HIDREAM_SKIP_APT:-0}" == "1" ]]; then
    return
  fi
  if ! command -v apt-get >/dev/null 2>&1; then
    return
  fi
  log "Installing/checking WSL packages..."
  as_root apt-get update
  as_root apt-get install -y git curl python3 python3-venv python3-pip git-lfs
}

ensure_image() {
  mkdir -p "$RUNTIME_ROOT"
  if [[ -f "$IMAGE" ]]; then
    return
  fi
  need_command truncate
  need_command mkfs.ext4
  log "Creating ext4 runtime image: $IMAGE ($IMAGE_SIZE)"
  truncate -s "$IMAGE_SIZE" "$IMAGE"
  as_root mkfs.ext4 -F "$IMAGE" >/dev/null
}

ensure_mount() {
  ensure_image
  mkdir -p "$MOUNT"
  if mountpoint -q "$MOUNT"; then
    return
  fi
  log "Mounting runtime image at $MOUNT"
  as_root mount -o loop,noatime "$IMAGE" "$MOUNT"
}

ensure_swap() {
  mkdir -p "$APP_ROOT"
  if swapon --show=NAME | grep -qx "$SWAP_FILE"; then
    return
  fi
  if [[ ! -f "$SWAP_FILE" ]]; then
    log "Creating 32G swap file inside fast runtime..."
    as_root fallocate -l 32G "$SWAP_FILE"
    as_root chmod 600 "$SWAP_FILE"
    as_root mkswap "$SWAP_FILE" >/dev/null
  fi
  log "Enabling HiDream swap file..."
  as_root swapon "$SWAP_FILE"
}

export_runtime_env() {
  export HF_HOME="$APP_ROOT/.cache/huggingface"
  export XDG_CACHE_HOME="$APP_ROOT/.cache"
  export PIP_CACHE_DIR="$APP_ROOT/.cache/pip"
  export UV_CACHE_DIR="$APP_ROOT/.cache/uv"
  export PYTORCH_CUDA_ALLOC_CONF="expandable_segments:True"
  export HIDREAM_COMFY_URL="http://127.0.0.1:$COMFY_PORT"
  export HIDREAM_OUTPUT_DIR="$COMFY_DIR/output"
  export HIDREAM_STATE_DIR="$STATE_DIR"
  export HIDREAM_APP_PORT="$APP_PORT"
  mkdir -p "$HF_HOME" "$XDG_CACHE_HOME" "$PIP_CACHE_DIR" "$UV_CACHE_DIR" "$STATE_DIR" "$LOG_DIR"
}

write_warmup_node() {
  mkdir -p "$WARMUP_NODE_DIR"
  cat > "$WARMUP_NODE_DIR/__init__.py" <<'PY'
class SimpleHiDreamWarmup:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"model": ("HIDREAM_O1_MODEL",)}}

    RETURN_TYPES = ()
    FUNCTION = "warmup"
    OUTPUT_NODE = True
    CATEGORY = "HiDream O1"

    def warmup(self, model):
        inference_model = model.load_for_inference()
        model.resolve_attention_backend()
        _ = getattr(inference_model, "device", None)
        return {}


NODE_CLASS_MAPPINGS = {
    "SimpleHiDreamWarmup": SimpleHiDreamWarmup,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "SimpleHiDreamWarmup": "Simple HiDream Warmup",
}
PY
}

setup_runtime() {
  ensure_host_deps
  ensure_mount
  ensure_swap
  export_runtime_env

  if [[ ! -d "$COMFY_DIR/.git" ]]; then
    log "Cloning ComfyUI..."
    git clone https://github.com/comfyanonymous/ComfyUI.git "$COMFY_DIR"
  fi

  if [[ ! -x "$COMFY_VENV/bin/python" ]]; then
    log "Creating ComfyUI Python venv..."
    python3 -m venv "$COMFY_VENV"
  fi

  log "Installing Python dependencies..."
  "$COMFY_VENV/bin/python" -m pip install --upgrade pip setuptools wheel
  "$COMFY_VENV/bin/python" -m pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121
  "$COMFY_VENV/bin/python" -m pip install -r "$COMFY_DIR/requirements.txt"
  "$COMFY_VENV/bin/python" -m pip install aiohttp huggingface_hub[hf_transfer]

  if [[ ! -d "$CUSTOM_NODE_DIR/.git" ]]; then
    log "Cloning HiDream O1 ComfyUI node..."
    git clone https://github.com/Saganaki22/HiDream_O1-ComfyUI.git "$CUSTOM_NODE_DIR"
  fi
  if [[ -f "$CUSTOM_NODE_DIR/requirements.txt" ]]; then
    "$COMFY_VENV/bin/python" -m pip install -r "$CUSTOM_NODE_DIR/requirements.txt"
  fi

  write_warmup_node

  if [[ ! -f "$MODEL_DIR/model.safetensors" ]]; then
    log "Downloading HiDream O1 Dev FP8 model. This is large and can take a while..."
    mkdir -p "$MODEL_DIR"
    MODEL_DIR="$MODEL_DIR" HF_HUB_ENABLE_HF_TRANSFER=1 "$COMFY_VENV/bin/python" - <<'PY'
import os
from huggingface_hub import snapshot_download

snapshot_download(
    repo_id="drbaph/HiDream-O1-Image-Dev-FP8",
    local_dir=os.environ["MODEL_DIR"],
    local_dir_use_symlinks=False,
)
PY
  else
    log "Model already installed: $MODEL_DIR"
  fi

  log "Setup complete."
}

pid_for_port() {
  local port="$1"
  ss -ltnp "sport = :$port" 2>/dev/null | sed -n 's/.*pid=\([0-9]\+\).*/\1/p' | head -n 1
}

is_running() {
  local pid="${1:-}"
  [[ -n "$pid" ]] && kill -0 "$pid" >/dev/null 2>&1
}

wait_http() {
  local url="$1"
  local seconds="$2"
  for _ in $(seq 1 "$seconds"); do
    if curl -fsS --max-time 3 "$url" >/dev/null 2>&1; then
      return 0
    fi
    sleep 1
  done
  return 1
}

start_comfyui() {
  local port_pid
  port_pid="$(pid_for_port "$COMFY_PORT")"
  if [[ -n "$port_pid" ]]; then
    echo "$port_pid" > "$COMFY_PID_FILE"
    log "ComfyUI already running on port $COMFY_PORT (pid $port_pid)."
    return
  fi

  [[ -x "$COMFY_VENV/bin/python" ]] || die "ComfyUI venv missing. Run: $PROJECT_DIR/setup.sh"
  log "Starting ComfyUI on http://127.0.0.1:$COMFY_PORT ..."
  (
    cd "$COMFY_DIR"
    setsid "$COMFY_VENV/bin/python" -u main.py --listen 0.0.0.0 --port "$COMFY_PORT" \
      > "$LOG_DIR/comfyui.log" 2>&1 < /dev/null &
    echo $! > "$COMFY_PID_FILE"
  )
  wait_http "http://127.0.0.1:$COMFY_PORT/system_stats" 120 || die "ComfyUI did not become ready. See $LOG_DIR/comfyui.log"
}

start_app() {
  local port_pid
  port_pid="$(pid_for_port "$APP_PORT")"
  if [[ -n "$port_pid" ]]; then
    echo "$port_pid" > "$APP_PID_FILE"
    log "Photo Studio already running on port $APP_PORT (pid $port_pid)."
    return
  fi

  log "Starting HiDream Photo Studio on http://127.0.0.1:$APP_PORT ..."
  (
    cd "$PROJECT_DIR/app"
    setsid "$COMFY_VENV/bin/python" -u app.py \
      > "$LOG_DIR/photo-studio.log" 2>&1 < /dev/null &
    echo $! > "$APP_PID_FILE"
  )
  wait_http "http://127.0.0.1:$APP_PORT/api/health" 60 || die "Photo Studio did not become ready. See $LOG_DIR/photo-studio.log"
}

start_all() {
  ensure_mount
  ensure_swap
  export_runtime_env
  start_comfyui
  start_app
  log "Ready:"
  log "  Photo Studio: http://127.0.0.1:$APP_PORT"
  log "  ComfyUI:      http://127.0.0.1:$COMFY_PORT"
}

stop_one() {
  local name="$1"
  local pid_file="$2"
  local port="$3"
  local pid=""
  if [[ -f "$pid_file" ]]; then
    pid="$(cat "$pid_file" 2>/dev/null || true)"
  fi
  if ! is_running "$pid"; then
    pid="$(pid_for_port "$port")"
  fi
  if [[ -z "$pid" ]]; then
    rm -f "$pid_file"
    log "$name is not running."
    return
  fi

  log "Stopping $name (pid $pid)..."
  kill "$pid" >/dev/null 2>&1 || true
  for _ in $(seq 1 20); do
    if ! is_running "$pid"; then
      rm -f "$pid_file"
      return
    fi
    sleep 0.5
  done
  log "$name did not stop gracefully; forcing it."
  kill -9 "$pid" >/dev/null 2>&1 || true
  rm -f "$pid_file"
}

stop_all() {
  stop_one "Photo Studio" "$APP_PID_FILE" "$APP_PORT"
  stop_one "ComfyUI" "$COMFY_PID_FILE" "$COMFY_PORT"
}

status_all() {
  local app_pid comfy_pid
  app_pid="$(pid_for_port "$APP_PORT")"
  comfy_pid="$(pid_for_port "$COMFY_PORT")"
  if [[ -n "$app_pid" ]]; then
    log "Photo Studio: running on http://127.0.0.1:$APP_PORT (pid $app_pid)"
  else
    log "Photo Studio: stopped"
  fi
  if [[ -n "$comfy_pid" ]]; then
    log "ComfyUI: running on http://127.0.0.1:$COMFY_PORT (pid $comfy_pid)"
  else
    log "ComfyUI: stopped"
  fi
}

case "${1:-}" in
  setup)
    setup_runtime
    ;;
  start)
    start_all
    ;;
  stop)
    stop_all
    ;;
  restart)
    stop_all
    start_all
    ;;
  status)
    status_all
    ;;
  *)
    cat <<EOF
Usage:
  $PROJECT_DIR/setup.sh          Install/update runtime dependencies and model
  $PROJECT_DIR/start.sh          Start ComfyUI and HiDream Photo Studio
  $PROJECT_DIR/stop.sh           Stop both apps
  $PROJECT_DIR/scripts/hidream.sh status
  $PROJECT_DIR/scripts/hidream.sh restart

Runtime defaults:
  Runtime root: $RUNTIME_ROOT
  Runtime mount: $MOUNT
  App URL:      http://127.0.0.1:$APP_PORT
  ComfyUI URL:  http://127.0.0.1:$COMFY_PORT
EOF
    exit 2
    ;;
esac
