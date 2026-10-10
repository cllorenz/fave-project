package apkeep.ndd;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.io.File;
import java.util.ArrayList;
import java.util.Collections;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Random;
import java.util.Set;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;

import apkeep.ApkeepTestBase;
import apkeep.checker.ReachabilityChecker;
import apkeep.core.Network;
import apkeep.utils.Evaluator;
import apkeep.utils.Parameters;
import common.PositionTuple;

/**
 * NDD-APKeep (Network backend "ndd") against BDD-APKeep on random networks
 * (APKEEP_INCREMENTAL_SCOPE.md §4, steps 4-5): after every insertion and
 * deletion, every molecule stands for its port's predicate, and every
 * host-to-host reachability answer equals a from-zero NDD build's and the
 * BDD backend's on the same rules.
 */
class NddBackendDifferentialTest extends ApkeepTestBase {

	private final List<Network> open = new ArrayList<>();
	/* Non-vacuity: answers compared, by value. */
	private int seenTrue = 0, seenFalse = 0;
	private boolean savedDivision;

	/* Collect the atomized table almost every update and query, so a
	 * molecule used without a reference would be collected under it --
	 * which the invariant and matrix checks would see. */
	@org.junit.jupiter.api.BeforeAll
	static void collectOften() {
		NddPorts.COLLECT_FLOOR = 20;
		// and re-atomize often, so molecules rebuilt by it are checked too
		NddPorts.REATOMIZE_EVERY = 7;
	}

	@org.junit.jupiter.api.AfterAll
	static void collectedOften() {
		assertTrue(NddPorts.collections > 10, "the atomized table was collected only "
				+ NddPorts.collections + " times");
	}

	@AfterEach
	void closeAll() {
		for (Network n : open) n.close();
		open.clear();
	}

	private static Evaluator eva(String name) throws Exception {
		return new Evaluator(name, File.createTempFile("apkeep-" + name, ".out").getAbsolutePath());
	}

	/** A network: topology, devices, filters, NATs; built from `rules`. */
	private static final class Spec {
		List<String> links = new ArrayList<>();
		List<String> devices = new ArrayList<>();
		Set<String> filters = new HashSet<>();
		Map<String, Set<String>> acls = null;
		Map<String, Set<String>> nats = null;
		List<PositionTuple> hosts = new ArrayList<>();
	}

	private Network build(Spec s, String backend, List<String> rules) throws Exception {
		Network net = new Network("diff-" + backend, backend);
		open.add(net);
		net.initializeNetwork(new ArrayList<>(s.links), s.devices, s.acls, null, s.nats,
				s.filters.isEmpty() ? null : s.filters);
		net.run(eva("diff-" + backend), rules);
		return net;
	}

	private static boolean ask(Network net, PositionTuple a, PositionTuple b, String cidr) {
		if (net.isNdd()) {
			NddReachabilityChecker c = new NddReachabilityChecker(net);
			return cidr == null ? c.isReachable(a, b) : c.isReachable(a, b, cidr);
		}
		ReachabilityChecker c = new ReachabilityChecker(net);
		return cidr == null ? c.isReachable(a, b) : c.isReachable(a, b, cidr);
	}

	private static Map<String, Boolean> matrix(Network net, Spec s, String cidr) {
		Map<String, Boolean> m = new HashMap<>();
		for (PositionTuple a : s.hosts) {
			for (PositionTuple b : s.hosts) {
				if (a.equals(b)) continue;
				m.put(a + "->" + b, ask(net, a, b, cidr));
			}
		}
		return m;
	}

