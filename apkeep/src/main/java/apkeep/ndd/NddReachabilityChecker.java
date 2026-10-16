package apkeep.ndd;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;

import org.ants.jndd.diagram.AtomizedNDD;
import org.ants.jndd.diagram.NDD;

import apkeep.checker.Witness;
import apkeep.core.Network;
import apkeep.elements.Element;
import apkeep.elements.ForwardElement;
import apkeep.elements.NATElement;
import common.PositionTuple;

/**
 * {@link apkeep.checker.ReachabilityChecker} on NDD-APKeep's molecules
 * (APKEEP_INCREMENTAL_SCOPE.md §4). The walk is the BDD checker's, step for
 * step -- simple paths, arrival at an egress or a link-destination port after
 * at least one hop, a NAT relabelling the traffic and continuing out its
 * "outport", "deny" a dead end -- with the forwarded space a molecule and each
 * hop {@code AtomizedNDD.and} with the port's molecule, as the reference's
 * {@code CheckerNDDAP} does.
 *
 * <p>One difference, because an NDD network has one universe: the source seed
 * is the source's EXACT space (plain NDD), carried beside the molecule and
 * intersected at arrival -- what the BDD checker does for an IPv6 source
 * (Lever B), here for IPv4 too. BDD-APKeep's IPv4 seed is the ACL-universe
 * atoms overlapping the source, which exists only under its ACL division. As
 * in the BDD checker, the seed passes a NAT unchanged, so it is exact only
 * where nothing rewrites the source; the adapter does not seed such a source.
 */
public class NddReachabilityChecker {

	private final Network net;
	private final NddPorts ports;
	private final NddEncoder enc;

	public static long nodesVisited = 0;
	public static long branchesExplored = 0;

	private int targetHeader = NDD.getTrue();
	private int relatedHeader = NDD.getTrue();

	/* Footprints, as the BDD checker's: per element the forwarded and the
	 * seed space that ARRIVED there, and the ports the walk left by. */
	public Map<String, AtomizedNDD> fpFwd = null;
	public Map<String, Integer> fpAcl = null;
	public Set<PositionTuple> fpPorts = null;

	public List<PositionTuple> witnessPath = null;

	/* Witness footprints (APKEEP_INCREMENTAL_SCOPE.md §9), as the BDD
	 * checker's: the hops on the current path -- {element, logical port or
	 * null for a rewrite, the molecule and the seed that arrived there} -- and
	 * the ports the path left by. */
	public Witness witness = null;
	public PositionTuple lastTarget = null;
	private final boolean recordWitness;
	private final List<Object[]> hopStack = new ArrayList<>();
	private final List<PositionTuple> egressStack = new ArrayList<>();

	public NddReachabilityChecker(Network net) {
		this.net = net;
		this.ports = net.nddPorts();
		this.enc = net.nddEncoder();
		if (net.isTracking()) {
			fpFwd = new HashMap<>();
			fpAcl = new HashMap<>();
			fpPorts = new HashSet<>();
		}
		recordWitness = net.isTracking() && net.footprintWitness();
	}

	private void begin(PositionTuple target) {
		witnessPath = null;
		witness = null;
		lastTarget = target;
		hopStack.clear();
		egressStack.clear();
	}

	public void setRelatedHeader(int related) { this.relatedHeader = related; }

	public void andArrivalHeader(int header) {
		this.relatedHeader = NDD.isTrue(this.relatedHeader) ? header
				: NDD.ref(NDD.and(this.relatedHeader, header));
	}

	private static void resetCounters() {
		nodesVisited = 0;
		branchesExplored = 0;
	}

	private void note(Element e, AtomizedNDD fwd, int acl) {
		if (fpFwd == null || e == null) return;
		AtomizedNDD old = fpFwd.get(e.getName());
		if (old == null) {
			fpFwd.put(e.getName(), AtomizedNDD.ref(fwd));
		} else {
			fpFwd.put(e.getName(), AtomizedNDD.ref(AtomizedNDD.or(old, fwd)));
			AtomizedNDD.deref(old);
		}
		Integer a = fpAcl.get(e.getName());
		if (a == null) {
			fpAcl.put(e.getName(), NDD.ref(acl));
		} else {
			fpAcl.put(e.getName(), NDD.ref(NDD.or(a, acl)));
			NDD.deref(a);
		}
	}

