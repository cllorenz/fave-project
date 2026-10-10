package apkeep.core;

import common.ACLRule;

/** {@link RuleEncoder} on BDDs: exactly the calls upstream's elements made --
 *  the destination prefixes through the APKeeper's shared prefix cache. */
public final class BddEncoder implements RuleEncoder {
	private final APKeeper apk;

	public BddEncoder(APKeeper apk) {
		this.apk = apk;
	}

	@Override public int dstPrefix(long ip, int len) { return apk.encodePrefixBDD(ip, len); }
	@Override public int srcPrefix(long ip, int len) { return APKeeper.bddengine.encodeSrcIPPrefix(ip, len); }
	@Override public int acl(ACLRule rule) { return apk.encodeACLBDD(rule); }
	@Override public int vlan(int id) { return APKeeper.bddengine.ConvertVLAN(id); }
}