	/** Insert `rules` one by one and delete some again on an NDD network; at
	 *  every step compare against from-zero NDD and BDD builds. */
	private void differential(Spec s, List<String> rules, Random rnd, String cidr) throws Exception {
		Network inc = build(s, "ndd", new ArrayList<>());
		List<String> present = new ArrayList<>();
		List<String> stream = new ArrayList<>();
		for (String r : rules) stream.add(r);
		// interleave deletions of rules already inserted
		List<String> ops = new ArrayList<>();
		for (String r : stream) {
			ops.add(r);
			if (rnd.nextInt(3) == 0) ops.add("DEL");
		}
		int step = 0;
		for (String op : ops) {
			String update;
			if (op.equals("DEL")) {
				if (present.isEmpty()) continue;
				String victim = present.remove(rnd.nextInt(present.size()));
				update = "-" + victim.substring(1);
			} else {
				update = op;
				present.add(op);
			}
			inc.applyUpdates(Collections.singletonList(update));
			step++;
			List<String> bad = inc.nddPorts().checkInvariants();
			assertTrue(bad.isEmpty(), "step " + step + " (" + update + "): " + bad);
			if (step % 3 != 0 && step != ops.size()) continue;
			Network zero = build(s, "ndd", present);
			bad = zero.nddPorts().checkInvariants();   // after the build's re-atomization
			assertTrue(bad.isEmpty(), "from zero, step " + step + ": " + bad);
			bad = inc.nddPorts().checkInvariants();    // and after its splits reached inc
			assertTrue(bad.isEmpty(), "step " + step + " after a from-zero build: " + bad);
			Network bdd = build(s, "bdd", present);
			Map<String, Boolean> mi = matrix(inc, s, cidr);
			for (boolean v : mi.values()) {
				if (v) seenTrue++; else seenFalse++;
			}
			assertEquals(matrix(zero, s, cidr), mi, "NDD incremental vs from zero, step " + step + " (" + update + ")");
			assertEquals(matrix(bdd, s, cidr), mi, "NDD vs BDD, step " + step + " (" + update + ")");
			zero.close();
			bdd.close();
			open.remove(zero);
			open.remove(bdd);
		}
	}

	private static final String[] PREFIXES = {
		"167772160 8", "167772160 16", "167837696 16", "167772160 24", "167772416 24",
		"167772160 25", "167772288 25", "0 0", "3232235520 16", "3232235520 24" };

	/** Routers r0..r3 in a ring with a host on each; random LPM routes. */
	private static Spec fibRing() {
		Spec s = new Spec();
		for (int i = 0; i < 4; i++) {
			int j = (i + 1) % 4;
			s.links.add("r" + i + " e" + j + " r" + j + " w" + i);
			s.links.add("r" + j + " w" + i + " r" + i + " e" + j);
			s.links.add("h" + i + " p r" + i + " h");
			s.links.add("r" + i + " h h" + i + " p");
			s.hosts.add(new PositionTuple("h" + i, "p"));
		}
		return s;
	}

	private static List<String> fibRules(Random rnd, int n) {
		List<String> out = new ArrayList<>();
		Set<String> seen = new HashSet<>();
		while (out.size() < n) {
			int i = rnd.nextInt(4);
			String[] pl = PREFIXES[rnd.nextInt(PREFIXES.length)].split(" ");
			String[] ports = {"e" + ((i + 1) % 4), "w" + ((i + 3) % 4), "h"};
			String port = ports[rnd.nextInt(ports.length)];
			String r = "+ fwd r" + i + " " + pl[0] + " " + pl[1] + " " + port + " " + pl[1];
			if (seen.add(r)) out.add(r);
		}
		return out;
	}

	@Test
	void fibRingInsertsAndDeletes() throws Exception {
		for (int seed = 1; seed <= 6; seed++) {
			Random rnd = new Random(seed);
			differential(fibRing(), fibRules(rnd, 18), rnd, null);
		}
		assertTrue(seenTrue > 20 && seenFalse > 20, "vacuous: " + seenTrue + " true, " + seenFalse + " false");
	}

	/** Negative control: the comparison sees a single missing rule. */
	@Test
	void comparisonDetectsAMissingRule() throws Exception {
		int caught = 0;
		for (int seed = 1; seed <= 6; seed++) {
			Random rnd = new Random(seed);
			Spec s = fibRing();
			List<String> rules = fibRules(rnd, 18);
			Network full = build(s, "ndd", rules);
			Map<String, Boolean> want = matrix(full, s, null);
			for (int k = 0; k < rules.size(); k++) {
				List<String> less = new ArrayList<>(rules);
				less.remove(k);
				Network bdd = build(s, "bdd", less);
				if (!matrix(bdd, s, null).equals(want)) caught++;
			}
		}
		assertTrue(caught > 10, "dropping one rule changed the matrix only " + caught + " times");
	}

