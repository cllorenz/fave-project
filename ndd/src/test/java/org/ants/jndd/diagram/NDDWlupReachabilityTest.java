package org.ants.jndd.diagram;

import static org.junit.jupiter.api.Assumptions.assumeTrue;
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.io.IOException;
import java.net.InetAddress;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.TreeSet;

import org.junit.jupiter.api.Test;

/**
 * §2.5c: an NDD reachability engine for wl_up, gated on EXACT parity with the frozen
 * BDD baseline (APKEEP_BDD_BASELINE.md: 3660/3660). Correctness proof of the (B)
 * engine-swap. Reachability runs on plain per-field NDDs (hop = NDD.and, arrival iff
 * != FALSE); atomization (§2.5b, 40x) is the orthogonal speed layer added after parity.
 * Single-universe; source src-IPv6 seed (Lever B); no NAT.
 *
 * Forwarding model (from the dumped wl_up graph): 269 filter devices (first-match rules
 * -> named out_ports, higher priority wins => LPM), 137 sources (emit their src-IPv6
 * space), 137 probes (sinks). Reachability is tracked per (device, arrival-port); a
 * header does NOT leave via the port it arrived on (no-hairpin), matching the BDD
 * checker's simple-path semantics.
 *
 * Runs only with -Dwlup.rules -Dwlup.edges -Dwlup.sources -Dwlup.probes -Dwlup.golden
 * (line files from wl_up_dump2.py + mat_apk.json); skips otherwise.
 */
class NDDWlupReachabilityTest {

    static final int SRC = 0, DST = 1, PROTO = 2, SPORT = 3, DPORT = 4, REL = 5;
    static final int[] W = {128, 128, 8, 16, 16, 1};
    static final String DROP = "__drop__";

    static final class Rule { int hit; String out; long prio; }

    @Test
    void wlupReachabilityMatchesBddBaseline() throws IOException {
        String rulesP = System.getProperty("wlup.rules");
        assumeTrue(rulesP != null, "set -Dwlup.* to run");

        AtomizedNDD.initAtomizedNDD(4_000_000, 8_000_000, 40_000_000, 8_000_000);
        for (int w : W) AtomizedNDD.declareField(w);
        NDD.generateFields();

        // --- load rules, grouped by device -----------------------------------
        Map<String, List<Rule>> byDev = new HashMap<>();
        for (String line : Files.readAllLines(Path.of(rulesP))) {
            String[] t = line.trim().split("\\s+");
            if (t.length < 17 || !t[1].equals("filter")) continue;
            Rule r = new Rule();
            r.hit = NDD.ref(ruleToNDD(t));
            r.out = t[5];
            r.prio = Long.parseLong(t[16]);
            byDev.computeIfAbsent(t[2], k -> new ArrayList<>()).add(r);
        }

        // (dev PIPE outPort) -> list of (nextDev PIPE nextPort). A header arriving at
        // nextDev on nextPort forwards out nextDev's OTHER ports only (no-hairpin).
        Map<String, List<String>> edges = new HashMap<>();
        for (String line : Files.readAllLines(Path.of(System.getProperty("wlup.edges")))) {
            String[] e = line.trim().split("\\s+");
            if (e.length < 4) continue;
            edges.computeIfAbsent(key(e[0], e[1]), k -> new ArrayList<>()).add(key(e[2], e[3]));
        }

        // per device: first-match residual predicate per (real, non-drop) out_port
        Map<String, Map<String, Integer>> portPred = new HashMap<>();
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
            portPred.put(en.getKey(), pp);
        }

        List<String[]> sources = readCols(System.getProperty("wlup.sources")); // name dev port cidr
        List<String[]> probes = readCols(System.getProperty("wlup.probes"));   // name dev port

        // --- reachability: one flood per source, keyed (device, arrival-port) ---
        Map<String, TreeSet<String>> matrix = new HashMap<>();
        for (String[] pr : probes) matrix.put(pr[0], new TreeSet<>());

