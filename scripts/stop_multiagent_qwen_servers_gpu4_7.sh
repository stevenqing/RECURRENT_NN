#!/usr/bin/env bash
set -euo pipefail

ROOT=/home/aiscuser/RECURRENT_NN
OUT="$ROOT/results/multiagent_overnight_gpu4_7/servers"
shopt -s nullglob
for pidfile in "$OUT"/*.pid; do
  pid=$(cat "$pidfile")
  if [[ -r "/proc/$pid/cmdline" ]]; then
    command=$(tr '\0' ' ' <"/proc/$pid/cmdline")
    if [[ "$command" == *"vllm.entrypoints.openai.api_server"* ]] && [[ "$command" == *"810"* ]]; then
      kill "$pid"
      echo "stopped owned vLLM pid=$pid"
    else
      echo "refusing to stop pid=$pid because command is not the owned multi-agent vLLM server" >&2
    fi
  fi
done