	/** A packet filter between two routers: 5-tuple first-match rules,
	 *  including ties, VLAN, connection state and TCP flags. */
	private static Spec filterChain() {
		Spec s = new Spec();
		s.filters.add("fw");
		s.links.add("h0 p r0 h");
		s.links.add("r0 h h0 p");
		s.links.add("r0 out fw in");
		s.links.add("fw in r0 out");
		s.links.add("fw a r1 in");
		s.links.add("fw b r2 in");
		s.links.add("r1 in fw a");
		s.links.add("r2 in fw b");
		s.links.add("r1 h h1 p");
		s.links.add("r2 h h2 p");
		s.links.add("h1 p r1 h");
		s.links.add("h2 p r2 h");
		for (int i = 0; i < 3; i++) s.hosts.add(new PositionTuple("h" + i, "p"));
		return s;
	}

	private static List<String> filterRules(Random rnd, int n) {
		List<String> out = new ArrayList<>();
		out.add("+ fwd r0 0 0 out 0");
		out.add("+ fwd r0 3232235520 16 h 16");
		out.add("+ fwd r1 0 0 in 0");
		out.add("+ fwd r2 0 0 in 0");
		out.add("+ fwd r1 167772160 8 h 8");
		out.add("+ fwd r2 3232235520 16 h 16");
		String[] protos = {"6 6", "17 17", "0 255", "null null"};
		// sources and destinations from ONE list: equal-width NDD fields share
		// label variables, so the same prefix is the same label on both -- the
		// case NDD's atomization mixed up (ndd/FAVE_CHANGES.md §12)
		String[] dsts = {"10.0.0.0 0.255.255.255", "10.1.0.0 0.0.255.255", "192.168.0.0 0.0.255.255",
				"0.0.0.0 255.255.255.255"};
		String[] dports = {"80 80", "0 1023", "null null", "443 443"};
		String[] outs = {"a", "b", "a", "b", "in", "__drop__"};
		String[] vlans = {"null", "null", "10", "10,20"};
		String[] rels = {"null", "null", "0", "1"};
		String[] flags = {"null", "null", "1xxxxxxx"};
		Set<String> seen = new HashSet<>();
		while (out.size() < n) {
			String r = "+ filter fw fwd 0 " + outs[rnd.nextInt(outs.length)] + " "
					+ protos[rnd.nextInt(protos.length)] + " " + dsts[rnd.nextInt(dsts.length)] + " null null "
					+ dsts[rnd.nextInt(dsts.length)] + " " + dports[rnd.nextInt(dports.length)] + " "
					+ (10 * (1 + rnd.nextInt(4))) + " " + vlans[rnd.nextInt(vlans.length)] + " "
					+ rels[rnd.nextInt(rels.length)] + " " + flags[rnd.nextInt(flags.length)];
			if (seen.add(r)) out.add(r);
		}
		return out;
	}

	@Test
	void packetFilterInsertsAndDeletes() throws Exception {
		for (int seed = 1; seed <= 6; seed++) {
			Random rnd = new Random(100 + seed);
			differential(filterChain(), filterRules(rnd, 20), rnd, null);
		}
		assertTrue(seenTrue > 20 && seenFalse > 20, "vacuous: " + seenTrue + " true, " + seenFalse + " false");
	}

