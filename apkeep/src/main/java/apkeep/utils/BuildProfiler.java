package apkeep.utils;

import java.io.FileWriter;
import java.io.IOException;
import java.io.PrintWriter;
import java.util.Set;

import apkeep.core.APKeeper;
import apkeep.core.Network;
import apkeep.elements.Element;

/**
 * FaVe fork (Phase 7 / Phase C): a STREAMING build profiler for APKeep's from-zero
 * network construction. The full wl_up build is a single synchronous call into
 * {@link Network#run}, so a Python (JPype) caller is blocked for its whole duration
 * and cannot poll mid-build -- the sampler therefore lives here, on the Java side, as
 * a daemon thread that snapshots shared counters on a wall-clock interval and appends
 * one JSON object per line, flushed per line, so a killed run still leaves a parseable
 * growth curve (an aborted run is a first-class result: the SHAPE of ap_num/element/
 * BDD growth is what discriminates a partition blow-up from element/PPM bookkeeping).
 *
 * Each metric maps to the cost hypothesis it discriminates (see APKEEP_TUM_UP_PLAN.md
 * Phase C): ap_num -> global AP partition (case a); elements/ppm_entries -> bookkeeping
 * (case b); bdd_used/bdd_mem -> BDD encoding + memory ceiling (case c); the encode/
 * insert/ppm/merge cumulative timers -> attribution across the build's inner steps.
 *
 * Profiling is OPT-IN: {@link #start} is a no-op when the path is null/empty, so normal
 * runs and the exactness gate pay nothing but a few ns/rule for the always-on counters.
 * The per-sample reads are best-effort and individually guarded -- a metric that touches
 * a concurrently-mutated collection may throw, in which case that field is emitted null
 * for that sample rather than killing the profiler.
 */
public class BuildProfiler {

    // Always-on counters (single writer: the build thread). Cheap for the sampler to
    // read; volatile so the sampler sees fresh, monotone values.
    public static volatile long rulesApplied = 0;
    public static volatile long totalRules = 0;
    public static volatile long encodeNanos = 0;   // e.encodeOneRule (ConvertACLRule)
    public static volatile long insertNanos = 0;   // e.insert/removeOneRule (AP splits)
    public static volatile long ppmNanos = 0;      // e.updatePortPredicateMap
    public static volatile long mergeNanos = 0;    // soft/hardMergeAPBatch (tryMergeAP)

    private static Thread thread;
    private static volatile boolean running = false;
    private static Network net;
    private static PrintWriter out;
    private static long t0;
    private static long intervalMs;

    public static void reset() {
        // NB: totalRules is set by the caller before start() and must survive reset.
        rulesApplied = 0;
        encodeNanos = 0; insertNanos = 0; ppmNanos = 0; mergeNanos = 0;
    }

    /** Begin streaming to {@code path} every {@code interval} ms. No-op if path is
     *  null/empty (profiling disabled). */
    public static void start(Network network, String path, long interval) {
        if (path == null || path.isEmpty()) return;
        net = network;
        intervalMs = interval;
        reset();
        try {
            out = new PrintWriter(new FileWriter(path, false));
        } catch (IOException e) {
            out = null;
            return;
        }
        t0 = System.nanoTime();
        running = true;
        thread = new Thread(() -> {
            while (running) {
                sample("running");
                try {
                    Thread.sleep(intervalMs);
                } catch (InterruptedException e) {
                    break;
                }
            }
        });
        thread.setDaemon(true);
        thread.setName("apkeep-build-profiler");
        thread.start();
    }

    /** Emit one JSONL sample. Synchronized so the periodic thread and the final
     *  stop()-sample never interleave a half-written line. */
    public static synchronized void sample(String phase) {
        if (out == null) return;
        StringBuilder sb = new StringBuilder(256);
        long elapsedMs = (System.nanoTime() - t0) / 1_000_000L;
        sb.append("{\"ms\":").append(elapsedMs);
        sb.append(",\"phase\":\"").append(phase).append('"');
        sb.append(",\"rules\":").append(rulesApplied);
        sb.append(",\"total_rules\":").append(totalRules);
        appendMetric(sb, "ap_num", () -> (long) net.getAPNum());
        appendMetric(sb, "elements", () -> (long) net.numElements());
        appendMetric(sb, "ports", () -> (long) net.numPorts());
        appendMetric(sb, "ppm_entries", () -> net.totalPPMEntries());
        appendMetric(sb, "bdd_mem", () -> APKeeper.bddengine.getBDD().getMemoryUsage());
        appendMetric(sb, "bdd_used", () -> {
            jdd.bdd.BDD b = APKeeper.bddengine.getBDD();
            return (long) (b.debug_table_size() - b.debug_free_nodes_count());
        });
        sb.append(",\"encode_ms\":").append(encodeNanos / 1_000_000L);
        sb.append(",\"insert_ms\":").append(insertNanos / 1_000_000L);
        sb.append(",\"ppm_ms\":").append(ppmNanos / 1_000_000L);
        sb.append(",\"merge_ms\":").append(mergeNanos / 1_000_000L);
        sb.append('}');
        out.println(sb.toString());
        out.flush();
    }

    private interface LongMetric { long get() throws Exception; }

    private static void appendMetric(StringBuilder sb, String key, LongMetric m) {
        sb.append(",\"").append(key).append("\":");
        try {
            sb.append(m.get());
        } catch (Throwable t) {
            sb.append("null");   // touched a concurrently-mutated structure this tick
        }
    }

    /** Stop streaming and write one final sample. */
    public static void stop() {
        running = false;
        if (thread != null) {
            thread.interrupt();
            try { thread.join(1000); } catch (InterruptedException e) { /* ignore */ }
        }
        if (out != null) {
            sample("final");
            out.flush();
            out.close();
            out = null;
        }
    }
}
