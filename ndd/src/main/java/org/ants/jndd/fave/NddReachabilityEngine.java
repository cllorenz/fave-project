package org.ants.jndd.fave;

import java.net.InetAddress;
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;

import org.ants.jndd.diagram.AtomizedNDD;
import org.ants.jndd.diagram.NDD;

/**
 * A per-field NDD reachability engine for FaVe's single-universe forwarding
 * workloads (wl_up), promoted from the §2.5c/§2.5d prototype
 * ({@code NDDWlupReachabilityTest}) into a main-source class the FaVe adapter
 * drives through JPype (see {@code fave/apkeep/lib_ndd.py}).
 *
 * <p>It is the second FaVe backend engine behind one shared APKeep adapter: the
 * adapter emits exactly the same {@code + filter ...} rule strings and
 * {@code "dev port dev port"} topology edges it hands to the BDD engine, and
 * this class consumes them directly (the same neutral IR the BDD path uses).
 *
 * <p>Model (proven at exact parity with the frozen BDD baseline, 3660/3660):
 * per device a first-match residual predicate per (real, non-drop) out_port
 * (higher priority wins =&gt; longest-prefix-match); reachability is a per-source
 * fixpoint flood keyed by (device, arrival-port); a header does not leave via
 * the port it arrived on (no-hairpin), matching the BDD checker's simple-path
 * semantics; each source emits its own src-IPv6 space (query-time seed, Lever B).
 * Reachability runs on plain per-field NDDs (hop = {@link NDD#and}); atomization
 * (§2.5b) is the orthogonal speed layer, kept in the test variant.
 *
 * <p><b>Scope:</b> single-universe forwarding only (no ACLElement/NATElement).
 * The adapter guards this before dispatching here; transformers (NAT/VLAN
 * rewrite via per-field {@code exist}) and ACL division are future work
 * (APKEEP_NDD_PLAN §2.6, "extend beyond wl_up").
 */
public final class NddReachabilityEngine {

    // Per-field layout, shared with the sizing/reachability tests.
    static final int SRC = 0, DST = 1, PROTO = 2, SPORT = 3, DPORT = 4, REL = 5;
    static final int[] W = {128, 128, 8, 16, 16, 1};
    static final String DROP = "__drop__";

    // NDD's node tables are process-global statics; initialise the field layout
    // exactly once per JVM (the FaVe path builds one network per process).
    private static boolean fieldsReady = false;

    private static synchronized void ensureFields() {
        if (fieldsReady) return;
        AtomizedNDD.initAtomizedNDD(4_000_000, 8_000_000, 40_000_000, 8_000_000);
        for (int w : W) AtomizedNDD.declareField(w);
        NDD.generateFields();
        fieldsReady = true;
    }

    private static final class Rule { int hit; String out; long prio; }

    // "dev|port" -> peers "dev|port" reachable across one L1 link.
    private final Map<String, List<String>> edges = new HashMap<>();
    // device -> out_port -> first-match residual predicate (plain NDD node id).
    private final Map<String, Map<String, Integer>> portPred = new HashMap<>();
    // source key "dev|port|cidr" -> set of devices its flood reaches.
    private final Map<String, Set<String>> reachCache = new HashMap<>();

    private boolean built = false;

    public NddReachabilityEngine() {
        ensureFields();
    }

    private static String key(String dev, String port) { return dev + "|" + port; }