	@Test
	void ipv6SourceSeed() throws Exception {
		Spec s = filterChain();
		Random rnd = new Random(7);
		List<String> rules = new ArrayList<>();
		rules.add("+ fwd r0 0 0 out 0");
		rules.add("+ fwd r1 0 0 h 0");
		rules.add("+ fwd r2 0 0 h 0");
		rules.add("+ filter fw fwd 0 a 6 6 2001:db8:1::/48 null null null ::/0 null 80 80 30");
		rules.add("+ filter fw fwd 0 b 0 255 2001:db8::/32 null null null 2001:db8:2::/48 null null null 20");
		rules.add("+ filter fw fwd 0 __drop__ 0 255 2001:db8:1:5::/64 null null null ::/0 null null null 40");
		differential(s, rules, rnd, "2001:db8:1::/48");
		differential(s, rules, rnd, "2001:db8:3::/48");
		assertTrue(seenTrue > 0 && seenFalse > 0, "vacuous: " + seenTrue + " true, " + seenFalse + " false");
	}

	/** A NAT rewriting the VLAN on a route, gating two VLAN-admission ACLs
	 *  (NATReachabilityTest's network), with routes and rewrites changing. */
	@Test
	void vlanRewriteUpdates() throws Exception {
		savedDivision = Parameters.USE_DIVISION;
		Parameters.USE_DIVISION = false;
		try {
			Spec s = new Spec();
			s.links.add("src 1 r 2");
			s.links.add("r 1 d_inACL_p1_in inport");
			s.links.add("d_inACL_p1_in permit B 1");
			s.links.add("r 1 e_inACL_p1_in inport");
			s.links.add("e_inACL_p1_in permit C 1");
			s.devices.add("r");
			s.acls = Map.of("d", Set.of("inACL"), "e", Set.of("inACL"));
			s.nats = Map.of("r", Set.of("1"));
			s.hosts.add(new PositionTuple("src", "1"));
			s.hosts.add(new PositionTuple("B", "1"));
			s.hosts.add(new PositionTuple("C", "1"));
			String permitVlan = "0 255 0.0.0.0 255.255.255.255 null null "
					+ "0.0.0.0 255.255.255.255 null null 100 ";
			List<String> rules = List.of(
					"+ fwd r 167772160 8 1 8",
					"+ nat r 1 vlan 10.0.0.0 8 20",
					"+ acl d_inACL acl 0 permit " + permitVlan + "20",
					"+ acl e_inACL acl 0 permit " + permitVlan + "30",
					"+ nat r 1 vlan 10.128.0.0 9 30",
					"+ fwd r 3232235520 16 1 16",
					"+ nat r 1 vlan 192.168.0.0 16 20");
			for (int seed = 1; seed <= 4; seed++) {
				differential(s, rules, new Random(200 + seed), null);
			}
			assertTrue(seenTrue > 0 && seenFalse > 0, "vacuous: " + seenTrue + " true, " + seenFalse + " false");
		} finally {
			Parameters.USE_DIVISION = savedDivision;
		}
	}

	/** Two NDD networks in one JVM share the per-field atoms; a split made
	 *  for one must keep the other's molecules exact, and so must a
	 *  re-atomization. */
	@Test
	void twoNetworksShareAtoms() throws Exception {
		Random rnd = new Random(42);
		Spec s = fibRing();
		List<String> a = fibRules(rnd, 15);
		List<String> b = fibRules(rnd, 15);
		Network na = build(s, "ndd", a);
		Network nb = build(s, "ndd", new ArrayList<>());
		Map<String, Boolean> before = matrix(na, s, null);
		nb.applyUpdates(b);
		assertTrue(na.nddPorts().checkInvariants().isEmpty(), "A after B's splits");
		assertTrue(nb.nddPorts().checkInvariants().isEmpty(), "B");
		assertEquals(before, matrix(na, s, null), "A's answers after B's splits");
		NddPorts.reatomize();
		assertTrue(na.nddPorts().checkInvariants().isEmpty(), "A after re-atomization");
		assertTrue(nb.nddPorts().checkInvariants().isEmpty(), "B after re-atomization");
		assertEquals(before, matrix(na, s, null), "A's answers after re-atomization");
		Network zb = build(s, "ndd", b);
		assertEquals(matrix(zb, s, null), matrix(nb, s, null), "B incremental vs from zero");
	}
}
