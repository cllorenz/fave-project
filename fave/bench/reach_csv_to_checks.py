#!/usr/bin/env python3

# -*- coding: utf-8 -*-

# Copyright 2021 Claas Lorenz <claas_lorenz@genua.de>

# This file is part of FaVe.

# FaVe is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

# FaVe is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

# You should have received a copy of the GNU General Public License
# along with FaVe.  If not, see <https://www.gnu.org/licenses/>.


import sys
import csv
import json
import argparse
import itertools


# The one role whose self-reachability is not a question anyone can answer: the
# Internet is external by definition, outside the administrative reach of any
# organisation writing an FPL policy, so whether it reaches itself is not
# verifiable and not meaningful. Every OTHER role's self-rule is an ordinary
# compliance question -- see _abstracts_a_subnet.
_INTERNET = 'Internet'


def _load_role_attributes(path):
    """ {role name: attributes} from a `policy_translator --roles` dump, which
    the translator derives from the FPL inventory (roles_and_services.txt). No
    file => {}, and every self-rule is treated as degenerate, exactly as before
    this argument existed. """
    if not path:
        return {}
    with open(path, 'r') as raw:
        return {role['name']: role.get('attributes', {}) for role in json.load(raw)}


def _load_role_services(path):
    """ {role name: [service attribute dict, ...]} from the same dump.

    The translator records what each role OFFERS alongside what it is, so a
    consumer can ask "which services does reaching this role mean?" without
    re-reading the FPL. Only `--deny-per-service` uses it. """
    if not path:
        return {}
    with open(path, 'r') as raw:
        return {
            role['name']: [
                service.get('attributes', {})
                for service in role.get('services', [])
            ] for role in json.load(raw)
        }


def _service_terms(attributes):
    """ One service's attributes as check terms, in declaration order. """
    return ['f=%s:%s' % (field, value) for field, value in attributes.items()]


def _deny_checks(fstr, sources, target, services):
    """ The must-not-reach checks for one denied cell.

    WITHOUT `--deny-per-service` a denied cell denies ALL traffic to the target,
    which is the right reading where a role is a subnet: wl_up's `Wifi` is a set
    of machines, and "must not reach Wifi" means no packet of any kind.

    WITH it, a denied cell denies exactly the target's OFFERED SERVICES. That is
    the right reading where a role is a SERVICE, because then two roles can name
    the same machines -- `wl_cloud`'s services 2 and 3 are both 10.0.17.0/25,
    distinguished in the data plane only by TCP port. Under the blanket reading
    such a matrix is self-contradictory rather than merely strict: any row
    permitting service 2 and denying service 3 asks for a packet to arrive at
    those hosts and not arrive at them. Probe-side filtering would be the other
    way to resolve it, but `netplumber/adapter.py` has `filter_fields` commented
    out (memory explosion), so the qualification has to live in the check.

    A role offering no service falls back to the blanket form: there is then no
    service to name, and silently emitting nothing would delete the check. """
    qualifiers = [terms for terms in map(_service_terms, services) if terms]

    if not qualifiers:
        return ['! ' + fstr % (s, target) for s in sources]

    return [
        '! ' + fstr % (s, target) + ' && ' + ' && '.join(terms)
        for s in sources for terms in qualifiers
    ]


