#!/usr/bin/env bash

# Extract one archive member's INSERT BLOCK -- every line before its first
# withdrawal -- as a static snapshot (CLOUD_BENCH_PLAN.md §2.14, added
# 2026-09-28).
#
# `phase` measured that in every non-airtel member the inserts are lines 1..N
# and the first withdrawal is line N+1, so the state after line N is one the
# trace passes through; and `opening.sh` showed the dataset's own vendored
# airtel snapshots are exactly this cut. This makes the cut for any member.
#
# It REFUSES rather than trusts: after the cut it keeps reading, and if any
# insert follows the first withdrawal the block is not the whole insert set and
# the output is deleted. The output keeps the trace's own format and order.
#
# Streams like survey.sh; `--occurrence` stops tar once the member is read.
#
# Usage:  ./insert_block.sh <archive.tar.gz> <member.csv> <output.csv>

set -euo pipefail

ARCHIVE="${1:?usage: insert_block.sh <archive.tar.gz> <member.csv> <output.csv>}"
MEMBER="${2:?missing member name, e.g. berkeley.csv}"
OUT="${3:?missing output path}"
mkdir -p "$(dirname "$OUT")"
OUT="$(cd "$(dirname "$OUT")" && pwd)/$(basename "$OUT")"

export BLOCK_OUT="$OUT"
READER="$(mktemp)"
trap 'rm -f "$READER"' EXIT
cat > "$READER" <<'READER_EOF'
#!/usr/bin/env bash
set -euo pipefail
mawk -v out="$BLOCK_OUT" '
    !cut && /^-/ { cut = NR }
    !cut         { print > out; next }
    /^\+/        { late++ }
    END { printf "block_lines=%d\nfirst_withdrawal_line=%d\ninserts_after_cut=%d\n", \
                 cut ? cut - 1 : NR, cut, late > "/dev/stderr" }'
READER_EOF
chmod +x "$READER"

tar -xzf "$ARCHIVE" --occurrence=1 --to-command="$READER" \
    "nsdi-data-sets/$MEMBER" 2> "$OUT.log"
cat "$OUT.log"
if ! grep -q '^inserts_after_cut=0$' "$OUT.log"; then
    rm -f "$OUT"
    echo "REFUSED: $MEMBER has inserts after its first withdrawal" >&2
    exit 1
fi
echo "sha256=$(sha256sum < "$OUT" | cut -d' ' -f1)" | tee -a "$OUT.log"
