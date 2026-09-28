#!/usr/bin/env bash

# Are the vendored `*-only-inserts.csv` the OPENING insert block of their full
# airtel trace? (CLOUD_BENCH_PLAN.md §2.14, added 2026-09-28.)
#
# `phase` found that both full airtel traces begin with an insert-only block
# whose first withdrawal is at line 38,101 -- and 38,100 is the size of both
# vendored files. This tests the obvious reading as sets: take each full
# trace's lines BEFORE ITS FIRST WITHDRAWAL (the block's length is measured
# here, not assumed to be 38,100), sort, and compare with the sorted vendored
# file. Order is reported separately, because the two files need not list the
# same rules in the same order to hold the same FIB.
#
# Streams, like survey.sh; `--occurrence` stops tar once both members are read,
# so this costs ~1.5 min rather than a full pass.
#
# Usage:  ./opening.sh <archive.tar.gz> <output-dir>

set -euo pipefail

ARCHIVE="${1:?usage: opening.sh <archive.tar.gz> <output-dir>}"
OUTDIR="${2:?missing output directory}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TRACES="$HERE/../traces"
mkdir -p "$OUTDIR"

export OPENING_OUT="$OUTDIR"
READER="$(mktemp)"
trap 'rm -f "$READER"' EXIT
cat > "$READER" <<'READER_EOF'
#!/usr/bin/env bash
set -euo pipefail
base="$(basename "$TAR_FILENAME")"
# Stop at the first withdrawal, then drain so tar does not see a broken pipe.
{ mawk '/^-/ { exit } { print }' > "$OPENING_OUT/$base.opening"; cat > /dev/null; }
READER_EOF
chmod +x "$READER"

tar -xzf "$ARCHIVE" --occurrence=1 --to-command="$READER" \
    nsdi-data-sets/airtel1.csv nsdi-data-sets/airtel2.csv

for n in 1 2; do
    opening="$OUTDIR/airtel$n.csv.opening"
    vendored="$TRACES/airtel$n-only-inserts.csv"
    LC_ALL=C sort "$opening"  > "$OUTDIR/airtel$n.opening.sorted"
    LC_ALL=C sort "$vendored" > "$OUTDIR/airtel$n.vendored.sorted"
    echo "airtel$n:"
    echo "  opening_block_lines=$(wc -l < "$opening")"
    echo "  sorted_sha256_opening=$(sha256sum < "$OUTDIR/airtel$n.opening.sorted" | cut -d' ' -f1)"
    echo "  sorted_sha256_vendored=$(sha256sum < "$OUTDIR/airtel$n.vendored.sorted" | cut -d' ' -f1)"
    echo "  rows_only_in_opening=$(LC_ALL=C comm -23 "$OUTDIR/airtel$n.opening.sorted" "$OUTDIR/airtel$n.vendored.sorted" | wc -l)"
    echo "  rows_only_in_vendored=$(LC_ALL=C comm -13 "$OUTDIR/airtel$n.opening.sorted" "$OUTDIR/airtel$n.vendored.sorted" | wc -l)"
    if cmp -s "$opening" "$vendored"; then order=identical; else order=different; fi
    echo "  file_order=$order"
done
