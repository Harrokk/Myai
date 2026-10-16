#!/usr/bin/env bash
# Import-only disposable ARM64 voice wheel test. NEVER launch real models/audio.
set -euo pipefail
umask 077
ulimit -c 0

test "$(uname -m)" = "aarch64"
test "$(id -un)" = "arduino"
test -n "$RUNNER_TEMP"
test -n "$GITHUB_RUN_ID"
test "$RUNNER_TEMP" != /home/arduino/MyAI
test -d /home/arduino/MyAI/.venv

repo_root="$(pwd -P)"
case "$repo_root" in
  /home/arduino/MyAI|/home/arduino/MyAI/*)
    echo "MYAI_DISPOSABLE_STAGE_BLOCKED_PRODUCTION_CHECKOUT=true"
    exit 2
    ;;
esac
test -f requirements-voice-arm64-hashed.lock
test -f config/voice_arm64_cp312_wheels.lock.json

available_kib="$(df -Pk "$RUNNER_TEMP" | awk 'NR==2 {print $4}')"
memory_kib="$(awk '/MemAvailable:/ {print $2}' /proc/meminfo)"
test "$available_kib" -ge 6291456
test "$memory_kib" -ge 2097152

scratch="$RUNNER_TEMP/myai-disposable-voice-$GITHUB_RUN_ID"
test ! -e "$scratch"
mkdir -m 700 "$scratch"
cleanup() {
  if [[ "$scratch" == "$RUNNER_TEMP/myai-disposable-voice-$GITHUB_RUN_ID" &&
        -d "$scratch" && ! -L "$scratch" ]]; then
    rm -rf -- "$scratch"
  fi
  echo "MYAI_DISPOSABLE_VOICE_CLEANUP_ATTEMPTED=true"
}
trap cleanup EXIT
mkdir -m 700 "$scratch/home" "$scratch/tmp" "$scratch/cache" "$scratch/wheels"
test ! -e "$scratch/venv"
/usr/bin/python3 -m venv "$scratch/venv"

# Pinned, binary-only download. Any missing artifact -> FAIL CLOSED.
# Run pip in the disposable interpreter with private HOME and cache,
# never in the installed MyAI production interpreter.
timeout --signal=TERM --kill-after=3s 200s \
  env -i PATH=/usr/bin:/bin HOME="$scratch/home" \
    TMPDIR="$scratch/tmp" XDG_CACHE_HOME="$scratch/cache" \
    PYTHONDONTWRITEBYTECODE=1 PYTHONNOUSERSITE=1 \
    "$scratch/venv/bin/python" -m pip download \
  --disable-pip-version-check --no-input --quiet \
  --only-binary=:all: --require-hashes \
  --dest "$scratch/wheels" \
  -r requirements-voice-arm64-hashed.lock \
  > "$scratch/download.log" 2>&1 || {
    echo "MYAI_DISPOSABLE_VOICE_HASHED_DOWNLOAD_BLOCKED=true"
    exit 2
  }

cp config/voice_arm64_cp312_wheels.lock.json \
  "$scratch/wheels/wheelhouse.lock.json"
/usr/bin/python3 -B -m scripts.ventuno_voice_wheelhouse_gate \
  --wheelhouse "$scratch/wheels"

# Offline wheel-only installation in that same new venv; never production.
timeout --signal=TERM --kill-after=3s 240s \
  env -i PATH=/usr/bin:/bin HOME="$scratch/home" \
    TMPDIR="$scratch/tmp" XDG_CACHE_HOME="$scratch/cache" \
    PYTHONDONTWRITEBYTECODE=1 PYTHONNOUSERSITE=1 \
    HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 \
    "$scratch/venv/bin/python" -m pip install \
    --disable-pip-version-check --no-input \
    --no-index --no-cache-dir --only-binary=:all: --require-hashes \
    --find-links "$scratch/wheels" \
    -r "$repo_root/requirements-voice-arm64-hashed.lock" \
    > "$scratch/install.log" 2>&1 || {
      echo "MYAI_DISPOSABLE_VOICE_OFFLINE_INSTALL_BLOCKED=true"
      exit 2
    }

timeout --signal=TERM --kill-after=3s 30s \
  "$scratch/venv/bin/python" -m pip check \
  > "$scratch/pipcheck.log" 2>&1 || {
    echo "MYAI_DISPOSABLE_VOICE_DEPENDENCY_CLOSURE_BLOCKED=true"
    exit 2
  }
echo "MYAI_DISPOSABLE_VOICE_HASHED_VENV_INSTALLED=true"

for module in numpy av ctranslate2 webrtcvad sounddevice faster_whisper pyttsx3 onnxruntime; do
  if ! timeout --signal=TERM --kill-after=3s 35s \
    env -i PATH=/usr/bin:/bin HOME="$scratch/home" \
      TMPDIR="$scratch/tmp" XDG_CACHE_HOME="$scratch/cache" \
      PYTHONDONTWRITEBYTECODE=1 PYTHONNOUSERSITE=1 \
      HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 \
      HF_HUB_DISABLE_TELEMETRY=1 OMP_NUM_THREADS=2 \
      "$scratch/venv/bin/python" -I -B \
      "$repo_root/scripts/ventuno_disposable_voice_abi.py" \
      --module "$module"; then
    echo "MYAI_DISPOSABLE_VOICE_IMPORT_BLOCKED=$module"
    exit 2
  fi
done
echo "MYAI_DISPOSABLE_VOICE_IMPORT_ONLY_ABI_PASS=true"
echo "No actual mic, speaker, model, LLM, service, or NPU executed."