	private boolean arrive(List<PositionTuple> history, PositionTuple last, AtomizedNDD fwd, int acl) {
		witnessPath = new ArrayList<>(history);
		witnessPath.add(last);
		if (recordWitness) witness = buildWitness(fwd, acl);
		return true;
	}

	/** {@link apkeep.checker.ReachabilityChecker}'s witness, on NDDs. */
	private Witness buildWitness(AtomizedNDD fwd, int acl) {
		NddOps ops = NddOps.INSTANCE;
		int space = NDD.ref(AtomizedNDD.atomizedToNDD(fwd));
		int arrived = ops.and(space, acl);
		NDD.deref(space);
		for (int header : new int[] {targetHeader, relatedHeader}) {
			int next = ops.and(arrived, header);
			NDD.deref(arrived);
			arrived = next;
		}
		int packet = ops.onePacket(arrived);
		NDD.deref(arrived);
		int lastRewrite = -1;
		for (int i = 0; i < hopStack.size(); i++) if (hopStack.get(i)[1] == null) lastRewrite = i;
		Witness w = new Witness();
		for (int i = 0; i < hopStack.size(); i++) {
			Object[] hop = hopStack.get(i);
			w.hops.add(i <= lastRewrite
					? new Witness.Hop((String) hop[0], (String) hop[1],
							NDD.ref(AtomizedNDD.atomizedToNDD((AtomizedNDD) hop[2])), NDD.ref((Integer) hop[3]))
					: new Witness.Hop((String) hop[0], (String) hop[1], NDD.ref(packet), NDD.ref(packet)));
		}
		NDD.deref(packet);
		w.egress.addAll(egressStack);
		return w;
	}

	public boolean isReachable(PositionTuple source, PositionTuple target) {
		begin(target);
		return start(source, target, NDD.getTrue());
	}

	/** Traffic from source IPv4 prefix src/len (len &lt;= 0: any source). */
	public boolean isReachable(PositionTuple source, PositionTuple target, long src, int len) {
		begin(target);
		int seed = len <= 0 ? NDD.getTrue() : enc.srcPrefix(src, len);
		boolean r = start(source, target, seed);
		NDD.deref(seed);
		return r;
	}

	public boolean isReachable(PositionTuple source, PositionTuple target, long src, int len,
			int targetHeaderNDD) {
		this.targetHeader = targetHeaderNDD;
		return isReachable(source, target, src, len);
	}

	/** Traffic from a source IPv6 prefix (null/empty: any source). */
	public boolean isReachable(PositionTuple source, PositionTuple target, String srcCidr) {
		begin(target);
		int seed = enc.srcIP6(srcCidr);
		if (NDD.isFalse(seed)) return false;
		boolean r = start(source, target, seed);
		NDD.deref(seed);
		return r;
	}

	private boolean start(PositionTuple source, PositionTuple target, int seed) {
		NddPorts.maybeCollect();   // between queries nothing unreferenced is in use
		NddPorts.enterQueries();   // the reference's operation cache (FAVE_CHANGES.md §15)
		resetCounters();
		witnessPath = null;
		return traverse(source, AtomizedNDD.getAtomizedTrue(), seed, target,
				new ArrayList<PositionTuple>(), false);
	}

	private boolean arrives(AtomizedNDD fwd, int acl) {
		if (fwd.isFalse() || NDD.isFalse(acl)) return false;
		int header = NDD.ref(NDD.and(targetHeader, relatedHeader));
		if (NDD.isTrue(header) && NDD.isTrue(acl)) {
			return true;
		}
		int space = NDD.ref(AtomizedNDD.atomizedToNDD(fwd));
		int both = NDD.ref(NDD.and(space, acl));
		int all = NDD.ref(NDD.and(both, header));
		boolean hit = !NDD.isFalse(all);
		NDD.deref(all);
		NDD.deref(both);
		NDD.deref(space);
		NDD.deref(header);
		return hit;
	}

