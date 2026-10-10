package apkeep.checker;

import java.util.ArrayList;
import java.util.List;

import common.PositionTuple;

/**
 * FaVe fork (APKEEP_INCREMENTAL_SCOPE.md §9, witness footprints): what a
 * REACHABLE answer rests on -- the path of its witness and the packets on it.
 *
 * <p>An existential "reachable" survives every update that leaves one
 * delivering path intact, and the walk is complete, so it would find a path
 * again. So the answer depends only on, at each hop, the port the witness left
 * the element by and the witness's packets there, and on the links it used.
 * A change at a hop that moves none of those packets OUT of that port -- or
 * moves packets INTO it -- leaves the witness delivering.
 *
 * <p>The packets at a hop: after the last rewrite on the path the header no
 * longer changes, so one concrete packet of what arrived at the target stands
 * for all of them ({@code PredicateOps.onePacket}). At the rewrite itself and
 * before it, the packet's earlier header would need the rewrite inverted;
 * those hops keep the sets that arrived there instead, as the explored
 * footprint does -- coarser, and still sound.
 *
 * <p>Every set is a handle in the network's {@code PredicateOps}, referenced;
 * {@link apkeep.core.Network#recordFootprint} takes them over.
 */
public final class Witness {

	/** One element on the path. {@code port} is the logical port the walk left
	 *  by (a VLAN, not its member ports, as a change names it), or null for a
	 *  rewrite, which leaves by its inline outport: any change there counts. */
	public static final class Hop {
		public final String element;
		public final String port;
		public final int fwd;
		public final int acl;

		public Hop(String element, String port, int fwd, int acl) {
			this.element = element;
			this.port = port;
			this.fwd = fwd;
			this.acl = acl;
		}
	}

	public final List<Hop> hops = new ArrayList<>();
	/** The ports the path left by, the source's included: a link change there
	 *  can cut it. */
	public final List<PositionTuple> egress = new ArrayList<>();
}
