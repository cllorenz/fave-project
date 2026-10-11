"""M2 spike: how many ENGINE rules does one firewall edit change?

Scratch prototype, not FaVe code. For a ruleset and a seeded stream of S4-like
edits (insert a copy of a rule line / delete a line / modify a line), it
regenerates the packet-filter model after every edit and counts the rules an
engine would have to delete and insert, under two index schemes:

  dense   -- today's: the generator's own indices (interwoven densely)
  stable  -- stable renumbering by alignment: per table, the new rule list is
             aligned with the previously EMITTED list by content; matched rules
             keep their index, new ones take free indices between neighbours,
             and a table without room is re-spaced (counted)

and against the floor -- the minimum edit an order-preserving alignment admits
(the same opcodes, without re-spacing). Content excludes idx and raw-line
metadata, which no engine reads.
"""
import difflib, json, os, random, statistics, sys, tempfile, time

sys.path.insert(0, '/home/ubuntu/fave-project/fave')
from iptables.generator import generate
from iptables.parser_singleton import PARSER

IDX_MAX = 2**20 - 1          # NetPlumber adapter's _RULE_IDX_MAX


def key(r):
    return (r.tid, tuple(r.in_ports), str(r.match), ",".join(str(a) for a in r.actions))


def model_tables(lines, node='fw'):
    with tempfile.NamedTemporaryFile('w', suffix='.rs', delete=False) as f:
        f.write('\n'.join(lines) + '\n')
        path = f.name
    try:
        m = generate(PARSER.parse(path), node, None, [node + '.1', node + '.2'])
    finally:
        os.unlink(path)
    return {t: sorted(rs, key=lambda r: r.idx) for t, rs in m.tables.items()
            if t.endswith('_filter')}


def spacing(n):
    return max(1, IDX_MAX // (2 * (n + 1)))   # half the range left for growth


class Stable:
    """ stable renumbering by alignment, per table """
    def __init__(self):
        self.prev = {}          # table -> [(idx, key)]
        self.respaced = 0

    def emit(self, table, keys):
        prev = self.prev.get(table)
        if prev is None:
            g = spacing(len(keys))
            out = [(g * (i + 1), k) for i, k in enumerate(keys)]
            self.prev[table] = out
            return out
        pk = [k for _i, k in prev]
        ops = difflib.SequenceMatcher(None, pk, keys, autojunk=False).get_opcodes()
        out = []
        for tag, i1, i2, j1, j2 in ops:
            if tag == 'equal':
                out.extend((prev[i][0], keys[j1 + (i - i1)]) for i in range(i1, i2))
            elif j2 > j1:                       # insert / replace: new rules
                lo = out[-1][0] if out else 0
                hi = prev[i2][0] if i2 < len(prev) else IDX_MAX + 1
                k = j2 - j1
                if hi - lo - 1 < k:
                    out = None
                    break
                step = (hi - lo) / (k + 1)
                out.extend((int(lo + step * (n + 1)), keys[j]) for n, j in enumerate(range(j1, j2)))
        if out is None or len({i for i, _k in out}) != len(out):
            self.respaced += 1
            g = spacing(len(keys))
            out = [(g * (i + 1), k) for i, k in enumerate(keys)]
        assert [i for i, _k in out] == sorted(i for i, _k in out)
        self.prev[table] = out
        return out


def floor_edit(old_keys, new_keys):
    ops = difflib.SequenceMatcher(None, old_keys, new_keys, autojunk=False).get_opcodes()
    return sum((i2 - i1) + (j2 - j1) for t, i1, i2, j1, j2 in ops if t != 'equal')


def diff(old, new):
    return len(set(old) ^ set(new))


def mutate(line, rnd):
    # never flip a state-checking rule to DROP: that crashes the generator
    # (FINDINGS F1), which is a defect of its own, not this spike's question
    if 'ESTABLISHED' in line:
        return line.replace(' -j ', ' -p tcp -j ', 1) if ' -p ' not in line else line
    toks = line.split()
    if '-j' in toks:
        j = toks.index('-j') + 1
        if j < len(toks) and toks[j] in ('ACCEPT', 'DROP'):
            toks[j] = 'DROP' if toks[j] == 'ACCEPT' else 'ACCEPT'
            return ' '.join(toks)
    return line + ' -p tcp' if ' -p ' not in line else line.replace(' -j ', ' --dport 4711 -j ', 1)


def run(path, n_edits, seed):
    lines = [l.rstrip('\n') for l in open(path) if l.strip() and not l.startswith('#')]
    rnd = random.Random(seed)
    tables = model_tables(lines)
    stable = Stable()
    dense_prev = {t: [(r.idx, key(r)) for r in rs] for t, rs in tables.items()}
    stable_prev = {t: stable.emit(t, [key(r) for r in rs]) for t, rs in tables.items()}
    size = sum(len(v) for v in dense_prev.values())
    rows = []
    for e in range(n_edits):
        rule_pos = [i for i, l in enumerate(lines) if ' -A ' in l]
        op = rnd.choice(['insert', 'delete', 'modify'])
        pos = rnd.choice(rule_pos)
        if op == 'insert':
            src = lines[rnd.choice(rule_pos)]
            chain = lines[pos].split(' -A ')[1].split()[0]
            src = src.split(' -A ')[0] + ' -A ' + chain + ' ' + ' '.join(src.split(' -A ')[1].split()[1:])
            lines.insert(pos, src)
        elif op == 'delete':
            del lines[pos]
        else:
            lines[pos] = mutate(lines[pos], rnd)
        t0 = time.perf_counter()
        tables = model_tables(lines)
        t_gen = time.perf_counter() - t0
        d = s = fl = 0
        t0 = time.perf_counter()
        for t in set(tables) | set(dense_prev):
            new = [(r.idx, key(r)) for r in tables.get(t, [])]
            d += diff(dense_prev.get(t, []), new)
            fl += floor_edit([k for _i, k in dense_prev.get(t, [])], [k for _i, k in new])
            st = stable.emit(t, [k for _i, k in new])
            s += diff(stable_prev.get(t, []), st)
            dense_prev[t], stable_prev[t] = new, st
        t_align = time.perf_counter() - t0
        rows.append((op, d, s, fl, t_gen, t_align))
    return size, rows, stable.respaced


if __name__ == '__main__':
    path, n, seed = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
    size, rows, respaced = run(path, n, seed)
    print('ruleset %s: %d engine rules in the filter tables, %d edits, seed %d, re-spacings %d'
          % (os.path.basename(path), size, n, seed, respaced))
    for op in ('insert', 'delete', 'modify', 'all'):
        sel = [r for r in rows if op == 'all' or r[0] == op]
        if not sel:
            continue
        med = lambda i: statistics.median(r[i] for r in sel)
        mx = lambda i: max(r[i] for r in sel)
        print('  %-6s n=%3d  dense med/max %7.0f/%7d   stable med/max %6.0f/%6d   floor med/max %6.0f/%6d'
              '   gen %.2fs  align %.3fs (med)'
              % (op, len(sel), med(1), mx(1), med(2), mx(2), med(3), mx(3), med(4), med(5)))
    print('  stable == floor on %d of %d edits' % (sum(r[2] == r[3] for r in rows), len(rows)))
