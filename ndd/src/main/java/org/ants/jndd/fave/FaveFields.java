package org.ants.jndd.fave;

import org.ants.jndd.diagram.AtomizedNDD;
import org.ants.jndd.diagram.NDD;

/**
 * FaVe's one NDD field layout, shared by every NDD engine in the JVM.
 *
 * <p>NDD's node tables, its BDD label engine and the per-field atoms of
 * {@link AtomizedNDD} are process-global statics, and a field layout can be
 * declared only once. NDD-Flood ({@link NddReachabilityEngine}) and NDD-APKeep
 * (the APKeep fork's NDD backend, {@code apkeep.ndd}) run in the same JVM --
 * the exactness gate and the from-zero oracle put both in one process -- so
 * both take their layout from here. The indices are NDD-Flood's, unchanged:
 * 0..5 the wl_up fields, then IPv4 addresses, VLAN (16 bits) and TCP flags;
 * since 2026-10-14 a packet filter's ingress and egress VLAN tags (SVLAN,
 * DVLAN: `-i eth1.<v>` and `-o eth1.<v>`), APPENDED so 0..9 are untouched.
 */
public final class FaveFields {

    public static final int SRC6 = 0, DST6 = 1, PROTO = 2, SPORT = 3, DPORT = 4,
            REL = 5, SRC4 = 6, DST4 = 7, VLAN = 8, FLAGS = 9, SVLAN = 10, DVLAN = 11;
    public static final int[] WIDTH = {128, 128, 8, 16, 16, 1, 32, 32, 16, 8, 16, 16};

    private static boolean ready = false;

    private FaveFields() {}

    /** Initialise the layout once per JVM (idempotent). */
    public static synchronized void ensure() {
        if (ready) return;
        AtomizedNDD.initAtomizedNDD(8_000_000, 16_000_000, 48_000_000, 16_000_000);
        for (int w : WIDTH) AtomizedNDD.declareField(w);
        NDD.generateFields();
        ready = true;
    }
}
