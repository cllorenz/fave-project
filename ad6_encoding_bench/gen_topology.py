"""Synthetic LPM-forwarding router-chain generator for the H1/H2 encoding
microbenchmark (see ../AD6_ENCODING_PLAN.md §3). Builds real ad6 models via
ad6's own, stable, production pipeline (IP6TablesParser -> GenUtils ->
Instantiator) so every axis measures the same real encoding path
wl_ifi/wl_up/wl_stanford already go through -- not a toy stand-in.

Deliberately self-contained: everything is one firewall with N custom
chains ("ROUTER1".."ROUTERn"), each jumping to the next, so no network/
interface wiring (GenUtils.node/network/route, fave/ad6/adapter.py,
ad6/src/parser/favemodel.py) is touched at all -- those are exactly the
files the concurrent wl_stanford session may be editing.

Node-key convention (reverse-engineered empirically against the real
parser, not assumed): IP6TablesParser keys a chain's rules
"<fw>_<chain>_r<idx>", idx = -4096, 0, 4096, 8192, ... in ruleset order --
but idx starts at 0 for the chain's FIRST *-A* rule only if a preceding
"-P <chain> <policy>" line already bumped the internal counter once. Every
chain generated here gets such a policy line for exactly this reason, so
"<fw>_router1_r0" is reliably the chain's true entry rule.
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'ad6'))

from src.xml.genutils import GenUtils
from src.parser.iptables import IP6TablesParser
from src.core.instantiator import Instantiator

FW_NAME = 'bench'
DEST_PREFIX = '2001:db8:beef::/64'          # the query's real destination
FORWARD_PREFIX = '2001:db8::/32'             # "keep forwarding" catch-all
ENTRY_KEY = '%s_router1_r0' % FW_NAME
ACCEPT_KEY = '%s_accept_r0' % FW_NAME
DROP_KEY = '%s_drop_r0' % FW_NAME


def _distractor_prefix(router_idx, distractor_idx):
    """A deterministic, distinct CIDR that never overlaps DEST_PREFIX --
    stresses rule/bit-vector count (Factor B) without changing the
    query's real answer. Widens with distractor_idx so each router's
    distractor set spans a realistic mix of prefix lengths, mirroring a
    real FIB's mix of specific and broad routes."""
    prefix_len = 40 + (distractor_idx % 24)  # 40..63, never /64 (=DEST)
    return '2001:db8:%x:%x::/%d' % (
        0xd000 + router_idx, distractor_idx, prefix_len)


def generate_ruleset(n_routers, distractors_per_router=0, cyclic=False):
    """Returns (ruleset_text, entry_key, accept_key). Chain i (1-indexed)
    forwards everything under FORWARD_PREFIX to chain i+1; the last chain
    additionally has the one specific rule matching DEST_PREFIX -> ACCEPT.
    If cyclic, the last chain's forward rule targets ROUTER1 instead of
    terminating, so the "keep forwarding" traffic class loops forever
    (aside from the DEST_PREFIX traffic, which still exits at ACCEPT)."""
    assert n_routers >= 1
    lines = []

    for i in range(1, n_routers + 1):
        chain = 'ROUTER%d' % i
        lines.append('ip6tables -P %s DROP' % chain)

        for d in range(distractors_per_router):
            lines.append('ip6tables -A %s -d %s -j DROP' %
                          (chain, _distractor_prefix(i, d)))

        if i == n_routers:
            lines.append('ip6tables -A %s -d %s -j ACCEPT' %
                          (chain, DEST_PREFIX))

        target = 'ROUTER%d' % (1 if (cyclic and i == n_routers) else i + 1)
        if i < n_routers or cyclic:
            lines.append('ip6tables -A %s -d %s -j %s' %
                          (chain, FORWARD_PREFIX, target))

    return '\n'.join(lines) + '\n', ENTRY_KEY, ACCEPT_KEY


def build_model(n_routers, distractors_per_router=0, cyclic=False):
    """Parses+instantiates via ad6's real, unmodified pipeline. Returns
    (kripke, encoding, entry_key, accept_key)."""
    ruleset, entry_key, accept_key = generate_ruleset(
        n_routers, distractors_per_router, cyclic)
    fw = IP6TablesParser.parse(ruleset, FW_NAME)

    config = GenUtils.config()
    firewalls = GenUtils.firewalls()
    firewalls.append(fw)
    config.append(firewalls)

    kripke, encoding = Instantiator.InstantiateBase(
        config, Inits=[entry_key], default_inits=False)
    return kripke, encoding, entry_key, accept_key


if __name__ == '__main__':
    # smoke test
    from src.solver.pycosat import PycoSATAdapter
    kripke, encoding, entry_key, accept_key = build_model(
        n_routers=4, distractors_per_router=3, cyclic=False)
    solver = PycoSATAdapter()
    instance = Instantiator.InstantiateReach(kripke, encoding, accept_key)
    result = solver.Solve(instance)
    print('nodes:', len(list(kripke.IterNodes())))
    print('accept reachable (expect True):', bool(result))

    kripke_c, encoding_c, entry_key_c, accept_key_c = build_model(
        n_routers=4, distractors_per_router=3, cyclic=True)
    instance_c = Instantiator.InstantiateReach(kripke_c, encoding_c, accept_key_c)
    result_c = solver.Solve(instance_c)
    print('cyclic variant accept reachable (expect True):', bool(result_c))
