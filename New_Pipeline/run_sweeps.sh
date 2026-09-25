#!/usr/bin/env bash
# Queue several sweeps back to back, unattended, with a live progress bar.
#
#   ./New_Pipeline/run_sweeps.sh New_Pipeline.sweep_parameters_US New_Pipeline.sweep_parameters_EU
#
# Each argument is a dotted module with the same shape as
# New_Pipeline/sweep_parameters_US.py (SWEEP_NAME / GRID / EXPLICIT / FIXED). Each gets its
# OWN sweep_output/<stamp>_<SWEEP_NAME>/ folder -- so two params modules produce two
# separate results.pdf/.csv/.xlsx.
#
# Deliberately NOT `&&`: a sweep that dies must not cancel the ones behind it. Each exit
# status is recorded and the script exits non-zero if any failed, so the log says what
# happened without you having to watch it.
#
# THE PROGRESS BAR. Each sweep's full stdout still goes to its log; the terminal instead
# gets one self-updating line per sweep, driven by the sweep's OWN ledger
# (<outdir>/results.jsonl, one line per completed cell). That file is the same thing
# --resume reads, so the count is the truth rather than a guess parsed out of stdout.
#
# It is also why the bar can sit at 0/64 for the first few minutes: a cell is only counted
# once it has COMPLETED and been appended. Under --jobs N the first N cells finish at
# roughly the same moment, so expect the bar to move in steps of N, not one at a time.
#
# `caffeinate -is` keeps the Mac awake for the whole queue; without it a sleeping laptop
# suspends the run midway. Skipped automatically if the binary is absent (i.e. on Linux).
set -u

PY="${PY:-.venv/bin/python}"          # the venv interpreter -- `python3` is not it
# Extra flags forwarded to every sweep, e.g. SWEEP_ARGS="--jobs 1" ./run_sweeps.sh ...
# Word-split into an array so an unset/empty value passes NO argument at all.
read -r -a EXTRA <<< "${SWEEP_ARGS:-}"
LOG_DIR="${LOG_DIR:-sweep_output/_logs}"
POLL="${POLL:-5}"                     # seconds between progress refreshes
mkdir -p "$LOG_DIR"

[ $# -gt 0 ] || { echo "usage: $0 <params.module> [params.module ...]" >&2; exit 2; }

CAFF=()
command -v caffeinate >/dev/null 2>&1 && CAFF=(caffeinate -is)

# Render one progress line IN PLACE. \r returns to column 0 and the trailing blanks wipe
# whatever the previous, possibly longer, line left behind -- without them a shrinking ETA
# leaves stale digits on screen.
bar() {
    local label="$1" done="$2" total="$3" started="$4"
    local width=28 filled=0 pct=0 elapsed eta="--" bar_str=""
    elapsed=$(( $(date +%s) - started ))
    if [ "$total" -gt 0 ]; then
        pct=$(( done * 100 / total ))
        filled=$(( done * width / total ))
        # ETA from the average cell so far; meaningless until at least one has landed.
        [ "$done" -gt 0 ] && eta="$(( (elapsed * (total - done) / done + 59) / 60 ))m"
    fi
    local i
    for ((i = 0; i < width; i++)); do
        if [ "$i" -lt "$filled" ]; then bar_str+="#"; else bar_str+="."; fi
    done
    printf "\r  %-34.34s %3d/%-4d %3d%% [%s] %dm elapsed, eta %s      " \
        "$label" "$done" "$total" "$pct" "$bar_str" "$((elapsed / 60))" "$eta"
}

rc=0
for mod in "$@"; do
    stamp=$(date -u +%Y%m%dT%H%M%SZ)
    log="$LOG_DIR/${stamp}_${mod##*.}.log"
    echo "[queue] $(date -u +%H:%M:%SZ) starting $mod  -> $log"

    "${CAFF[@]}" "$PY" -m New_Pipeline.sweep --params "$mod" ${EXTRA+"${EXTRA[@]}"} \
        >"$log" 2>&1 &
    pid=$!
    started=$(date +%s)

    # The sweep prints its plan before the first cell runs; both numbers come from there.
    # Until they appear (or if they never do, e.g. --dry-run) the bar just shows 0/0.
    total=0; outdir=""; label="${mod##*.}"
    while kill -0 "$pid" 2>/dev/null; do
        if [ "$total" -eq 0 ] && [ -s "$log" ]; then
            total=$(grep -m1 -oE '[0-9]+ experiment\(s\) planned' "$log" | grep -oE '^[0-9]+')
            : "${total:=0}"
            outdir=$(grep -m1 -oE 'output -> [^ ]+' "$log" | sed 's|output -> ||')
            [ -n "$outdir" ] && label=$(basename "$outdir")
        fi
        done_n=0
        [ -n "$outdir" ] && [ -f "$outdir/results.jsonl" ] &&
            done_n=$(grep -c . "$outdir/results.jsonl" 2>/dev/null || echo 0)
        bar "$label" "$done_n" "$total" "$started"
        sleep "$POLL"
    done

    wait "$pid"; status=$?
    [ "$total" -gt 0 ] && bar "$label" "$total" "$total" "$started"
    printf "\r%-110s\r" ""          # wipe the bar before the verdict line
    if [ $status -eq 0 ]; then
        echo "[queue] $(date -u +%H:%M:%SZ) finished $mod  ($(( ($(date +%s) - started) / 60 ))m)"
    else
        echo "[queue] $(date -u +%H:%M:%SZ) FAILED   $mod (exit $status) -- see $log"
        rc=1
    fi
done

echo "[queue] all done; logs in $LOG_DIR/"
exit $rc
