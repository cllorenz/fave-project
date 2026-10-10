package apkeep.ndd;

import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Set;

import org.ants.jndd.diagram.AtomizedNDD;

import apkeep.checker.Loop;
import apkeep.core.Network;
import apkeep.elements.Element;
import apkeep.elements.ForwardElement;
import apkeep.elements.NATElement;
import common.PositionTuple;

/**
 * APKeep's per-update loop check ({@code Checker.checkProperty}, the
 * single-universe case) on molecules -- the invariant check APKeep runs by
 * default after every update, charged to NDD-APKeep as to BDD-APKeep
 * (INCREMENTAL_PLAN.md decision 1). Step for step the BDD walk: from each port
 * of the updated element that received moved traffic, follow the topology,
 * forward through each next element's ports, and report a loop when a port
 * repeats on the path. As there, a NAT's rule ports have no links, so a walk
 * reaching a NAT ends there.
 */
public class NddLoopChecker {
	private final Network net;
	private final NddPorts ports;
	private final Set<Loop> loops = new HashSet<>();

	public NddLoopChecker(Network net) {
		this.net = net;
		this.ports = net.nddPorts();
	}

	public Set<Loop> getLoops() {
		return loops;
	}

	public void checkProperty(String element_name, AtomizedNDD moved) {
		loops.clear();
		Element e = net.getElement(element_name);
		if (e == null) return;
		for (String port : e.getPorts()) {
			if (port.equals("default")) continue;
			AtomizedNDD held = ports.molecule(element_name, port);
			if (held.isFalse()) continue;
			AtomizedNDD aps = AtomizedNDD.ref(AtomizedNDD.and(moved, held));
			if (!aps.isFalse()) {
				for (String next_port : getPhysicalPorts(e, port)) {
					traverse(new PositionTuple(element_name, next_port), aps, new ArrayList<>());
				}
			}
			AtomizedNDD.deref(aps);
		}
	}

	private void traverse(PositionTuple cur_hop, AtomizedNDD fwd, List<PositionTuple> history) {
		if (fwd.isFalse()) return;
		if (history.contains(cur_hop)) {
			history.add(cur_hop);
			loops.add(new Loop(new HashSet<Integer>(), history, cur_hop));
			return;
		}
		history.add(cur_hop);
		Set<PositionTuple> connected = net.getConnectedPorts(cur_hop);
		if (connected == null) return;
		for (PositionTuple connected_pt : connected) {
			String next_node = connected_pt.getDeviceName();
			Element e = getElement(next_node);
			for (String port : e.getPorts()) {
				if (port.equals(connected_pt.getPortName())) continue;
				AtomizedNDD aps = AtomizedNDD.ref(e instanceof NATElement
						? NddRewrites.one(ports, (NATElement) e, port, fwd)
						: AtomizedNDD.and(fwd, ports.molecule(e.getName(), port)));
				for (String next_port : getPhysicalPorts(e, port)) {
					if (next_port.equals(connected_pt.getPortName())) continue;
					List<PositionTuple> new_history = new ArrayList<>(history);
					new_history.add(connected_pt);
					traverse(new PositionTuple(next_node, next_port), aps, new_history);
				}
				AtomizedNDD.deref(aps);
			}
		}
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
}