    /**
     * Build the residual forwarding model from the adapter's in-memory IR.
     *
     * @param rules the adapter's rule strings; only {@code + filter ...} rules
     *              are consumed (wl_up is all-FilterElement -- IPv6 FIBs +
     *              packet-filter chains). Non-filter rules are ignored.
     * @param edgeStrings directed topology edges "dev1 port1 dev2 port2".
     */
    public void build(List<String> rules, List<String> edgeStrings) {
        // rules -> per-device rule lists
        Map<String, List<Rule>> byDev = new HashMap<>();
        for (String line : rules) {
            String[] t = line.trim().split("\\s+");
            if (t.length < 17 || !t[1].equals("filter")) continue;
            Rule r = new Rule();
            r.hit = NDD.ref(ruleToNDD(t));
            r.out = t[5];
            r.prio = Long.parseLong(t[16]);
            byDev.computeIfAbsent(t[2], k -> new ArrayList<>()).add(r);
        }
        // edges
        for (String line : edgeStrings) {
            String[] e = line.trim().split("\\s+");
            if (e.length < 4) continue;
            edges.computeIfAbsent(key(e[0], e[1]), k -> new ArrayList<>())
                 .add(key(e[2], e[3]));
        }
        // per device: first-match residual predicate per (real, non-drop) out_port
        for (Map.Entry<String, List<Rule>> en : byDev.entrySet()) {
            List<Rule> rs = new ArrayList<>(en.getValue());
            rs.sort(Comparator.comparingLong((Rule r) -> r.prio).reversed()); // higher prio first
            Map<String, Integer> pp = new HashMap<>();
            int covered = NDD.ref(NDD.getFalse());
            for (Rule r : rs) {
                int eff = NDD.ref(NDD.diff(r.hit, covered));     // hit & !covered
                if (eff != NDD.getFalse() && !r.out.equals(DROP)) {
                    Integer prev = pp.get(r.out);
                    int merged = NDD.ref(prev == null ? eff : NDD.or(prev, eff));
                    if (prev != null) NDD.deref(prev);
                    pp.put(r.out, merged);
                }
                int nc = NDD.ref(NDD.or(covered, r.hit));
                NDD.deref(covered); covered = nc;
                NDD.deref(eff);
            }
            NDD.deref(covered);
            // rule hit predicates are no longer needed once the residual is built
            for (Rule r : rs) NDD.deref(r.hit);
            portPred.put(en.getKey(), pp);
        }
        built = true;
    }

    /**
     * True iff traffic injected at (srcDev, srcPort) with source address {@code
     * cidr} (null / full space =&gt; unconstrained) can reach {@code dstDev} on
     * any port. The per-source flood is computed once and cached, so the
     * adapter's probe x source loop pays 137 floods, not 137^2.
     */
    public boolean isReachable(String srcDev, String srcPort, String cidr,
                               String dstDev, String dstPort) {
        return reachedDevices(srcDev, srcPort, cidr).contains(dstDev);
    }

    /** Devices reachable from one source (cached). */
    public synchronized Set<String> reachedDevices(String srcDev, String srcPort,
                                                   String cidr) {
        if (!built) throw new IllegalStateException("build() must run first");
        String ck = srcDev + "|" + srcPort + "|" + (cidr == null ? "" : cidr);
        Set<String> hit = reachCache.get(ck);
        if (hit != null) return hit;

        int h0 = NDD.ref(addrPred(SRC, cidr, "null"));   // {src in cidr}, rest free
        Map<String, Integer> reached = new HashMap<>();  // "dev|arrivalPort" -> NDD
        ArrayDeque<String> work = new ArrayDeque<>();
        for (String peer : edges.getOrDefault(key(srcDev, srcPort), List.of())) {
            reached.put(peer, NDD.ref(h0));
            work.add(peer);
        }
        while (!work.isEmpty()) {
            String cur = work.poll();
            int bar = cur.indexOf('|');
            String d = cur.substring(0, bar);
            String inPort = cur.substring(bar + 1);
            int rd = reached.get(cur);
            Map<String, Integer> pp = portPred.get(d);
            if (pp == null) continue;                    // sink (probe) or no rules
            for (Map.Entry<String, Integer> pe : pp.entrySet()) {
                if (pe.getKey().equals(inPort)) continue; // no-hairpin
                int out = NDD.and(rd, pe.getValue());
                if (out == NDD.getFalse()) continue;
                for (String peer : edges.getOrDefault(key(d, pe.getKey()), List.of())) {
                    Integer old = reached.get(peer);
                    int nr = old == null ? out : NDD.or(old, out);
                    if (old == null || nr != old) {
                        int rr = NDD.ref(nr);
                        if (old != null) NDD.deref(old);
                        reached.put(peer, rr);
                        work.add(peer);
                    }
                }
            }
        }
        hit = new HashSet<>();
        for (Map.Entry<String, Integer> re : reached.entrySet()) {
            if (re.getValue() != NDD.getFalse()) {
                String d = re.getKey().substring(0, re.getKey().indexOf('|'));
                hit.add(d);
            }
        }
        for (int v : reached.values()) NDD.deref(v);
        NDD.deref(h0);
        reachCache.put(ck, hit);
        return hit;
    }

