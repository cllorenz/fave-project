package apkeep.rules;

import apkeep.core.APKeeper;
import common.Fields;

public class RewriteRule extends Rule{
	
	/* FaVe fork (APKEEP_INCREMENTAL_SCOPE.md §4): the rewritten FIELD is kept
	 * by name and resolved on use. Upstream resolved it to its BDD
	 * quantification cube in the constructor, through the static engine --
	 * which an NDD network does not have, and which quantifies a field there
	 * by its index instead (apkeep.ndd). Resolving it on use gives the BDD path
	 * the same cube from the same engine (Network.activate()). */
	private final Fields field;
	private int new_pkt_bdd;
	
	public RewriteRule(int old_bdd, int new_bdd, String rname, int p)
	{
		super(old_bdd, p, rname);
		new_pkt_bdd = new_bdd;
		field = Fields.dst_ip;
	}
	
	public RewriteRule(int old_bdd, int hit_bdd, int new_bdd, String rname, int p)
	{
		super(old_bdd, hit_bdd, p, rname);
		new_pkt_bdd = new_bdd;
		field = Fields.dst_ip;
	}

	// P7b: rewrite a field OTHER than dst-IP (e.g. VLAN). The match (old_bdd/
	// hit_bdd) may be on a different field than the one rewritten -- e.g. the
	// Stanford mid-stage matches the dst-IP route but rewrites the egress VLAN.
	public RewriteRule(int old_bdd, int hit_bdd, int new_bdd, Fields field, String rname, int p)
	{
		super(old_bdd, hit_bdd, p, rname);
		new_pkt_bdd = new_bdd;
		this.field = field;
	}

	public Fields getField() {
		return field;
	}

	public int getField_bdd() {
		return APKeeper.bddengine.get_field_bdd(field);
	}

	public int getNew_pkt_bdd() {
		return new_pkt_bdd;
	}

	public String toString()
	{
		return "";
	}
}
