package apkeep.core;

import common.ACLRule;

/**
 * Encodes the header spaces of APKeep's rule strings in one representation
 * (FaVe fork, APKEEP_INCREMENTAL_SCOPE.md §4): {@link BddEncoder} for
 * BDD-APKeep, {@code apkeep.ndd.NddEncoder} for NDD-APKeep. Every result is a
 * handle the caller owns one reference to.
 */
public interface RuleEncoder {
	/** {dst IPv4 in ip/len}. */
	int dstPrefix(long ip, int len);
	/** {src IPv4 in ip/len}. */
	int srcPrefix(long ip, int len);
	/** The match of an ACL/filter rule body (5-tuple, VLAN, state, flags). */
	int acl(ACLRule rule);
	/** {vlan == id}. */
	int vlan(int id);
}