def _abstracts_a_subnet(attributes):
    """ True iff the role's declared address is a PROPER subnet: more than one
    address, but not the whole space.

    This decides whether a role's self-rule (`R <--> R`) states something real.
    A role is one node in the model; what that node STANDS FOR is the question:

      * a bare address, /32 or /128 -- one device. `R <--> R` is then a host
        talking to itself, which is not a network question.
      * a match-all prefix (`0.0.0.0/0`, `::/0`) -- a PLACEHOLDER that carries no
        cardinality at all. wl_i2 and wl_stanford give every router role
        `ipv4 = '0.0.0.0/0'` because those models have no per-role addressing, so
        it is not evidence of many devices either.
      * anything in between -- a subnet, whose single node stands for all the
        devices in it. wl_up's `Wifi` is this case (`ipv6 = 2001:db8:abc:2::0/64`,
        and deliberately no `hosts` list): `Wifi <--> Wifi` says wifi clients may
        talk to each other, which is how wifi networks work -- L2 is generally
        unrestricted, you either have access or you do not -- and is a compliance
        question like any other.
    """
    for field, width in (('ipv4', 32), ('ipv6', 128)):
        value = attributes.get(field)
        if not value:
            continue
        _address, _, length = str(value).partition('/')
        if not length:
            continue                      # a bare address is a single device
        if 0 < int(length) < width:
            return True
    return False


def _peers(sources, target, keep_self):
    """ The sources a check is emitted for against one target.

    A host is not its own peer, so the self-pair is normally dropped: for a role
    listing several hosts this leaves exactly the cross-pairs, which is what the
    self-rule means. But where the role's ONE node stands for a whole subnet,
    that self-pair is the only representation of the intra-subnet traffic the
    rule is about, and dropping it discards the rule entirely. """
    return [s for s in sources if s != target or keep_self]


def _generate_cchecks(checks):
    cchecks = {}

    for check in checks:
        valid = not check.startswith("! ")
        check = check.lstrip('! ')

        cond = []

        tokens = check.split(" && ")
        if len(tokens) == 2:
            src, dst = tokens
        elif len(tokens) == 3:
            src, dst, cond = tokens
            cond = [cond.lstrip("f=")]
        elif len(tokens) > 3:
            src = tokens[0]
            dst = tokens[1]
            cond = [c.lstrip("f=") for c in tokens[2:]]
        else:
            raise Exception("unsupported amount of operands: %s (%s)" % (len(tokens), tokens))

        src = src.lstrip("s").lstrip('=')
        dst = dst.lstrip("EF p").lstrip('=')

        cchecks.setdefault(src, [])
        cchecks[src].append((dst, valid, cond))

    return cchecks


def complement_terms(flag):
    """ The complement of a conditionally permitted cell, in disjunctive form.

    A cell such as `(protocol:tcp;port:80|protocol:tcp;port:22)` states the
    ONLY traffic the policy permits between that pair. Verifying it needs the
    other half of the claim -- that nothing else gets through -- and the engine
    can only express that as "no flow outside the permitted set arrives", since
    its one condition primitive is existential overlap with no universal
    counterpart.

    The complement of a union is the intersection of complements, and
    `not (a and b)` is `not a or not b`, so complementing the cell gives one
    term per way of contradicting every alternative at once: pick one field
    from each alternative and negate it. Multiple check entries OR together, so
    each term becomes its own must-not-reach check and the union of them is the
    complement.

    Terms that are supersets of another are dropped: more negations describe a
    SMALLER set, so such a term is already covered. For the cell above that
    leaves `not tcp` and `not 80 and not 22` -- two checks rather than four.
    """
    alternatives = [
        tuple(sorted(set(alternative.split(';'))))
        for alternative in flag.lstrip('(').rstrip(')').split('|')
    ]

    terms = set(
        tuple(sorted(set(combination)))
        for combination in itertools.product(*alternatives)
    )

    return sorted(
        term for term in terms
        if not any(set(other) < set(term) for other in terms)
    )


