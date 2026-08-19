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
import java.util.TreeSet;

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

    // Canonical per-field layout serving every FaVe benchmark from one
    // process-global NDD field set. Indices 0..5 (the wl_up fields) are FIXED so
    // §2.5e parity is preserved by construction; IPv4 address fields and VLAN are
    // APPENDED. A benchmark constrains only the fields it uses (IPv4 xor IPv6 per
    // rule; the untouched fields stay TRUE, so unused fields cost nothing).
    static final int SRC = 0, DST = 1, PROTO = 2, SPORT = 3, DPORT = 4, REL = 5;
    static final int SRC4 = 6, DST4 = 7, VLAN = 8;
    static final int[] W = {128, 128, 8, 16, 16, 1, 32, 32, 16};
    static final String DROP = "__drop__";

    // NDD's node tables are process-global statics; initialise the field layout
    // exactly once per JVM (the FaVe path builds one network per process).
    private static boolean fieldsReady = false;

    private static synchronized void ensureFields() {
        if (fieldsReady) return;
        AtomizedNDD.initAtomizedNDD(8_000_000, 16_000_000, 48_000_000, 16_000_000);
        for (int w : W) AtomizedNDD.declareField(w);
        NDD.generateFields();
        fieldsReady = true;
    }

    private static final class Rule { int hit; String out; long prio; }

    // "dev|port" -> peers "dev|port" reachable across one L1 link.
    private final Map<String, List<String>> edges = new HashMap<>();
    // device -> out_port -> first-match residual predicate (plain NDD node id).
    private final Map<String, Map<String, Integer>> portPred = new HashMap<>();
    // "dev|port" -> inline VLAN-rewrite rules (NATElement): each (dst-prefix NDD,
    // vlan id). A header forwarded out this port has its VLAN set to vlanN on the
    // dst-prefix-matched part (exist VLAN, then set); unmatched dst is unchanged.
    private final Map<String, List<int[]>> nat = new HashMap<>();  // val: {dstPredNode, vlanN}
    // source key "dev|port|cidr" -> device -> union of reached headers (NDD node,
    // reffed). Cached so the adapter's probe x source loop floods once per source.
    private final Map<String, Map<String, Integer>> reachCache = new HashMap<>();

    private boolean built = false;

    public NddReachabilityEngine() {
        ensureFields();
    }

    private static String key(String dev, String port) { return dev + "|" + port; }

    /** A topology node -> the rule element it belongs to. APKeep names an
     * element E's boundary nodes "E_<port>_in"/"E_<port>_out" (ACLElement) with a
     * varying number of trailing "_"-segments (e.g. "ifi_inACLp2_in",
     * "iacl_0_i_in"), so resolve by the LONGEST rule element K that is a prefix of
     * the node up to a "_" boundary. Returns null when no element matches (a sink
     * such as a probe), leaving dotted device names like "in.bbra_rtr" untouched. */
    private String elementOf(String node) {
        String best = null;
        for (String k : portPred.keySet()) {
            if (node.startsWith(k + "_")
                    && (best == null || k.length() > best.length())) best = k;
        }
        return best;
    }

    /** {VLAN == v} over the 16-bit VLAN field (comma-separated set -> OR). */
    private static int vlanPred(String vlanSet) {
        int r = NDD.getFalse();
        for (String v : vlanSet.split(",")) {
            if (v.isEmpty()) continue;
            r = NDD.or(r, exact(VLAN, Long.parseLong(v.trim()), W[VLAN]));
        }
        return r;
    }

    /**
     * Build the residual forwarding model from the adapter's in-memory IR.
     *
     * @param rules the adapter's rule strings: {@code + filter ...} (5-tuple
     *              FilterElement) and {@code + fwd ...} (dst-LPM ForwardElement).
     * @param edgeStrings directed topology edges "dev1 port1 dev2 port2".
     */
    public void build(List<String> rules, List<String> edgeStrings) {
        // rules -> per-device rule lists. Every element type (FilterElement,
        // ForwardElement, later ACLElement) reduces to the SAME residual-per-
        // out_port model; only the rule-string parse differs.
        //   "+ filter <dev> filter 0 <out> <plo> <phi> <sip> <swild> <slo> <shi>
        //             <dip> <dwild> <dlo> <dhi> <prio> [null] [rel]"  (5-tuple)
        //   "+ fwd    <dev> <prefixUint32> <plen> <out> <prio>"       (dst LPM)
        Map<String, List<Rule>> byDev = new HashMap<>();
        Map<String, List<FwdRule>> fwdByDev = new HashMap<>();
        for (String line : rules) {
            String[] t = line.trim().split("\\s+");
            if (t.length < 2) continue;
            Rule r = new Rule();
            String dev;
            if (t[1].equals("filter") && t.length >= 17) {
                r.hit = NDD.ref(ruleToNDD(t));
                r.out = t[5];
                r.prio = Long.parseLong(t[16]);
                dev = t[2];
            } else if (t[0].equals("+") && t[1].equals("fwd") && t.length >= 7) {
                // A dst-IP FIB rule. Do NOT build a per-rule NDD or a growing
                // "covered" residual (that blows up at wl_i2's 77k routes) --
                // collect the ranges and resolve LPM per-device by ATOMS
                // (buildFwdPortPred): the per-port dst set becomes a bounded
                // union of contiguous ranges, not a union of thousands of prefixes.
                FwdRule fr = new FwdRule();
                fr.prefix = Long.parseLong(t[3]);
                fr.plen = Integer.parseInt(t[4]);
                fr.out = t[5];
                fwdByDev.computeIfAbsent(t[2], k -> new ArrayList<>()).add(fr);
                continue;
            } else if (t[1].equals("acl") && t.length >= 17) {
                // "+ acl <elem> acl 0 <permit|deny> 0 255 <sip> <swild> null null
                //       <dip> <dwild> null null <prio> [vlan]" -- SAME field layout
                // as "+ filter" (proto/src/sport/dst/dport at the same indices), so
                // the predicate reuses ruleToNDD; a permit forwards to the element's
                // "permit" out_port (Cisco first-match => higher priority wins), a
                // deny drops. The element node appears in the topology as
                // "<elem>_..._{in,out}" (resolved in the flood). A trailing VLAN
                // token (VLAN-admission ACL, faithful wl_stanford) constrains VLAN.
                int hit = ruleToNDD(t);
                if (t.length > 17 && !t[17].equals("null"))
                    hit = NDD.and(hit, vlanPred(t[17]));
                r.hit = NDD.ref(hit);
                r.out = t[5].equals("permit") ? "permit" : DROP;
                r.prio = Long.parseLong(t[16]);
                dev = t[2];
            } else if (t[1].equals("nat") && t.length >= 8 && t[4].equals("vlan")) {
                // "+ nat <dev> <port> vlan <dstIP> <dstlen> <vlanN>": an inline
                // VLAN rewrite on (dev, port). Not a residual -- recorded in `nat`
                // and applied to headers forwarded out that port (see the flood).
                int plen = Integer.parseInt(t[6]);
                int dstPred = plen == 0 ? NDD.getTrue()
                        : prefixV4(DST4, ipv4ToLong(t[5]), plen);
                nat.computeIfAbsent(key(t[2], t[3]), k -> new ArrayList<>())
                   .add(new int[]{NDD.ref(dstPred), Integer.parseInt(t[7])});
                continue;
            } else {
                continue;
            }
            byDev.computeIfAbsent(dev, k -> new ArrayList<>()).add(r);
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
            for (Rule r : rs) NDD.deref(r.hit);   // hits no longer needed
            portPred.put(en.getKey(), pp);
        }
        buildFwdPortPred(fwdByDev);
        built = true;
    }

    // ---- atom-based dst-IP FIB (avoids the 77k-route residual blow-up) --------

    private static final class FwdRule { long prefix; int plen; String out; }

    private static final class Trie { Trie[] ch = new Trie[2]; Set<String> ports; }

    private static void trieInsert(Trie root, long prefix, int plen, String port) {
        Trie n = root;
        for (int i = 0; i < plen; i++) {
            int b = (int) ((prefix >> (31 - i)) & 1);
            if (n.ch[b] == null) n.ch[b] = new Trie();
            n = n.ch[b];
        }
        if (n.ports == null) n.ports = new HashSet<>();
        n.ports.add(port);
    }

    private static Set<String> trieLpm(Trie root, long addr) {
        Trie n = root; Set<String> best = root.ports;
        for (int i = 0; i < 32 && n != null; i++) {
            n = n.ch[(int) ((addr >> (31 - i)) & 1)];
            if (n != null && n.ports != null) best = n.ports;
        }
        return best == null ? java.util.Collections.emptySet() : best;
    }

    /** For each device's dst-IP FIB, resolve LPM over elementary intervals and
     * set portPred[device][port] = the union of the (merged, contiguous) dst
     * ranges forwarded out that port -- a bounded NDD, computed WITHOUT a growing
     * residual. Exact (LPM first-match) and equal to what the residual loop would
     * produce, but tractable at wl_i2's 77k-route scale. */
    private void buildFwdPortPred(Map<String, List<FwdRule>> fwdByDev) {
        for (Map.Entry<String, List<FwdRule>> en : fwdByDev.entrySet()) {
            List<FwdRule> rs = en.getValue();
            TreeSet<Long> bset = new TreeSet<>();
            bset.add(0L); bset.add(1L << 32);
            Trie root = new Trie();
            for (FwdRule fr : rs) {
                long lo = fr.prefix, hi = fr.prefix + (1L << (32 - fr.plen)) - 1;
                bset.add(lo); bset.add(hi + 1);
                trieInsert(root, fr.prefix, fr.plen, fr.out);
            }
            Long[] bs = bset.toArray(new Long[0]);
            Map<String, List<long[]>> raw = new HashMap<>();
            for (int i = 0; i < bs.length - 1; i++) {
                long lo = bs[i], hi = bs[i + 1] - 1;
                for (String p : trieLpm(root, lo)) {
                    if (p.equals(DROP)) continue;
                    raw.computeIfAbsent(p, k -> new ArrayList<>()).add(new long[]{lo, hi});
                }
            }
            Map<String, Integer> pp = new HashMap<>();
            for (Map.Entry<String, List<long[]>> pe : raw.entrySet()) {
                int nd = NDD.getFalse();
                for (long[] rg : mergeAdjacent(pe.getValue()))
                    nd = NDD.or(nd, interval(DST4, rg[0], rg[1], W[DST4]));
                pp.put(pe.getKey(), NDD.ref(nd));
            }
            portPred.put(en.getKey(), pp);
        }
    }

    /** Merge a port's elementary intervals (already in ascending order) into
     * maximal contiguous [lo,hi] ranges, so the union NDD is over few ranges. */
    private static List<long[]> mergeAdjacent(List<long[]> ivs) {
        List<long[]> out = new ArrayList<>();
        for (long[] iv : ivs) {
            if (!out.isEmpty() && out.get(out.size() - 1)[1] + 1 == iv[0])
                out.get(out.size() - 1)[1] = iv[1];
            else
                out.add(new long[]{iv[0], iv[1]});
        }
        return out;
    }

    /**
     * True iff traffic injected at (srcDev, srcPort) with src address {@code cidr}
     * (null =&gt; unconstrained) can reach {@code dstDev}. When {@code targetVlan}
     * &gt;= 0, arrival additionally requires the header to carry that VLAN (the
     * faithful wl_stanford probes accept only vlan 0); &lt; 0 imposes no VLAN
     * constraint. The per-source flood is computed once and cached.
     */
    public boolean isReachable(String srcDev, String srcPort, String cidr,
                               String dstDev, String dstPort, int targetVlan) {
        Integer h = reachedHeaders(srcDev, srcPort, cidr).get(dstDev);
        if (h == null) return false;
        if (targetVlan < 0) return h != NDD.getFalse();
        return NDD.and(h, exact(VLAN, targetVlan, W[VLAN])) != NDD.getFalse();
    }

    /** Back-compat: no VLAN constraint. */
    public boolean isReachable(String srcDev, String srcPort, String cidr,
                               String dstDev, String dstPort) {
        return isReachable(srcDev, srcPort, cidr, dstDev, dstPort, -1);
    }

    /** Per-device union of the headers reachable from one source (cached; the
     * stored node ids are reffed for the engine's lifetime). */
    public synchronized Map<String, Integer> reachedHeaders(String srcDev,
            String srcPort, String cidr) {
        if (!built) throw new IllegalStateException("build() must run first");
        String ck = srcDev + "|" + srcPort + "|" + (cidr == null ? "" : cidr);
        Map<String, Integer> cached = reachCache.get(ck);
        if (cached != null) return cached;

        int h0 = NDD.ref(addrPred(SRC, SRC4, cidr, "null"));  // {src in cidr}, rest free
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
            if (pp == null) {
                // Resolve an APKeep boundary node "E_..._{in,out}" to element E.
                String elem = elementOf(d);
                if (elem != null) pp = portPred.get(elem);
            }
            if (pp == null) continue;                    // sink (probe) or no rules
            for (Map.Entry<String, Integer> pe : pp.entrySet()) {
                if (pe.getKey().equals(inPort)) continue; // no-hairpin
                int out = NDD.and(rd, pe.getValue());
                if (out == NDD.getFalse()) continue;
                // inline VLAN rewrite (NATElement) on the egress port, if any
                List<int[]> nrules = nat.get(key(d, pe.getKey()));
                int fwd = nrules == null ? out : NDD.ref(applyNat(out, nrules));
                for (String peer : edges.getOrDefault(key(d, pe.getKey()), List.of())) {
                    Integer old = reached.get(peer);
                    int nr = old == null ? fwd : NDD.or(old, fwd);
                    if (old == null || nr != old) {
                        int rr = NDD.ref(nr);
                        if (old != null) NDD.deref(old);
                        reached.put(peer, rr);
                        work.add(peer);
                    }
                }
                if (nrules != null) NDD.deref(fwd);
            }
        }
        // aggregate arrival ports -> one union header per device
        Map<String, Integer> byDevHdr = new HashMap<>();
        for (Map.Entry<String, Integer> re : reached.entrySet()) {
            String d = re.getKey().substring(0, re.getKey().indexOf('|'));
            Integer prev = byDevHdr.get(d);
            int u = NDD.ref(prev == null ? re.getValue() : NDD.or(prev, re.getValue()));
            if (prev != null) NDD.deref(prev);
            byDevHdr.put(d, u);
        }
        for (int v : reached.values()) NDD.deref(v);
        // A probe is a host on an access port, which STRIPS the VLAN tag on
        // delivery (the frame reaches the host untagged), so a probe accepts
        // traffic regardless of the transit VLAN it arrived carrying. Model this
        // by existentially quantifying VLAN out of a probe device's header. This
        // is a no-op where VLAN is already free (every non-faithful benchmark),
        // and is what makes the faithful wl_stanford data plane match NetPlumber
        // exactly (a probe requiring a literal vlan=0 would wrongly drop transit
        // VLANs the access port untags).
        for (Map.Entry<String, Integer> e : byDevHdr.entrySet()) {
            if (e.getKey().startsWith("probe.")) {
                int untag = NDD.ref(NDD.exist(e.getValue(), VLAN));
                NDD.deref(e.getValue());
                e.setValue(untag);
            }
        }
        NDD.deref(h0);
        reachCache.put(ck, byDevHdr);
        return byDevHdr;
    }

    /** Devices reachable from one source, ignoring VLAN (diagnostic). */
    public Set<String> reachedDevices(String srcDev, String srcPort, String cidr) {
        Set<String> hit = new HashSet<>();
        for (Map.Entry<String, Integer> e :
                reachedHeaders(srcDev, srcPort, cidr).entrySet())
            if (e.getValue() != NDD.getFalse()) hit.add(e.getKey());
        return hit;
    }

    /** Apply a NATElement's VLAN rewrites to a header leaving one port: the
     * dst-prefix-matched part has its VLAN existentially removed then set to
     * vlanN; dst matched by no rule passes unchanged (identity default rule). */
    private static int applyNat(int h, List<int[]> rules) {
        int result = NDD.getFalse();
        int matched = NDD.getFalse();
        for (int[] rl : rules) {
            int part = NDD.and(h, rl[0]);
            if (part != NDD.getFalse()) {
                int rw = NDD.and(NDD.exist(part, VLAN), exact(VLAN, rl[1], W[VLAN]));
                result = NDD.or(result, rw);
            }
            matched = NDD.or(matched, rl[0]);
        }
        return NDD.or(result, NDD.and(h, NDD.not(matched)));
    }

    /** Number of atomic predicates in the built model (diagnostic). */
    public int fieldCount() { return NDD.getFieldNum(); }

    // ---- per-field encoders (identical to NDDWlupReachabilityTest) -----------

    private static int ruleToNDD(String[] t) {
        int r = NDD.getTrue();
        r = NDD.and(r, rangePred(PROTO, t[6], t[7]));
        r = NDD.and(r, addrPred(SRC, SRC4, t[8], t[9]));
        r = NDD.and(r, rangePred(SPORT, t[10], t[11]));
        r = NDD.and(r, addrPred(DST, DST4, t[12], t[13]));
        r = NDD.and(r, rangePred(DPORT, t[14], t[15]));
        String rel = t.length > 18 ? t[18] : "null";
        if (!rel.equals("null")) r = NDD.and(r, exact(REL, Long.parseLong(rel), 1));
        return r;
    }

    /** Encode a src/dst address slot, dispatching by family: an IPv6 token
     * ("addr/len", wild "null") constrains {@code field6} over 128 bits; an IPv4
     * token (dotted-quad + a cisco inverse-mask wildcard, or "addr/len")
     * constrains {@code field4} over 32 bits. The APKeep match-any form
     * (0.0.0.0 / 255.255.255.255) and null map to TRUE in either family. A rule
     * only ever names one family, so the other field stays free. */
    private static int addrPred(int field6, int field4, String ip, String wild) {
        if (ip == null) return NDD.getTrue();
        if (ip.equals("0.0.0.0") && "255.255.255.255".equals(wild)) return NDD.getTrue();
        if (ip.contains(":")) return addrPred6(field6, ip);
        return addrPred4(field4, ip, wild);
    }

    /** IPv6 prefix "addr/len" (or bare address = /128) over a 128-bit field. */
    private static int addrPred6(int field, String ip) {
        int len = 128;
        String addr = ip;
        int slash = ip.indexOf('/');
        if (slash >= 0) { addr = ip.substring(0, slash); len = Integer.parseInt(ip.substring(slash + 1)); }
        if (len == 0) return NDD.getTrue();
        byte[] b;
        try { b = InetAddress.getByName(addr).getAddress(); }
        catch (Exception e) { throw new RuntimeException("bad ipv6 " + ip, e); }
        if (b.length != 16) return NDD.getTrue();
        int[] bits = new int[len];
        for (int i = 0; i < len; i++) bits[i] = (b[i >> 3] >> (7 - (i & 7))) & 1;
        return prefix(field, bits, len);
    }

    /** IPv4 slot over a 32-bit field. Accepts either a cisco inverse-mask
     * wildcard ("10.0.14.0" + "0.0.1.255": a set wildcard bit is "don't care") --
     * general (contiguous or not), built bit-by-bit -- or an "addr/len" prefix.
     * "null"/absent wildcard means an exact /32; a match-any wildcard => TRUE. */
    private static int addrPred4(int field, String ip, String wild) {
        String addr = ip;
        int slash = ip.indexOf('/');
        if (slash >= 0) {
            int len = Integer.parseInt(ip.substring(slash + 1));
            if (len == 0) return NDD.getTrue();
            long p = ipv4ToLong(ip.substring(0, slash));
            return prefixV4(field, p, len);
        }
        long a = ipv4ToLong(addr);
        long w;
        if (wild == null || wild.equals("null")) {
            w = 0L;                                  // fully care => exact /32
        } else if (wild.equals("255.255.255.255")) {
            return NDD.getTrue();                    // match-any
        } else {
            w = ipv4ToLong(wild);
        }
        int r = NDD.getTrue();
        for (int i = 0; i < 32; i++) {               // MSB..LSB
            if (((w >> (31 - i)) & 1) != 0) continue; // don't-care bit
            int bit = (int) ((a >> (31 - i)) & 1);
            r = NDD.and(r, bit == 1 ? NDD.getVar(field, i) : NDD.getNotVar(field, i));
        }
        return r;
    }

    private static long ipv4ToLong(String dotted) {
        String[] o = dotted.split("\\.");
        return ((Long.parseLong(o[0]) & 255) << 24) | ((Long.parseLong(o[1]) & 255) << 16)
             | ((Long.parseLong(o[2]) & 255) << 8) | (Long.parseLong(o[3]) & 255);
    }

    /** A dst-IP prefix (top {@code plen} bits of a uint32) over a 32-bit field. */
    private static int prefixV4(int field, long prefix, int plen) {
        int r = NDD.getTrue();
        for (int i = 0; i < plen; i++) {
            int bit = (int) ((prefix >> (31 - i)) & 1);
            r = NDD.and(r, bit == 1 ? NDD.getVar(field, i) : NDD.getNotVar(field, i));
        }
        return r;
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