        for (String[] s : sources) {
            String sName = s[0], sDev = s[1], sPort = s[2], cidr = s[3];
            int h0 = NDD.ref(addrPred(SRC, cidr, "null"));   // {src in cidr}, rest free
            Map<String, Integer> reached = new HashMap<>();  // "dev|arrivalPort" -> NDD
            ArrayDeque<String> work = new ArrayDeque<>();
            // the source emits h0 out (sDev, sPort); its link-peer receives it
            for (String peer : edges.getOrDefault(key(sDev, sPort), List.of())) {
                reached.put(peer, NDD.ref(h0));
                work.add(peer);
            }
            while (!work.isEmpty()) {
                String cur = work.poll();
                int arrPort = cur.indexOf('|');
                String d = cur.substring(0, arrPort);
                String inPort = cur.substring(arrPort + 1);
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
            // arrival: probe reachable iff its device received a non-empty set on any port
            for (String[] p : probes) {
                if (s[0].equals(p[0])) continue;
                String pDev = p[1];
                boolean hit = false;
                for (Map.Entry<String, Integer> re : reached.entrySet()) {
                    if (re.getValue() != NDD.getFalse()
                            && re.getKey().substring(0, re.getKey().indexOf('|')).equals(pDev)) {
                        hit = true; break;
                    }
                }
                if (hit) matrix.get(p[0]).add(sName);
            }
            for (int v : reached.values()) NDD.deref(v);
            NDD.deref(h0);
        }

        // --- diff vs golden --------------------------------------------------
        HashSet<String> got = new HashSet<>();
        int gotPairs = 0;
        for (Map.Entry<String, TreeSet<String>> e : matrix.entrySet())
            for (String s : e.getValue()) { got.add(e.getKey() + " " + s); gotPairs++; }
        HashSet<String> golden = new HashSet<>();
        for (String line : Files.readAllLines(Path.of(System.getProperty("wlup.golden"))))
            if (!line.trim().isEmpty()) golden.add(line.trim());

        HashSet<String> over = new HashSet<>(got); over.removeAll(golden);   // NDD-only
        HashSet<String> under = new HashSet<>(golden); under.removeAll(got);  // BDD-only (unsound)
        System.out.println("[wlup-reach] NDD pairs=" + gotPairs + " golden=" + golden.size()
                + " OVER(ndd\\bdd)=" + over.size() + " UNDER(bdd\\ndd)=" + under.size());
        int shown = 0;
        for (String x : over) { if (shown++ >= 20) break; System.out.println("  OVER  " + x); }
        shown = 0;
        for (String x : under) { if (shown++ >= 20) break; System.out.println("  UNDER " + x); }
        assertEquals(0, under.size(), "UNSOUND: BDD-reachable pairs the NDD engine drops");
        assertEquals(0, over.size(), "OVER: pairs the NDD engine adds vs BDD");
        System.out.println("[wlup-reach] EXACT PARITY: " + golden.size() + " pairs");
    }

    private static String key(String dev, String port) { return dev + "|" + port; }

    private static List<String[]> readCols(String path) throws IOException {
        List<String[]> out = new ArrayList<>();
        for (String line : Files.readAllLines(Path.of(path)))
            if (!line.trim().isEmpty()) out.add(line.trim().split("\\s+"));
        return out;
    }

    // ---- per-field encoders (shared with NDDWlupSizingTest) ------------------

    private int ruleToNDD(String[] t) {
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

    private int addrPred(int field, String ip, String wild) {
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

    private int rangePred(int field, String lo, String hi) {
        if (lo.equals("null") || hi.equals("null")) return NDD.getTrue();
        long l = Long.parseLong(lo), h = Long.parseLong(hi);
        if (field == PROTO && l == 0 && h == 255) return NDD.getTrue();
        if (l == 0 && h == (1L << W[field]) - 1) return NDD.getTrue();
        if (l == h) return exact(field, l, W[field]);
        return interval(field, l, h, W[field]);
    }

    private int prefix(int field, int[] bits, int len) {
        int r = NDD.getTrue();
        for (int i = 0; i < len; i++)
            r = NDD.and(r, bits[i] == 1 ? NDD.getVar(field, i) : NDD.getNotVar(field, i));
        return r;
    }

    private int exact(int field, long value, int width) {
        int[] bits = new int[width];
        for (int i = 0; i < width; i++) bits[i] = (int) ((value >> (width - 1 - i)) & 1);
        return prefix(field, bits, width);
    }

    private int interval(int field, long lo, long hi, int width) {
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