if __name__ == '__main__':
    checks = []

    parser = argparse.ArgumentParser()

    parser.add_argument(
        '-c', '--checks',
        dest='checks_file',
        default='checks.json'
    )
    parser.add_argument(
        '--cchecks',
        dest='cchecks_file',
        default='cchecks.json'
    )
    parser.add_argument(
        '-j', '--reach-json',
        dest='reach_file',
        default='reachable.json'
    )
    parser.add_argument(
        '-m', '--inventory-mapping',
        dest='inventory_file',
        default='inventory.json'
    )
    parser.add_argument(
        '-p', '--policy-csv',
        dest='policy_file',
        default='policy.csv'
    )
    parser.add_argument(
        '-s', '--suffix',
        dest='suffix',
        default=''
    )
    # OFF by default. Emitting it changes the check set of every workload with
    # a conditionally permitted cell, and therefore what those workloads are
    # expected to report -- a decision per workload, not a silent upgrade. See
    # CLOUD_BENCH_PLAN.md 1.9.3.
    parser.add_argument(
        '--complement',
        dest='complement',
        action='store_true',
        default=False,
        help='also check that a conditionally permitted pair is UNreachable '
             'outside its permitted services'
    )
    # OFF by default, for the same reason `--complement` is: it changes what a
    # denied cell asserts, and that is a decision per workload. See
    # `_deny_checks` for when the two readings differ, and
    # CLOUD_BENCH_PLAN.md §1.9.6.
    parser.add_argument(
        '--deny-per-service',
        dest='deny_per_service',
        action='store_true',
        default=False,
        help='a denied cell denies the target role\'s OFFERED SERVICES rather '
             'than all traffic to it. For matrices whose roles are services '
             'and may therefore share machines. Needs --roles.'
    )
    parser.add_argument(
        '--roles',
        dest='roles_file',
        default=None,
        help='Atomic-role dump from `policy_translator --roles`. Lets a role '
             'whose single node stands for a whole subnet carry a self-check; '
             'without it every self-rule is treated as degenerate.'
    )
    parser.add_argument(
        '--strict',
        dest='strict',
        action='store_true',
        help='The matrix came from `policy_translator --strict`, so a filled '
             'diagonal means an FPL rule asked for it. WITHOUT this, the '
             'translator injects an implicit self-policy for EVERY atomic role '
             '(policy_builder.build_policies), so a diagonal carries no '
             'information and no positive self-check is emitted.'
    )

    args = parser.parse_args(sys.argv[1:])

    mapping = json.load(open(args.inventory_file, 'r'))
    role_attributes = _load_role_attributes(args.roles_file)
    role_services = _load_role_services(args.roles_file)

    if args.deny_per_service and not args.roles_file:
        parser.error(
            '--deny-per-service needs --roles: the offered services it names '
            'come from the translator\'s role dump. Without it every denied '
            'cell would silently fall back to the blanket form, which is the '
            'behaviour the flag exists to change.'
        )

    checks = []
    reach_json = {}
    with open(args.policy_file, 'r') as csv_file:
        reader = csv.reader(csv_file, delimiter=',')

        header = next(reader)[1:]

        for row in reader:

            row_iter = iter(row)

            source_role = source = next(row_iter)
            sources = [s+args.suffix if s != 'Internet' else s for s in mapping[source]] if mapping else [source+args.suffix if source != 'Internet' else source]

            if source != 'Internet':
                source += args.suffix

            for idx, flag in enumerate(row_iter):
                target_role = target = header[idx]
                targets = [t+args.suffix if t != 'Internet' else t for t in mapping[target]] if mapping else [target+args.suffix if target != 'Internet' else target]

                # The Internet's self-reachability is omitted: it is an external
                # entity, out of administrative reach of whoever writes the
                # policy, so the question is not answerable (and FPL carries
                # `Internet` as a builtin role, so it appears in most policies).
                if source == _INTERNET and source == target: continue

                if target != 'Internet': target += args.suffix

                # Does this cell's self-pair carry a check? Only when the
                # matrix came from strict mode -- loose mode gives EVERY atomic
                # role a diagonal whether or not the policy asked for one, so a
                # filled diagonal there is not evidence of anything -- and then
                # only on a role's own diagonal, and only where that role's
                # single node stands for a subnet rather than one device (see
                # _abstracts_a_subnet).
                keep_self = (
                    args.strict
                    and source_role == target_role
                    and source_role != _INTERNET
                    and len(sources) == 1 and len(targets) == 1
                    and _abstracts_a_subnet(role_attributes.get(source_role, {}))
                )

                for target in targets:
                    reach_json.setdefault(target, [])

                fstr = 's=source.%s && EF p=probe.%s'
                if flag == 'X':
                    for target in targets:
                        reach_json[target].extend(_peers(sources, target, keep_self))
                        checks.extend([fstr % (s, target) for s in _peers(sources, target, keep_self)])

                elif flag == '(X)':
                    for target in targets:
                        reach_json[target].extend(_peers(sources, target, keep_self))
                        checks.extend([fstr % (s, target) + ' && f=related:1'
                                       for s in _peers(sources, target, keep_self)])
                        checks.extend(['! ' + fstr % (s, target) + ' && f=related:0'
                                       for s in _peers(sources, target, keep_self)])

                elif flag.startswith('(') and flag.endswith(')'):
                    # `X` may appear among the alternatives, meaning the pair
                    # also carries the stateful condition -- `(X|<service>...)`.
                    # The matrix used to print such a cell as a bare `(X)`,
                    # which the branch above reads as "related traffic and
                    # NOTHING else" and turns into a must-NOT-reach check for
                    # everything unrelated: the exact opposite of what the cell
                    # permits. A cell that is ONLY `X` still takes that branch,
                    # unchanged.
                    alternatives = flag[1:-1].split('|')
                    stateful = 'X' in alternatives
                    conditions = [a for a in alternatives if a != 'X']

                    for target in targets:
                        reach_json[target].extend(_peers(sources, target, keep_self))

                        if stateful:
                            checks.extend([fstr % (s, target) + ' && f=related:1'
                                           for s in _peers(sources, target, keep_self)])

                        for condition in conditions:
                            checks.extend([
                                fstr % (s, target) + ' && f=related:0 && ' + ' && '.join(['f='+f for f in
                                    condition.split(';')
                                ]) for s in _peers(sources, target, keep_self)
                            ])

                        # The other half of what the cell claims: these
                        # services and NOTHING ELSE. Without it a conditional
                        # permission is only ever checked in the direction that
                        # confirms it, so "reachable on 331" passes whether or
                        # not 332 also gets through.
                        #
                        # Complemented over the SERVICE alternatives only. Each
                        # term is asserted under `related:0`, where the
                        # stateful alternative permits nothing, so including
                        # `X` would negate a token that is not a field and
                        # would wrongly forbid the services beside it.
                        if args.complement:
                            for term in complement_terms('(%s)' % '|'.join(conditions)):
                                checks.extend([
                                    '! ' + fstr % (s, target)
                                    + ' && f=related:0 && '
                                    + ' && '.join('f=!%s' % f for f in term)
                                    for s in _peers(sources, target, keep_self)
                                ])

                else:
                    # ITERATE `targets`, like every branch above. Using the
                    # bare `target` here checked only ONE endpoint of a
                    # multi-device role -- whichever the `for target in
                    # targets` loop above happened to leave bound, i.e. the
                    # last -- so a denied cell was asserted against one leaf
                    # and silently unasserted against the other eight. Every
                    # workload before wl_cloud maps each role to exactly one
                    # device, which is why the two spellings agreed until a
                    # role spread over nine leaf routers arrived.
                    for target in targets:
                        checks.extend(_deny_checks(
                            fstr, sources, target,
                            role_services.get(target_role, [])
                            if args.deny_per_service else []
                        ))


    with open(args.checks_file, 'w') as checks_file:
        checks_file.write(json.dumps(checks, indent=2) + '\n')

    with open(args.reach_file, 'w') as rf:
        rf.write(json.dumps(reach_json, indent=2) + '\n')

    cchecks = _generate_cchecks(checks)

    with open(args.cchecks_file, "w") as cchecks_file:
        cchecks_file.write(json.dumps(cchecks, indent=2) + '\n')
