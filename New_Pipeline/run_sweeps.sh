#!/usr/bin/env bash
# Queue several sweeps back to back, unattended.
#
#   ./New_Pipeline/run_sweeps.sh New_Pipeline.sweep_params_a New_Pipeline.sweep_params_b ...
#
# Each argument is a dotted module with the same shape as New_Pipeline/sweep_parameters.py
# (SWEEP_NAME / GRID / EXPLICIT / FIXED). Each gets its OWN sweep_output/<stamp>_<SWEEP_NAME>/
# folder -- so three params modules produce three separate results.pdf/.csv/.xlsx.
#
# Deliberately NOT `&&`: a sweep that dies must not cancel the ones behind it. Each exit
# status is recorded and the script exits non-zero if any failed, so the log says what
# happened without you having to watch it.
#
# `caffeinate -is` keeps the Mac awake for the whole queue; without it a sleeping laptop
# suspends the run midway. Drop it on Linux.
set -u

PY="${PY:-.venv/bin/python}"          # the venv interpreter -- `python3` is not it
# Extra flags forwarded to every sweep, e.g. SWEEP_ARGS="--jobs 1" ./run_sweeps.sh ...
# Word-split into an array so an unset/empty value passes NO argument at all.
read -r -a EXTRA <<< "${SWEEP_ARGS:-}"
LOG_DIR="${LOG_DIR:-sweep_output/_logs}"
mkdir -p "$LOG_DIR"

[ $# -gt 0 ] || { echo "usage: $0 <params.module> [params.module ...]" >&2; exit 2; }

rc=0
for mod in "$@"; do
    stamp=$(date -u +%Y%m%dT%H%M%SZ)
    log="$LOG_DIR/${stamp}_${mod##*.}.log"
    echo "[queue] $(date -u +%H:%M:%SZ) starting $mod  -> $log"
    "$PY" -m New_Pipeline.sweep --params "$mod" ${EXTRA+"${EXTRA[@]}"} >"$log" 2>&1
    status=$?
    if [ $status -eq 0 ]; then
        echo "[queue] $(date -u +%H:%M:%SZ) finished $mod"
    else
        echo "[queue] $(date -u +%H:%M:%SZ) FAILED   $mod (exit $status) -- see $log"
        rc=1
    fi
done

echo "[queue] all done; logs in $LOG_DIR/"
exit $rc
