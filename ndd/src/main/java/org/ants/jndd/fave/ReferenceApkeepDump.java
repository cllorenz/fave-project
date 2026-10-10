package org.ants.jndd.fave;

import java.io.IOException;
import java.io.PrintWriter;
import java.nio.file.Files;
import java.nio.file.Paths;
import java.util.ArrayList;
import java.util.List;
import java.util.TreeMap;

import org.ants.jndd.diagram.AtomizedNDD;
import org.ants.jndd.diagram.NDD;

import application.wan.ndd.verifier.DPVerifierNDDAP;
import application.wan.ndd.verifier.apkeep.core.NetworkNDDAP;
import application.wan.ndd.verifier.apkeep.element.FieldNodeAP;
import jdd.bdd.BDD;

/**
 * The authors' reference APKeep(NDD) on a FaVe forwarding workload, for the
 * differential against NDD-APKeep (APKEEP_INCREMENTAL_SCOPE.md §4; the owner's
 * check on the port's faithfulness). FaVe harness code, not the reference.
 *
 * <p>Input (one directory, plain text, written by the FaVe side): {@code
 * topology.txt} ("d1 p1 d2 p2"), {@code devices.txt} (forwarding elements),
 * {@code edge_ports.txt} ("dev port"), {@code rules.txt} ("+ fwd dev ip len port
 * prio"). The reference's own entry point builds the network
 * ({@code DPVerifierNDDAP}); every rule gets a next hop (it drops rules without
 * one as control-plane routes) and is inserted in one batch
 * ({@code UpdateBatchRules}), which ends with the reference's re-atomization.
 *
 * <p>Output: per element and port, the destination set as its canonical list
 * of maximal prefixes, and whether the molecule equals the plain predicate;
 * then the number of destination atoms. Must run in its own JVM: the reference
 * declares its five-field layout, which FaVe's ({@link FaveFields}) excludes.
 */
public final class ReferenceApkeepDump {

	static final int DST = 1;   // the reference's DST_IP_FIELD

	public static void main(String[] args) throws IOException {
		String dir = args[0];
		ArrayList<String> topo = new ArrayList<>(Files.readAllLines(Paths.get(dir, "topology.txt")));
		ArrayList<String> edge = new ArrayList<>(Files.readAllLines(Paths.get(dir, "edge_ports.txt")));
		List<String> devices = Files.readAllLines(Paths.get(dir, "devices.txt"));
		ArrayList<String> fwd = new ArrayList<>();
		for (String r : Files.readAllLines(Paths.get(dir, "rules.txt"))) fwd.add(r + " 1.1.1.1");

		long t0 = System.nanoTime();
		DPVerifierNDDAP v = new DPVerifierNDDAP("fave", topo, edge, null);
		NetworkNDDAP net = v.apkeepNetworkModel;
		for (String d : devices) net.addForwardNode(d);
		net.UpdateBatchRules(fwd, new ArrayList<>());
		long t1 = System.nanoTime();

		BDD bdd = NDD.getBDDEngine();
		int[] vars = NDD.getBDDVars(DST);
		// the reference encodes a prefix MSB-first over vars[0..]: bit b (0 =
		// least significant) is vars[31 - b]
		int[] bit = new int[32];
		for (int b = 0; b < 32; b++) bit[b] = vars[31 - b];
		try (PrintWriter out = new PrintWriter(args[1])) {
			TreeMap<String, FieldNodeAP> nodes = new TreeMap<>(net.FieldNodes);
			for (FieldNodeAP e : nodes.values()) {
				for (String port : new TreeMap<>(e.ports_aps).keySet()) {
					int mol = NDD.ref(AtomizedNDD.atomizedToNDD(e.ports_aps.get(port)));
					Integer plain = e.ports_pred.get(port);
					boolean same = plain != null && plain == mol;
					out.println(e.name + " " + port + " " + same + " "
							+ PrefixDump.prefixes(bdd, mol, DST, bit));
					NDD.deref(mol);
				}
			}
			out.println("#atoms " + AtomizedNDD.getAllAtoms(DST).size());
			out.println("#build_s " + (t1 - t0) / 1e9);
		}
	}
}
