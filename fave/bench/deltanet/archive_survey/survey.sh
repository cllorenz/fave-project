#!/usr/bin/env bash

# Survey the WHOLE Delta-net archive -- the nine members that are not vendored
# as well as the two that are (CLOUD_BENCH_PLAN.md §2.14, D8).
#
# This exists because §2.14's figures would otherwise rest on shell history,
# which is the exact debt D0 records settling: the vendored traces had been
# extracted with ad-hoc `tar` commands "existing nowhere in the repository".
# Re-deriving anything here needs the archive re-supplied -- it is 9.6 GB and
# deliberately not kept (owner, 2026-09-18) -- but the METHOD is kept.
#
# Nothing is extracted to disk. Each member is streamed through a reader by
# `tar --to-command`, so a 16 GB member costs time and no space. One full
# decompression pass is ~5m43s on the 2026-09-25 box; because tar is
# sequential, reaching a member costs everything before it, not its own size.
#
#   opmix   -- op mix only, no dict, so no member is ever truncated. This is
#              what answers "insert-only, or removals too?".
#   replay  -- replay to the terminal FIB and emit it in the trace's own
#              format, so `trace.py` consumes the result unchanged. Holds one
#              live key per rule, so it is the pass with a memory ceiling.
#   phase   -- where the insert phase ends relative to the first withdrawal,
#              whether field 4 is monotone, and how many routers carry each
#              prefix. Dicts over prefixes and routers only, so no ceiling
#              that any member reaches (added 2026-09-28).
#   revisions -- does any (router, prefix) occur twice in the INSERT BLOCK
#              (the lines before the first withdrawal)? A disk-backed
#              `sort -u` rather than a dict, so it has no ceiling either, and
#              it is what replay's 45M-key cap could not answer for inet,
#              rf3257 and rf6461 (added 2026-09-28).
#
# Usage:  ./survey.sh opmix|replay|phase|revisions  <archive.tar.gz>  <output-dir>

set -euo pipefail

MODE="${1:?usage: survey.sh opmix|replay|phase|revisions <archive.tar.gz> <output-dir>}"
ARCHIVE="${2:?missing archive path}"
OUTDIR="${3:?missing output directory}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

case "$MODE" in
    opmix|replay|phase|revisions) ;;
    *) echo "mode must be opmix, replay, phase or revisions, not '$MODE'" >&2; exit 2 ;;
esac
mkdir -p "$OUTDIR"

# The per-member reader. tar runs it once per member with TAR_FILENAME set.
export SURVEY_MODE="$MODE" SURVEY_OUT="$OUTDIR" SURVEY_AWK="$HERE"
READER="$(mktemp)"
trap 'rm -f "$READER"' EXIT
cat > "$READER" <<'READER_EOF'
#!/usr/bin/env bash
set -euo pipefail
base="$(basename "$TAR_FILENAME")"
case "$base" in
    *.csv) ;;
    *) cat > /dev/null; exit 0 ;;     # the directory entry
esac
start=$(date +%s)
if [ "$SURVEY_MODE" = "opmix" ]; then
    mawk -f "$SURVEY_AWK/opmix.awk" > "$SURVEY_OUT/$base.opmix"
    echo "seconds=$(( $(date +%s) - start ))" >> "$SURVEY_OUT/$base.opmix"
elif [ "$SURVEY_MODE" = "revisions" ]; then
    # "router,prefix,next_hop" for every insert before the first withdrawal,
    # sorted -u to a temp file, then counted twice: distinct lines, and
    # distinct (router,prefix) keys. Under LC_ALL=C a key's lines sort
    # contiguously (',' is below every prefix character), so `uniq` on the
    # key columns counts keys exactly.
    r="$SURVEY_OUT/$base.revisions"
    # Only `+` lines are rules: rf1755.links.csv ends in `]a,b` edge lines.
    mawk -F, -v lines="$r.lines" '/^-/ { exit }
        /^\+/ { n++; print $2 "," substr($1, 2) "," $3 }
        END { print n + 0 > lines }' \
        | LC_ALL=C sort -u -T "$SURVEY_OUT" -S 3G --parallel=2 -o "$r.sorted"
    cat > /dev/null      # drain the member past the cut
    lines=$(cat "$r.lines")
    keys=$(cut -d, -f1,2 "$r.sorted" | LC_ALL=C uniq | wc -l)
    { echo "block_lines=$lines"
      echo "distinct_rules=$(wc -l < "$r.sorted")"
      echo "distinct_keys=$keys"
      echo "revisions=$(( lines - keys ))"
      echo "seconds=$(( $(date +%s) - start ))"; } > "$r"
    rm -f "$r.lines" "$r.sorted"
elif [ "$SURVEY_MODE" = "phase" ]; then
    mawk -f "$SURVEY_AWK/phase.awk" > "$SURVEY_OUT/$base.phase"
    echo "seconds=$(( $(date +%s) - start ))" >> "$SURVEY_OUT/$base.phase"
else
    mawk -v census="$SURVEY_OUT/$base.census" -f "$SURVEY_AWK/replay.awk" \
        | LC_ALL=C sort -T "$SURVEY_OUT" -S 512M > "$SURVEY_OUT/$base.snapshot.csv"
    echo "seconds=$(( $(date +%s) - start ))" >> "$SURVEY_OUT/$base.census"
fi
READER_EOF
chmod +x "$READER"

echo "start=$(date -Is)" | tee "$OUTDIR/_START"
tar -xzf "$ARCHIVE" --to-command="$READER"
echo "end=$(date -Is)" | tee "$OUTDIR/_END"
