package apkeep.checker;

import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Set;

import apkeep.core.APKeeper;
import apkeep.core.Network;
import apkeep.elements.ACLElement;
import apkeep.elements.Element;
import apkeep.elements.ForwardElement;
import apkeep.elements.NATElement;
import common.BDDACLWrapper;
import common.PositionTuple;

/**
 * Existential port-to-port reachability over APKeep's Port Predicate Map.
 *
 * FaVe fork addition (see APKEEP_BACKEND.md, P3): APKeep ships only forwarding-
 * loop detection, but its PPM + topology + per-port AP transfer (Element.
 * forwardAPs) are exactly the substrate for reachability. This mirrors the
 * forwarding semantics of {@link Checker#traversePPMDivision} (and its
 * non-division case) but, instead of collecting loops, answers: "if all packets
 * are injected at the source port, does any packet survive forwarding (and
 * ACLs) to arrive at the target port?".
 *
 * Packets are seeded as the full space ({@code BDDTrue}); forwarding APs and
 * ACL APs are tracked separately (as APKeep does when ACL division is active)
 * and a packet "arrives" iff the two overlap. With no ACL elements the ACL set
 * stays full, so this reduces to plain forwarding reachability.
 *
 * The walk is a depth-first search over simple paths (a port already on the
 * current path stops that branch, exactly as the loop traversal does); this
 * terminates on networks with forwarding loops and is sound and complete for
 * existential reachability, since a reachable target always has an acyclic
 * path. Arrival is only counted after at least one hop, so a port "reaches
 * itself" only through a real cycle (matching APKeep's loop semantics).
 */
public class ReachabilityChecker {

    private final Network net;

    // FaVe fork (Phase 7 instrumentation): per-query work counters. `nodesVisited`
    // counts every traverse() invocation (each (path-prefix, port) the DFS expands);
    // `branchesExplored` counts descents into a child hop. Reset at each public
    // isReachable() entry, read from Python after the call. These make the
    // per-pair simple-path enumeration -- the performance wall Phase B removes --
    // directly measurable, especially for UNREACHABLE pairs (no early exit).
    public static long nodesVisited = 0;
    public static long branchesExplored = 0;

    private static void resetCounters() {
        nodesVisited = 0;
        branchesExplored = 0;
    }
    // A header constraint the arriving traffic must satisfy at the target (P7b):
    // wl_stanford probes only accept vlan=0, so a query can require the packets
    // that reach the probe to overlap a given header BDD. BDDTrue = no constraint.
    private int targetHeader = BDDACLWrapper.BDDTrue;

    // Witness capture (FaVe fork, gap-2 diagnosis): on the first arrival, record
    // the exact hop sequence and the surviving forwarding APs, so we can compare
    // APKeep's over-approximating path against NetPlumber hop by hop. Public so a
    // JPype caller can read them after isReachable(...) returns true.
    public List<PositionTuple> witnessPath = null;
    public Set<Integer> witnessFwd = null;

    public ReachabilityChecker(Network net) {
        this.net = net;
    }

    private boolean arrive(List<PositionTuple> history, PositionTuple last, Set<Integer> fwd) {
        witnessPath = new ArrayList<>(history);
        witnessPath.add(last);
        witnessFwd = new HashSet<>(fwd);
        return true;
    }

    /** True iff traffic injected at {@code source} can reach {@code target}. */
    public boolean isReachable(PositionTuple source, PositionTuple target) {
        resetCounters();
        Set<Integer> fwd_aps = new HashSet<>();
        fwd_aps.add(BDDACLWrapper.BDDTrue);
        Set<Integer> acl_aps = new HashSet<>();
        acl_aps.add(BDDACLWrapper.BDDTrue);
        witnessPath = null;
        return traverse(source, fwd_aps, acl_aps, target, new ArrayList<PositionTuple>(), false);
    }

    /**
     * Reachability for traffic injected with a specific source-IP prefix.
     *
     * When ACL elements are present they typically filter on the source IP, so
     * seeding the ACL packet space with the full space ({@code BDDTrue}) would
     * over-approximate: a flow would count as reachable whenever *any* source is
     * permitted to the destination. Seeding the ACL AP set with exactly the
     * atomic predicates overlapping {@code src/srcPrefixLen} restricts the query
     * to the injected source. Forwarding is source-independent, so the
     * forwarding AP set still starts at the full space and is narrowed by the
     * per-hop destination forwarding. A {@code srcPrefixLen <= 0} means the full
     * space (no source constraint).
     */
    public boolean isReachable(PositionTuple source, PositionTuple target,
                               long src, int srcPrefixLen) {
        resetCounters();
        Set<Integer> fwd_aps = new HashSet<>();
        fwd_aps.add(BDDACLWrapper.BDDTrue);
        Set<Integer> acl_aps = net.getACLSeedAPs(src, srcPrefixLen);
        if (acl_aps.isEmpty()) return false;
        witnessPath = null;
        return traverse(source, fwd_aps, acl_aps, target, new ArrayList<PositionTuple>(), false);
    }

    /**
     * As above, but the packets that reach {@code target} must also overlap
     * {@code targetHeaderBDD} (e.g. vlan=0 for a wl_stanford probe). BDDTrue
     * imposes no constraint (equivalent to the 4-arg overload).
     */
    public boolean isReachable(PositionTuple source, PositionTuple target,
                               long src, int srcPrefixLen, int targetHeaderBDD) {
        this.targetHeader = targetHeaderBDD;
        return isReachable(source, target, src, srcPrefixLen);
    }

