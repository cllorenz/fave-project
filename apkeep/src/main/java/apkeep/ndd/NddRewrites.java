package apkeep.ndd;

import java.util.Map;

import org.ants.jndd.diagram.AtomizedNDD;

import apkeep.elements.NATElement;

/** A NAT element's rewrite on molecules, as the NDD paper applies a
 *  transformer (App. F.3): the part a rule's port holds has the written field
 *  existentially removed and is then constrained to the new value; the part on
 *  "default" passes unchanged. The same packets {@code NATElement.rewriteAPs}
 *  maps on atomic predicates. */
final class NddRewrites {
	private NddRewrites() {}

	/** What leaves NAT element `nat` for traffic `in` (unreferenced). */
	static AtomizedNDD all(NddPorts ports, NATElement nat, AtomizedNDD in) {
		AtomizedNDD out = AtomizedNDD.getAtomizedFalse();
		for (String port : ports.ports(nat)) {
			AtomizedNDD part = AtomizedNDD.ref(one(ports, nat, port, in));
			AtomizedNDD next = AtomizedNDD.ref(AtomizedNDD.or(out, part));
			AtomizedNDD.deref(out);
			AtomizedNDD.deref(part);
			out = next;
		}
		AtomizedNDD.deref(out);
		return out;
	}

	/** What leaves through one rule port of `nat` (unreferenced). */
	static AtomizedNDD one(NddPorts ports, NATElement nat, String port, AtomizedNDD in) {
		AtomizedNDD hit = AtomizedNDD.ref(AtomizedNDD.and(in, ports.molecule(nat.getName(), port)));
		Map<String, NddPorts.Holder> rws = ports.rewritesOf(nat.getName());
		NddPorts.Holder rw = rws.get(port);
		if (port.equals("default") || rw == null || hit.isFalse()) {
			AtomizedNDD.deref(hit);
			return hit;
		}
		AtomizedNDD free = AtomizedNDD.ref(AtomizedNDD.exist(hit, rw.field));
		AtomizedNDD out = AtomizedNDD.and(free, rw.mol);
		AtomizedNDD.deref(free);
		AtomizedNDD.deref(hit);
		return out;
	}
}
