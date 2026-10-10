package apkeep.ndd;

import java.io.PrintWriter;
import java.nio.file.Files;
import java.nio.file.Paths;
import java.util.ArrayList;
import java.util.List;
import java.util.TreeSet;

import org.ants.jndd.diagram.AtomizedNDD;
import org.ants.jndd.diagram.NDD;
import org.ants.jndd.fave.FaveFields;
import org.ants.jndd.fave.PrefixDump;

import apkeep.core.Network;
import apkeep.utils.Evaluator;

/**
 * NDD-APKeep's side of the reference differential (APKEEP_INCREMENTAL_SCOPE.md
 * §4): the same input directory as {@code org.ants.jndd.fave.ReferenceApkeepDump}
 * -- topology, forwarding elements, "+ fwd" rules -- built by
 * {@code Network(name, "ndd")}, rule by rule as APKeep inserts, and dumped in
 * the same format: per element and port the destination set as maximal
 * prefixes, then the destination atoms after the build's re-atomization.
 */
public final class IrDump {
	public static void main(String[] args) throws Exception {
		String dir = args[0];
		ArrayList<String> topo = new ArrayList<>(Files.readAllLines(Paths.get(dir, "topology.txt")));
		List<String> devices = Files.readAllLines(Paths.get(dir, "devices.txt"));
		List<String> rules = Files.readAllLines(Paths.get(dir, "rules.txt"));
		long t0 = System.nanoTime();
		Network net = new Network("fave", "ndd");
		net.initializeNetwork(topo, devices, null, null, null, null);
		java.io.File log = java.io.File.createTempFile("irdump", ".out");
		log.deleteOnExit();
		net.run(new Evaluator("fave", log.getAbsolutePath()), rules);
		long t1 = System.nanoTime();
		int[] bit = NDD.getBDDVars(FaveFields.DST4);   // vars[b] is bit b (BDDACLWrapper)
		NddPorts ports = net.nddPorts();
		List<String> bad = ports.checkInvariants();
		try (PrintWriter out = new PrintWriter(args[1])) {
			for (String e : new TreeSet<>(java.util.Arrays.asList(net.elementNames()))) {
				for (String port : new TreeSet<>(net.getElement(e).getPorts())) {
					int pred = ports.predicate(e, port);
					out.println(e + " " + port + " " + bad.isEmpty() + " "
							+ PrefixDump.prefixes(NDD.getBDDEngine(), pred, FaveFields.DST4, bit));
				}
			}
			out.println("#atoms " + AtomizedNDD.getAllAtoms(FaveFields.DST4).size());
			out.println("#build_s " + (t1 - t0) / 1e9);
		}
		net.close();
	}
}