	private boolean traverse(PositionTuple cur_hop, AtomizedNDD fwd, int acl,
			PositionTuple target, List<PositionTuple> history, boolean moved) {
		nodesVisited++;
		if (fwd.isFalse() || NDD.isFalse(acl)) return false;
		if (cur_hop.getPortName().equals("deny")) return false;

		if (moved && cur_hop.equals(target) && arrives(fwd, acl))
			return arrive(history, cur_hop, fwd, acl);

		if (history.contains(cur_hop)) return false;
		history.add(cur_hop);
		if (fpPorts != null) fpPorts.add(cur_hop);

		Set<PositionTuple> connected_ports = net.getConnectedPorts(cur_hop);
		if (connected_ports == null) return false;

		egressStack.add(cur_hop);
		try {
			return traverseLinks(connected_ports, fwd, acl, target, history);
		} finally {
			egressStack.remove(egressStack.size() - 1);
		}
	}

	private boolean traverseLinks(Set<PositionTuple> connected_ports, AtomizedNDD fwd, int acl,
			PositionTuple target, List<PositionTuple> history) {
		for (PositionTuple connected_pt : connected_ports) {
			if (connected_pt.equals(target) && arrives(fwd, acl))
				return arrive(history, connected_pt, fwd, acl);

			Element e = getElement(connected_pt.getDeviceName());
			note(e, fwd, acl);

			if (e instanceof NATElement) {
				AtomizedNDD rw = AtomizedNDD.ref(NddRewrites.all(ports, (NATElement) e, fwd));
				PositionTuple out = new PositionTuple(connected_pt.getDeviceName(), "outport");
				List<PositionTuple> new_history = new ArrayList<>(history);
				new_history.add(connected_pt);
				hopStack.add(new Object[] {e.getName(), null, fwd, acl});
				boolean hit;
				try {
					hit = traverse(out, rw, acl, target, new_history, true);
				} finally {
					hopStack.remove(hopStack.size() - 1);
				}
				AtomizedNDD.deref(rw);
				if (hit) return true;
				continue;
			}

			for (String port : e.getPorts()) {
				if (port.equals(connected_pt.getPortName())) continue;
				// one universe: an ACL filters the forwarded space itself
				AtomizedNDD next_fwd = AtomizedNDD.ref(
						AtomizedNDD.and(fwd, ports.molecule(e.getName(), port)));
				hopStack.add(new Object[] {e.getName(), port, fwd, acl});
				try {
					for (String next_port : getPhysicalPorts(e, port)) {
						if (next_port.equals(connected_pt.getPortName())) continue;
						PositionTuple next_hop = new PositionTuple(connected_pt.getDeviceName(), next_port);
						List<PositionTuple> new_history = new ArrayList<>(history);
						new_history.add(connected_pt);
						branchesExplored++;
						if (traverse(next_hop, next_fwd, acl, target, new_history, true)) {
							AtomizedNDD.deref(next_fwd);
							return true;
						}
					}
				} finally {
					hopStack.remove(hopStack.size() - 1);
				}
				AtomizedNDD.deref(next_fwd);
			}
		}
		return false;
	}

	private Element getElement(String node_name) {
		if (net.isACLNode(node_name)) return net.getACLElement(node_name);
		return net.getElement(node_name);
	}

	private Set<String> getPhysicalPorts(Element e, String port) {
		if (e instanceof ForwardElement && port.toLowerCase().startsWith("vlan")) {
			return ((ForwardElement) e).getVlanPorts(port);
		}
		Set<String> s = new HashSet<>();
		s.add(port);
		return s;
	}

	/** Release the footprint (the network copies what it keeps). */
	public void releaseFootprint() {
		if (fpFwd == null) return;
		for (AtomizedNDD m : fpFwd.values()) AtomizedNDD.deref(m);
		for (int a : fpAcl.values()) NDD.deref(a);
		fpFwd.clear();
		fpAcl.clear();
	}
}
