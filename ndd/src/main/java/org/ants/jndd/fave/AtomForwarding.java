package org.ants.jndd.fave;

import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.TreeSet;

/**
 * Atomic-predicate forwarding for large single-field (dst-IP) FIBs (wl_i2: 77k
 * routes), the tractable core of the §2.6 incr-1b subsystem. It sidesteps the
 * blow-up of the monolithic per-port residual by computing the minimal dst
 * partition directly with integer interval arithmetic (no BDDs):
 *
 *   1. Each {@code + fwd <dev> <prefix> <plen> <port>} rule is a [lo,hi] dst
 *      range. The union of all rules' range boundaries cuts the 32-bit dst space
 *      into ELEMENTARY INTERVALS (every dst in one interval is forwarded
 *      identically by every device).
 *   2. Per device, a binary trie gives the longest-prefix-match port for each
 *      elementary interval in O(32).
 *   3. Intervals with the same per-device forwarding SIGNATURE merge into one
 *      ATOM. For wl_i2 the 16 232 intervals merge to 216 atoms — exactly APKeep's
 *      ap_num, the minimal partition.
 *
 * Reachability then floods ATOM-SETS (bit-cheap {@link HashSet}) rather than
 * header BDDs: per (device, out_port) the set of atoms forwarded, per-source
 * fixpoint flood keyed by (device, arrival-port) with no-hairpin. This validates
 * the AP algorithm end-to-end (== the BDD/NetPlumber oracle) and is the base the
 * faithful-i2 (dst × VLAN) engine builds on, where the VLAN stays a SEPARATE
 * field (NDD's Σ) instead of BDD's dst×VLAN cross-product (Π).
 */
public final class AtomForwarding {

    static final String DROP = "__drop__";

    // device -> out_port -> set of atom ids forwarded out that port
    private final Map<String, Map<String, Set<Integer>>> portAtoms = new HashMap<>();
    // "dev|port" -> peers "dev|port"
    private final Map<String, List<String>> edges = new HashMap<>();
    private int nAtoms = 0;

    public int atomCount() { return nAtoms; }

    private static String key(String d, String p) { return d + "|" + p; }

    // ---- per-device LPM trie over 32-bit dst ----------------------------------
    private static final class Trie {
        // child[0], child[1]; ports at a node = the rule(s) ending there (ECMP-safe)
        Trie[] ch = new Trie[2];
        Set<String> ports;   // non-null iff a rule ends here
    }

    private static void insert(Trie root, long prefix, int plen, String port) {
        Trie n = root;
        for (int i = 0; i < plen; i++) {
            int b = (int) ((prefix >> (31 - i)) & 1);
            if (n.ch[b] == null) n.ch[b] = new Trie();
            n = n.ch[b];
        }
        if (n.ports == null) n.ports = new HashSet<>();
        n.ports.add(port);
    }

    /** Longest-prefix-match port-set for addr (empty => no route => drop). */
    private static Set<String> lpm(Trie root, long addr) {
        Trie n = root;
        Set<String> best = root.ports;   // /0 default if present
        for (int i = 0; i < 32 && n != null; i++) {
            int b = (int) ((addr >> (31 - i)) & 1);
            n = n.ch[b];
            if (n != null && n.ports != null) best = n.ports;
        }
        return best == null ? java.util.Collections.emptySet() : best;
    }

