package org.ants.jndd.diagram;

import static org.junit.jupiter.api.Assumptions.assumeTrue;
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.io.IOException;
import java.net.InetAddress;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;

import org.junit.jupiter.api.Test;

/**
 * §2.5b engine sizing: build the wl_up rule predicates as per-field NDDs, atomize
 * with the (FaVe-restored) AtomizedNDD, and report the Sigma-over-fields atom count
 * -- the NDD analogue of the BDD global atomic-predicate partition (baseline
 * ap_num=14561). This is the make-or-break perf measurement of the NDD bet (§2.0 was
 * MIXED). It also exercises the ported atomization end-to-end on real data.
 *
 * Runs only when -Dwlup.rules=<path to newline-delimited "+ filter ..." rules> is set
 * (skips otherwise). The rules are dumped from the FaVe/APKeep adapter (all 6560 are
 * `+ filter`). Fields: SRC6(128) DST6(128) PROTO(8) SPORT(16) DPORT(16) RELATED(1).
 *
 * NOTE: this atomizes the RAW rule hit-predicates (pre-forwarding). The BDD 14561 is
 * the post-forwarding network partition, so this Sigma is an estimate/lower-bound of
 * the engine's per-field atom count; the per-field-vs-joint ratio is the point.
 */
class NDDWlupSizingTest {

    static final int SRC = 0, DST = 1, PROTO = 2, SPORT = 3, DPORT = 4, REL = 5;
    static final int[] W = {128, 128, 8, 16, 16, 1};

    @Test
    void wlupPerFieldAtomSizing() throws IOException {
        String path = System.getProperty("wlup.rules");
        assumeTrue(path != null, "set -Dwlup.rules=<rules file> to run");

        AtomizedNDD.initAtomizedNDD(4_000_000, 4_000_000, 20_000_000, 4_000_000);
        for (int w : W) AtomizedNDD.declareField(w);
        NDD.generateFields();

        List<String> lines = Files.readAllLines(Path.of(path));
        HashSet<Integer> preds = new HashSet<>();
        int parsed = 0;
        for (String line : lines) {
            line = line.trim();
            if (line.isEmpty()) continue;
            int p = ruleToNDD(line.split("\\s+"));
            if (p != -1) { preds.add(NDD.ref(p)); parsed++; }
        }
        System.out.println("[wlup-sizing] rules=" + parsed + " distinct-predicates=" + preds.size());

        java.util.HashMap<Integer, HashSet<Integer>[]> out = new java.util.HashMap<>();
        java.util.HashMap<Integer, AtomizedNDD> mol = AtomizedNDD.atomization(preds, out);

        int sigma = 0;
        String[] name = {"src6", "dst6", "proto", "sport", "dport", "rel"};
        StringBuilder sb = new StringBuilder();
        for (int f = 0; f <= NDD.getFieldNum(); f++) {
            int n = AtomizedNDD.getAllAtoms(f).size();
            sigma += n;
            sb.append(name[f]).append("=").append(n).append(" ");
        }
        System.out.println("[wlup-sizing] per-field atoms: " + sb);
        System.out.println("[wlup-sizing] SIGMA (NDD per-field) = " + sigma
                + "   vs BDD global ap_num = 14561   => " + String.format("%.1fx", 14561.0 / sigma));
        assertEquals(sigma, AtomizedNDD.totalCountOfAtoms());

        // recombination spot-check on a sample (the atomization is faithful iff each
        // predicate rebuilds exactly from its atoms)
        int checked = 0;
        for (int pr : preds) {
            assertEquals(pr, AtomizedNDD.atomizedToNDD(mol.get(pr)),
                    "predicate does not recombine from its atoms");
            if (++checked >= 500) break;
        }
        System.out.println("[wlup-sizing] recombination verified on " + checked + " predicates");
    }

    /** One "+ filter ..." rule -> its multi-field NDD hit predicate (int), or -1. */
    private int ruleToNDD(String[] t) {
        if (t.length < 17 || !t[1].equals("filter")) return -1;
        // + filter dev filter 0 out plo phi sip swild slo shi dip dwild dlo dhi prio [vlan] [rel]
        int r = NDD.getTrue();
        r = NDD.and(r, rangePred(PROTO, t[6], t[7]));            // proto
        r = NDD.and(r, addrPred(SRC, t[8], t[9]));               // src
        r = NDD.and(r, rangePred(SPORT, t[10], t[11]));          // sport
        r = NDD.and(r, addrPred(DST, t[12], t[13]));             // dst
        r = NDD.and(r, rangePred(DPORT, t[14], t[15]));          // dport
        String rel = t.length > 18 ? t[18] : "null";
        if (!rel.equals("null")) r = NDD.and(r, exact(REL, Long.parseLong(rel), 1));
        return r;
    }

    /** Address slot -> field predicate. IPv6 "addr[/len]" + "null"; IPv4 all-space = any. */
    private int addrPred(int field, String ip, String wild) {
        if (ip.equals("0.0.0.0") && wild.equals("255.255.255.255")) return NDD.getTrue();
        int len = 128;
        String addr = ip;
        int slash = ip.indexOf('/');
        if (slash >= 0) { addr = ip.substring(0, slash); len = Integer.parseInt(ip.substring(slash + 1)); }
        byte[] b;
        try { b = InetAddress.getByName(addr).getAddress(); }
        catch (Exception e) { throw new RuntimeException("bad ip " + ip, e); }
        if (b.length != 16) return NDD.getTrue();   // not IPv6 (shouldn't happen in wl_up)
        int[] bits = new int[len];
        for (int i = 0; i < len; i++) bits[i] = (b[i >> 3] >> (7 - (i & 7))) & 1;
        return prefix(field, bits, len);
    }

    /** proto/port slot: "null" -> any; "0".."255" for proto or "lo".."hi" -> range. */
    private int rangePred(int field, String lo, String hi) {
        if (lo.equals("null") || hi.equals("null")) return NDD.getTrue();
        long l = Long.parseLong(lo), h = Long.parseLong(hi);
        if (field == PROTO && l == 0 && h == 255) return NDD.getTrue();
        if (l == 0 && h == (1L << W[field]) - 1) return NDD.getTrue();
        if (l == h) return exact(field, l, W[field]);
        return interval(field, l, h, W[field]);
    }

    /** field's top len bits fixed to bits[]. */
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

    /** [lo,hi] over `width` bits -> OR of prefix decomposition. */
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
            cur += (1L << (width - plen));
            if (cur == 0) break; // overflow guard
        }
        return result;
    }
}
