#!/usr/bin/env bash
# Read-only queue progress. Pure text/dir inspection of what the sweep already writes to
# sweep_output/ -- no python process spun up, no dependency on the stdout log (which can
# get moved/trashed without affecting the run itself, since the ledger lives elsewhere).
cd "$(dirname "$0")/.." || exit 1

# name -> total cells, in queue order. Edit this if the queue composition changes.
declare -a NAMES=(europe_mktcap_weighted_6designs us_mktcap_weighted_6designs us_health_sdg_pre_post_2020)
declare -a TOTALS=(80 80 6)

running_mod=$(ps -eo command | grep -o 'New_Pipeline\.sweep --params New_Pipeline\.[a-zA-Z0-9_]*' | grep -o 'New_Pipeline\.[a-zA-Z0-9_]*$' | tail -1)
alive=$(pgrep -f run_sweeps.sh | head -1)

echo "[progress] $([ -n "$alive" ] && echo "RUNNING (pid $alive)" || echo "NOT RUNNING")"
[ -n "$running_mod" ] && echo "[progress] active params module: $running_mod"
echo

for i in "${!NAMES[@]}"; do
    name="${NAMES[$i]}"; total="${TOTALS[$i]}"
    dir=$(ls -td sweep_output/*_"$name" 2>/dev/null | head -1)
    done=0
    [ -n "$dir" ] && [ -f "$dir/results.jsonl" ] && done=$(grep -c . "$dir/results.jsonl")
    if [ "$done" -ge "$total" ] && [ "$done" -gt 0 ]; then state="DONE"
    elif [ -n "$dir" ] && [ "$done" -gt 0 ]; then state=">>> IN PROGRESS"
    else state="not started"
    fi
    printf "  [%-14s] %-34s %3d/%d\n" "$state" "$name" "$done" "$total"
done