    /** Number of atomic predicates in the built model (diagnostic). */
    public int fieldCount() { return NDD.getFieldNum(); }

    // ---- per-field encoders (identical to NDDWlupReachabilityTest) -----------

    private static int ruleToNDD(String[] t) {
        int r = NDD.getTrue();
        r = NDD.and(r, rangePred(PROTO, t[6], t[7]));
        r = NDD.and(r, addrPred(SRC, t[8], t[9]));
        r = NDD.and(r, rangePred(SPORT, t[10], t[11]));
        r = NDD.and(r, addrPred(DST, t[12], t[13]));
        r = NDD.and(r, rangePred(DPORT, t[14], t[15]));
        String rel = t.length > 18 ? t[18] : "null";
        if (!rel.equals("null")) r = NDD.and(r, exact(REL, Long.parseLong(rel), 1));
        return r;
    }

    private static int addrPred(int field, String ip, String wild) {
        if (ip == null) return NDD.getTrue();
        if (ip.equals("0.0.0.0") && wild.equals("255.255.255.255")) return NDD.getTrue();
        int len = 128;
        String addr = ip;
        int slash = ip.indexOf('/');
        if (slash >= 0) { addr = ip.substring(0, slash); len = Integer.parseInt(ip.substring(slash + 1)); }
        if (len == 0) return NDD.getTrue();
        byte[] b;
        try { b = InetAddress.getByName(addr).getAddress(); }
        catch (Exception e) { throw new RuntimeException("bad ip " + ip, e); }
        if (b.length != 16) return NDD.getTrue();
        int[] bits = new int[len];
        for (int i = 0; i < len; i++) bits[i] = (b[i >> 3] >> (7 - (i & 7))) & 1;
        return prefix(field, bits, len);
    }

    private static int rangePred(int field, String lo, String hi) {
        if (lo.equals("null") || hi.equals("null")) return NDD.getTrue();
        long l = Long.parseLong(lo), h = Long.parseLong(hi);
        if (field == PROTO && l == 0 && h == 255) return NDD.getTrue();
        if (l == 0 && h == (1L << W[field]) - 1) return NDD.getTrue();
        if (l == h) return exact(field, l, W[field]);
        return interval(field, l, h, W[field]);
    }

    private static int prefix(int field, int[] bits, int len) {
        int r = NDD.getTrue();
        for (int i = 0; i < len; i++)
            r = NDD.and(r, bits[i] == 1 ? NDD.getVar(field, i) : NDD.getNotVar(field, i));
        return r;
    }

    private static int exact(int field, long value, int width) {
        int[] bits = new int[width];
        for (int i = 0; i < width; i++) bits[i] = (int) ((value >> (width - 1 - i)) & 1);
        return prefix(field, bits, width);
    }

    private static int interval(int field, long lo, long hi, int width) {
        int result = NDD.getFalse();
        long cur = lo;
        while (cur <= hi) {
            int maxLen = width;
            while (maxLen > 0) {
                long mask = (1L << (width - maxLen + 1)) - 1;
                if ((cur & mask) != 0 || cur + mask > hi) break;
                maxLen--;
            }
            int plen = maxLen;
            int[] bits = new int[plen];
            for (int i = 0; i < plen; i++) bits[i] = (int) ((cur >> (width - 1 - i)) & 1);
            result = NDD.or(result, prefix(field, bits, plen));
            long step = 1L << (width - plen);
            cur += step;
            if (width - plen >= 63) break;
        }
        return result;
    }
}
