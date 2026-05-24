#!/usr/bin/env bash
set -euo pipefail

workdir=""
warmup=""
sim=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --warmup)
      warmup="${2:?--warmup requires a value}"
      shift 2
      ;;
    --sim)
      sim="${2:?--sim requires a value}"
      shift 2
      ;;
    -*)
      echo "Unknown option: $1" >&2
      echo "Usage: $0 <workdir> [--warmup N] [--sim N]" >&2
      exit 1
      ;;
    *)
      workdir="$1"
      shift
      ;;
  esac
done

if [[ -z "$workdir" ]]; then
  echo "Usage: $0 <workdir> [--warmup N] [--sim N]" >&2
  exit 1
fi

run_args=(-c ../ChampSim -t ../traces -o "${workdir}")
[[ -n "$warmup" ]] && run_args+=(--warmup "$warmup")
[[ -n "$sim" ]] && run_args+=(--sim "$sim")

python3 ./scripts/run_all_replacements.py "${run_args[@]}"
python3 ./scripts/visualize_replacement_results.py \
 --csv ${workdir}/replacement_results.csv \
 --ipc-png ${workdir}/replacement_ipc.png \
 --l2-miss-rate-png ${workdir}/replacement_l2_miss_rate.png \
 --gmean-md ${workdir}/replacement_gmean.md
