package apkeep.ndd;

import java.util.HashMap;
import java.util.Map;

import org.ants.jndd.diagram.NDD;
import org.ants.jndd.fave.FaveFields;

import apkeep.core.RuleEncoder;
import common.ACLRule;
import common.BDDACLWrapper;
import jdd.bdd.BDD;

/**
 * {@link RuleEncoder} on NDD (APKEEP_INCREMENTAL_SCOPE.md §4).
 *
 * <p>The field labels come from the fork's own encoders ({@link BDDACLWrapper}),
 * run over the NDD library's per-field variables, so a rule string reads the
 * same on both backends -- one parser ({@link ACLRule}), one encoding per
 * field. Only the assembly differs: BDD-APKeep conjoins the fields into one
 * BDD, NDD-APKeep makes them the levels of one NDD. The layout is
 * {@link FaveFields}', shared with NDD-Flood in the same JVM.
 *
 * <p>Destination prefixes are cached as {@code APKeeper.encodePrefixBDD} does:
 * the cache keeps a reference and each caller gets its own.
 */
public final class NddEncoder implements RuleEncoder {

	private final BDDACLWrapper fields;
	private final Map<String, Integer> prefixCache = new HashMap<>();

	public NddEncoder() {
		FaveFields.ensure();
		BDD engine = NDD.getBDDEngine();
		fields = new BDDACLWrapper(engine,
				NDD.getBDDVars(FaveFields.PROTO),
				NDD.getBDDVars(FaveFields.SPORT),
				NDD.getBDDVars(FaveFields.DPORT),
				NDD.getBDDVars(FaveFields.SRC4),
				NDD.getBDDVars(FaveFields.DST4),
				NDD.getBDDVars(FaveFields.SRC6),
				NDD.getBDDVars(FaveFields.DST6),
				NDD.getBDDVars(FaveFields.VLAN),
				NDD.getBDDVars(FaveFields.REL)[0],
				NDD.getBDDVars(FaveFields.FLAGS),
				NDD.getBDDVars(FaveFields.SVLAN),
				NDD.getBDDVars(FaveFields.DVLAN));
	}

	/** One field label (referenced in the label engine) -> a referenced NDD;
	 *  the label's reference is released. */
	private static int lift(int field, int label) {
		if (label == BDDACLWrapper.BDDFalse) return NDD.getFalse();
		if (label == BDDACLWrapper.BDDTrue) return NDD.getTrue();
		Map<Integer, Integer> edge = new HashMap<>();
		edge.put(NDD.getTrue(), label);
		int node = NDD.ref(NDD.addAtField(field, edge));
		NDD.getBDDEngine().deref(label);
		return node;
	}

	@Override
	public int dstPrefix(long ip, int len) {
		String key = ip + " " + len;
		Integer cached = prefixCache.get(key);
		if (cached == null) {
			cached = lift(FaveFields.DST4, fields.encodeDstIPPrefix(ip, len));   // the cache's reference
			prefixCache.put(key, cached);
		}
		return NDD.ref(cached);                                                    // the caller's
	}

	@Override
	public int srcPrefix(long ip, int len) {
		return lift(FaveFields.SRC4, fields.encodeSrcIPPrefix(ip, len));
	}

	@Override
	public int vlan(int id) {
		return lift(FaveFields.VLAN, fields.ConvertVLAN(id));
	}

	/** {src IPv6 in cidr}; the full space for null/empty. */
	public int srcIP6(String cidr) {
		if (cidr == null || cidr.isEmpty()) return NDD.getTrue();
		return lift(FaveFields.SRC6, fields.encodeSrcIP6Prefix(cidr));
	}

	/** {related == r}: 1 established/related, 0 new. */
	public int related(int r) {
		return lift(FaveFields.REL, fields.ConvertRelated(r));
	}

	@Override
	public int acl(ACLRule rule) {
		int[] parts = fields.ConvertACLRuleFields(rule);
		boolean src6 = rule.source != null && rule.source.contains(":");
		boolean dst6 = rule.destination != null && rule.destination.contains(":");
		// NDD levels in field order (FaveFields): SRC6, DST6, PROTO, SPORT,
		// DPORT, REL, SRC4, DST4, VLAN, FLAGS, SVLAN, DVLAN.
		int[] level = new int[FaveFields.WIDTH.length];
		java.util.Arrays.fill(level, BDDACLWrapper.BDDTrue);
		level[src6 ? FaveFields.SRC6 : FaveFields.SRC4] = parts[BDDACLWrapper.ACL_SRC];
		level[dst6 ? FaveFields.DST6 : FaveFields.DST4] = parts[BDDACLWrapper.ACL_DST];
		level[FaveFields.PROTO] = parts[BDDACLWrapper.ACL_PROTO];
		level[FaveFields.SPORT] = parts[BDDACLWrapper.ACL_SPORT];
		level[FaveFields.DPORT] = parts[BDDACLWrapper.ACL_DPORT];
		level[FaveFields.REL] = parts[BDDACLWrapper.ACL_RELATED];
		level[FaveFields.VLAN] = parts[BDDACLWrapper.ACL_VLAN];
		level[FaveFields.FLAGS] = parts[BDDACLWrapper.ACL_FLAGS];
		level[FaveFields.SVLAN] = parts[BDDACLWrapper.ACL_SVLAN];
		level[FaveFields.DVLAN] = parts[BDDACLWrapper.ACL_DVLAN];

		BDD engine = NDD.getBDDEngine();
		boolean empty = false;
		for (int label : level) if (label == BDDACLWrapper.BDDFalse) empty = true;
		int node = NDD.getTrue();
		if (!empty) {
			for (int f = level.length - 1; f >= 0; f--) {
				if (level[f] == BDDACLWrapper.BDDTrue) continue;
				Map<Integer, Integer> edge = new HashMap<>();
				edge.put(node, level[f]);
				int next = NDD.ref(NDD.addAtField(f, edge));
				NDD.deref(node);
				node = next;
			}
		} else {
			node = NDD.getFalse();
		}
		for (int label : parts) engine.deref(label);
		return node;
	}
}