    /**
     * Build the atom partition + per-port atom-sets from the adapter's IR.
     * Only {@code + fwd} rules are consumed (this path is for dst-IP FIBs).
     */
    public void build(List<String> rules, List<String> edgeStrings) {
        // device -> Trie, and collect boundaries
        Map<String, Trie> tries = new HashMap<>();
        TreeSet<Long> bounds = new TreeSet<>();
        bounds.add(0L); bounds.add(1L << 32);
        for (String r : rules) {
            String[] t = r.trim().split("\\s+");
            if (t.length < 6 || !t[1].equals("fwd")) continue;
            String dev = t[2];
            long prefix = Long.parseLong(t[3]);
            int plen = Integer.parseInt(t[4]);
            String port = t[5];
            long lo = prefix;
            long hi = prefix + (1L << (32 - plen)) - 1;
            bounds.add(lo); bounds.add(hi + 1);
            insert(tries.computeIfAbsent(dev, k -> new Trie()), prefix, plen, port);
        }
        for (String line : edgeStrings) {
            String[] e = line.trim().split("\\s+");
            if (e.length < 4) continue;
            edges.computeIfAbsent(key(e[0], e[1]), k -> new ArrayList<>())
                 .add(key(e[2], e[3]));
        }

        // elementary intervals (rep = lo of each)
        List<Long> bs = new ArrayList<>(bounds);
        List<String> devices = new ArrayList<>(tries.keySet());
        java.util.Collections.sort(devices);

        // merge intervals by per-device forwarding signature -> atoms
        Map<String, Integer> sigToAtom = new HashMap<>();
        // per (device, port) -> atom-set
        for (int i = 0; i < bs.size() - 1; i++) {
            long rep = bs.get(i);
            // signature = for each device, its LPM port-set at rep
            StringBuilder sig = new StringBuilder();
            List<Set<String>> perDev = new ArrayList<>(devices.size());
            for (String d : devices) {
                Set<String> ports = lpm(tries.get(d), rep);
                perDev.add(ports);
                sig.append(new TreeSet<>(ports)).append('|');
            }
            Integer atom = sigToAtom.get(sig.toString());
            if (atom == null) {
                atom = sigToAtom.size();
                sigToAtom.put(sig.toString(), atom);
                // register this atom's forwarding in portAtoms
                for (int di = 0; di < devices.size(); di++) {
                    for (String port : perDev.get(di)) {
                        if (port.equals(DROP)) continue;
                        portAtoms.computeIfAbsent(devices.get(di), k -> new HashMap<>())
                                 .computeIfAbsent(port, k -> new HashSet<>()).add(atom);
                    }
                }
            }
        }
        nAtoms = sigToAtom.size();
    }

    /** Devices reachable from (srcDev, srcPort) flooding the full dst space. */
    public Set<String> reachedDevices(String srcDev, String srcPort) {
        Set<Integer> all = new HashSet<>();
        for (int a = 0; a < nAtoms; a++) all.add(a);
        Map<String, Set<Integer>> reached = new HashMap<>();  // "dev|arrPort" -> atomset
        ArrayDeque<String> work = new ArrayDeque<>();
        for (String peer : edges.getOrDefault(key(srcDev, srcPort), List.of())) {
            reached.put(peer, all); work.add(peer);
        }
        while (!work.isEmpty()) {
            String cur = work.poll();
            int bar = cur.indexOf('|');
            String d = cur.substring(0, bar), inPort = cur.substring(bar + 1);
            Set<Integer> rd = reached.get(cur);
            Map<String, Set<Integer>> pp = portAtoms.get(d);
            if (pp == null) continue;
            for (Map.Entry<String, Set<Integer>> pe : pp.entrySet()) {
                if (pe.getKey().equals(inPort)) continue;   // no-hairpin
                Set<Integer> out = intersect(rd, pe.getValue());
                if (out.isEmpty()) continue;
                for (String peer : edges.getOrDefault(key(d, pe.getKey()), List.of())) {
                    Set<Integer> old = reached.get(peer);
                    if (old == null) { reached.put(peer, out); work.add(peer); }
                    else if (!old.containsAll(out)) {
                        Set<Integer> nr = new HashSet<>(old); nr.addAll(out);
                        reached.put(peer, nr); work.add(peer);
                    }
                }
            }
        }
        Set<String> hit = new HashSet<>();
        for (Map.Entry<String, Set<Integer>> e : reached.entrySet())
            if (!e.getValue().isEmpty())
                hit.add(e.getKey().substring(0, e.getKey().indexOf('|')));
        return hit;
    }

    private static Set<Integer> intersect(Set<Integer> a, Set<Integer> b) {
        Set<Integer> small = a.size() <= b.size() ? a : b, big = a.size() <= b.size() ? b : a;
        Set<Integer> r = new HashSet<>();
        for (int x : small) if (big.contains(x)) r.add(x);
        return r;
    }
}
