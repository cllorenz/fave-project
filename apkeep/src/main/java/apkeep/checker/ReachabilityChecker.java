package apkeep.checker;

import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Set;

import apkeep.core.Network;
import apkeep.elements.ACLElement;
import apkeep.elements.Element;
import apkeep.elements.ForwardElement;
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

    public ReachabilityChecker(Network net) {
        this.net = net;
    }

    /** True iff traffic injected at {@code source} can reach {@code target}. */
    public boolean isReachable(PositionTuple source, PositionTuple target) {
        Set<Integer> fwd_aps = new HashSet<>();
        fwd_aps.add(BDDACLWrapper.BDDTrue);
        Set<Integer> acl_aps = new HashSet<>();
        acl_aps.add(BDDACLWrapper.BDDTrue);
        return traverse(source, fwd_aps, acl_aps, target, new ArrayList<PositionTuple>(), false);
    }

    private boolean traverse(PositionTuple cur_hop, Set<Integer> fwd_aps, Set<Integer> acl_aps,
                             PositionTuple target, List<PositionTuple> history, boolean moved) {
        if (fwd_aps.isEmpty() || acl_aps.isEmpty()) return false;
        if (cur_hop.getPortName().equals("deny")) return false;

        // Arrival: target reached (after >=1 hop) with non-empty forwarding AND
        // ACL packet space. Checked before the loop guard so a self-reaching
        // (looping) port is still detected.
        if (moved && cur_hop.equals(target) && Element.hasOverlap(fwd_aps, acl_aps)) return true;

        if (history.contains(cur_hop)) return false;  // simple-path pruning
        history.add(cur_hop);

        Set<PositionTuple> connected_ports = net.getConnectedPorts(cur_hop);
        if (connected_ports == null) return false;

        for (PositionTuple connected_pt : connected_ports) {
            Element e = getElement(connected_pt.getDeviceName());
            for (String port : e.getPorts()) {
                if (port.equals(connected_pt.getPortName())) continue;

                Set<Integer> next_fwd = fwd_aps;
                Set<Integer> next_acl = acl_aps;
                if (e instanceof ACLElement) {
                    next_acl = e.forwardAPs(port, acl_aps);
                } else {
                    next_fwd = e.forwardAPs(port, fwd_aps);
                }

                for (String next_port : getPhysicalPorts(e, port)) {
                    if (next_port.equals(connected_pt.getPortName())) continue;
                    PositionTuple next_hop = new PositionTuple(connected_pt.getDeviceName(), next_port);
                    List<PositionTuple> new_history = new ArrayList<>(history);
                    new_history.add(connected_pt);
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