    /** Arrival test: the traffic forwarded here AND ACL-permitted is non-empty,
     *  and (if a target header constraint is set) overlaps it. Under ACL division
     *  the forwarding and ACL AP sets live in SEPARATE atomic-predicate universes,
     *  so overlap is a BDD intersection (bdd.and), not a shared index -- exactly
     *  what Element.hasOverlap does; we just additionally intersect the target
     *  header. BDDTrue on a side is the full space and intersects to the other. */
    private boolean arrives(Set<Integer> fwd_aps, Set<Integer> acl_aps) {
        if (targetHeader == BDDACLWrapper.BDDTrue) {
            return Element.hasOverlap(fwd_aps, acl_aps);
        }
        BDDACLWrapper bdd = APKeeper.bddengine;
        for (int f : fwd_aps) {
            for (int a : acl_aps) {
                int both = bdd.and(f, a);   // packets forwarded here AND permitted
                if (both == BDDACLWrapper.BDDFalse) continue;
                if (bdd.and(both, targetHeader) != BDDACLWrapper.BDDFalse) return true;
            }
        }
        return false;
    }

    private boolean traverse(PositionTuple cur_hop, Set<Integer> fwd_aps, Set<Integer> acl_aps,
                             PositionTuple target, List<PositionTuple> history, boolean moved) {
        nodesVisited++;
        if (fwd_aps.isEmpty() || acl_aps.isEmpty()) return false;
        if (cur_hop.getPortName().equals("deny")) return false;

        // Arrival: target reached (after >=1 hop) with non-empty forwarding AND
        // ACL packet space. Checked before the loop guard so a self-reaching
        // (looping) port is still detected.
        if (moved && cur_hop.equals(target) && arrives(fwd_aps, acl_aps))
            return arrive(history, cur_hop, fwd_aps);

        if (history.contains(cur_hop)) return false;  // simple-path pruning
        history.add(cur_hop);

        Set<PositionTuple> connected_ports = net.getConnectedPorts(cur_hop);
        if (connected_ports == null) return false;

        for (PositionTuple connected_pt : connected_ports) {
            // Arrival at a link-destination (ingress) port: traffic forwarded
            // out cur_hop is delivered to connected_pt over the L1 link, with
            // the current packet space (before the next element forwards). A
            // target may be either an egress port (a cur_hop above) or such an
            // ingress port (e.g. a probe attached to a device input).
            if (connected_pt.equals(target) && arrives(fwd_aps, acl_aps))
                return arrive(history, connected_pt, fwd_aps);

            Element e = getElement(connected_pt.getDeviceName());

            // A rewrite element (e.g. the Stanford mid-stage setting the egress
            // VLAN) transforms the actual packets: relabel BOTH the forwarding and
            // the ACL-permitted AP sets so the header change is reflected
            // consistently downstream (rewriteAPs passes unmatched APs through),
            // then continue out the NAT's inline output ("outport") to the
            // original downstream. Note the rewrite needs real atomic predicates,
            // so a NAT must sit downstream of a forwarding element (the {BDDTrue}
            // seed is not a network AP and rewrites to itself).
            if (e instanceof NATElement) {
                Set<Integer> rw_fwd = ((NATElement) e).rewriteAPs(new HashSet<>(fwd_aps));
                Set<Integer> rw_acl = ((NATElement) e).rewriteAPs(new HashSet<>(acl_aps));
                PositionTuple out = new PositionTuple(connected_pt.getDeviceName(), "outport");
                List<PositionTuple> new_history = new ArrayList<>(history);
                new_history.add(connected_pt);
                if (traverse(out, rw_fwd, rw_acl, target, new_history, true)) return true;
                continue;
            }

            for (String port : e.getPorts()) {
                if (port.equals(connected_pt.getPortName())) continue;

                Set<Integer> next_fwd = fwd_aps;
                Set<Integer> next_acl = acl_aps;
                if (e instanceof ACLElement && net.isDivisionActivated()) {
                    next_acl = e.forwardAPs(port, acl_aps);
                } else if (e instanceof ACLElement) {
                    // Single-universe (no division): the ACL lives in the same AP
                    // universe as forwarding/NAT, so it filters the forwarding set
                    // directly -- letting a VLAN admission compose with an upstream
                    // VLAN rewrite (the divergence division would cause).
                    next_fwd = e.forwardAPs(port, fwd_aps);
                } else {
                    next_fwd = e.forwardAPs(port, fwd_aps);
                }

                for (String next_port : getPhysicalPorts(e, port)) {
                    if (next_port.equals(connected_pt.getPortName())) continue;
                    PositionTuple next_hop = new PositionTuple(connected_pt.getDeviceName(), next_port);
                    List<PositionTuple> new_history = new ArrayList<>(history);
                    new_history.add(connected_pt);
                    branchesExplored++;
                    if (traverse(next_hop, next_fwd, next_acl, target, new_history, true)) return true;
                }
            }
        }
        return false;
    }

    // --- helpers (mirror Checker's private helpers) -------------------------

    private Element getElement(String node_name) {
        if (net.isACLNode(node_name)) return net.getACLElement(node_name);
        return net.getElement(node_name);
    }

    private Set<String> getPhysicalPorts(Element e, String port) {
        if (e instanceof ForwardElement && port.toLowerCase().startsWith("vlan")) {
            return ((ForwardElement) e).getVlanPorts(port);
        }
        Set<String> ports = new HashSet<>();
        ports.add(port);
        return ports;
    }
}
