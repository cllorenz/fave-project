package apkeep.elements;

import java.util.ArrayList;
import java.util.HashSet;
import java.util.LinkedList;
import java.util.List;

import apkeep.core.ChangeItem;
import apkeep.rules.FilterRule;
import apkeep.rules.Rule;
import apkeep.utils.Logger;
import common.ACLRule;
import common.BDDACLWrapper;

/**
 * Multi-field, first-match FORWARDING element -- a packet filter's forward_filter
 * (FaVe fork addition; APKEEP_TUM_UP_PLAN.md Phase 2).
 *
 * No stock APKeep element both matches a multi-field header AND forwards to a
 * chosen port: {@link ForwardElement} matches only a dst-IP prefix, and
 * {@link ACLElement} matches the full 5-tuple (+VLAN) but only gates into
 * permit/deny. A packet filter needs both: each rule matches on the 5-tuple
 * (+VLAN) and either forwards accepted traffic out a named out_port or drops it.
 *
 * This is {@link ACLElement}'s first-match machinery (an ordered rule list whose
 * overlapping hit-predicates are resolved higher-priority-wins by the shared
 * {@code identifyChangesInsert}) with two differences: the rule's action token
 * (the ACL "permitDeny" slot) carries a real out_port name rather than
 * permit/deny, and unmatched traffic falls to a drop sink ("__drop__", a
 * traversal dead-end like ACL "deny") instead of "deny". Because the per-port
 * hit-predicates land in {@code port_aps_raw} exactly as ForwardElement's do,
 * {@code forwardAPs} routes each rule's packets out its own out_port. It extends
 * {@link Element} directly (not ACLElement) so it lives in the forwarding AP
 * universe (fwd_apk), not the ACL "division" universe.
 *
 * Rule string: {@code + filter <device> <accessList> <accessListNumber>
 * <out_port> <protoLo> <protoHi> <src> <srcWild> <sportLo> <sportHi> <dst>
 * <dstWild> <dportLo> <dportHi> <priority> [vlan]} -- identical to an ACL rule
 * except the permitDeny slot holds the out_port (or "__drop__").
 */
public class FilterElement extends Element {

    /** Sink port for dropped (unmatched or explicitly denied) traffic. */
    public static final String DROP_PORT = "__drop__";

    private LinkedList<Rule> filter_rule;

    public FilterElement(String ename) {
        super(ename);
        filter_rule = new LinkedList<>();
    }

    @Override
    public void initialize() {
        // Default: everything unmatched drops. Priority -1 so any real rule wins.
        FilterRule rule = new FilterRule(BDDACLWrapper.BDDTrue, BDDACLWrapper.BDDTrue, DROP_PORT, -1);
        filter_rule.add(rule);

        HashSet<Integer> alltrue = new HashSet<Integer>();
        alltrue.add(BDDACLWrapper.BDDTrue);
        port_aps_raw.put(DROP_PORT, alltrue);
    }

    @Override
    public Rule encodeOneRule(String rule) {
        String[] tokens = rule.split(" ");
        // strip "<op> <type> <device> " -> the ACLRule substring; the permitDeny
        // slot of that ACLRule carries the out_port (ACCEPT) or __drop__ (DROP).
        ACLRule r = new ACLRule(rule.substring(tokens[0].length() + tokens[1].length() + tokens[2].length() + 3));
        int match_bdd = apk.encodeACLBDD(r);
        return new FilterRule(match_bdd, r);
    }

    @Override
    public List<ChangeItem> insertOneRule(Rule rule) throws Exception {
        List<ChangeItem> change_set = identifyChangesInsert(rule, filter_rule);
        port_aps_raw.putIfAbsent(rule.getPort(), new HashSet<Integer>());
        return change_set;
    }

    @Override
    public List<ChangeItem> removeOneRule(Rule rule) throws Exception {
        int index = findRule(rule);
        if (index == filter_rule.size()) {
            Logger.logInfo("Rule not found " + rule.toString());
            return new ArrayList<ChangeItem>();
        }
        Rule rule_to_remove = filter_rule.get(index);
        if (rule_to_remove.getHit_bdd() == BDDACLWrapper.BDDFalse) {
            removeRule(index);
            Logger.logInfo("hidden rule deleted");
            return new ArrayList<ChangeItem>();
        }

        List<ChangeItem> change_set = identifyChangesRemove(rule_to_remove, filter_rule);
        removeRule(index);
        return change_set;
    }

    private int findRule(Rule rule) {
        int index = 0;
        for (Rule r : filter_rule) {
            if (r.equals(rule)) return index;
            index++;
        }
        return index;
    }

    private void removeRule(int index) {
        bdd.deref(filter_rule.get(index).getMatch_bdd());
        filter_rule.remove(index);
    }

    @Override
    protected int tryMergeIfNATElement(int delta) {
        return delta;
    }
}
