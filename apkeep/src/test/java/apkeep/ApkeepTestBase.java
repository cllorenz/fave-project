package apkeep;

import java.io.File;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;

import org.junit.jupiter.api.BeforeAll;

import apkeep.core.Network;
import apkeep.utils.Evaluator;
import apkeep.utils.Parameters;
import common.BDDACLWrapper;

/**
 * Shared setup for APKeep core unit tests (FaVe fork; APKeep shipped no tests).
 *
 * Tests build tiny in-memory networks via the public API (Network.initializeNetwork
 * + run with rule strings) and assert on element-level behaviour (forwardAPs /
 * port APs) or reachability -- exercising the real forwarding/ACL/AP/BDD path in
 * Java, with no JPype and no FaVe. See TESTING_STRATEGY_JAVA.md.
 */
public abstract class ApkeepTestBase {

    @BeforeAll
    static void shrinkBddTable() {
        // The default BDD table is 100M nodes; tests build many tiny networks in
        // one JVM, so shrink it so the instances coexist cheaply.
        Parameters.BDD_TABLE_SIZE = 100_000;
    }

    /**
     * Build an in-memory APKeep network and apply the given rule strings.
     *
     * @param links directed L1 edges "dev1 port1 dev2 port2" (may be empty)
     * @param devices ForwardElement device names not implied by a link
     * @param deviceAcls device -> ACL names (creates ACLElements "device_acl"); may be null
     * @param rules "+ fwd ..." / "+ acl ..." update strings, applied in order
     */
    protected Network buildNetwork(String name, List<String> links, List<String> devices,
                                   Map<String, Set<String>> deviceAcls, List<String> rules)
            throws Exception {
        return buildNetwork(name, links, devices, deviceAcls, null, rules);
    }

    /** As above, plus a device -> {vlan -> physical ports} flood map (addVLANs). */
    protected Network buildNetwork(String name, List<String> links, List<String> devices,
                                   Map<String, Set<String>> deviceAcls,
                                   Map<String, Map<String, Set<String>>> vlanPorts,
                                   List<String> rules) throws Exception {
        Network net = new Network(name);
        net.initializeNetwork(new ArrayList<>(links), devices, deviceAcls, vlanPorts, null);
        Evaluator eva = new Evaluator(name, File.createTempFile("apkeep-" + name, ".out").getAbsolutePath());
        net.run(eva, rules);
        return net;
    }

    /** The full-space seed: forwardAPs(port, {BDDTrue}) returns all of a port's APs. */
    protected static HashSet<Integer> seedTrue() {
        HashSet<Integer> s = new HashSet<>();
        s.add(BDDACLWrapper.BDDTrue);
        return s;
    }

    /** A single-packet BDD for an IPv4 destination, as a one-element AP set. */
    protected static HashSet<Integer> dstPacket(Network net, long dstIp) {
        HashSet<Integer> s = new HashSet<>();
        s.add(net.bdd_engine.encodeDstIPPrefix(dstIp, 32));
        return s;
    }
}
