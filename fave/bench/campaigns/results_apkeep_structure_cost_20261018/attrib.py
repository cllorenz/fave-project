"""Attribution of BDD-APKeep's wl_up structure cost (ATTRIBUTION_PROTOCOL.txt):
probe.py with two more variants, each ONE of the update-ready structure's
behaviours on top of the from-zero structure. Monkeypatches only.
  split    the per-ingress-port split (`_for_updates` in the split pass, with
           its IPv6 rule for split elements), pass-through elision kept
  noelide  no pass-through elision, the from-zero ingress classes kept
plain / updatable as in probe.py. Run from fave/: python3 <this> <variant>."""
import runpy, sys
variant = sys.argv[1]
import apkeep.adapter as ad
orig_build = ad.APKeepAdapter._build
orig_elide = ad.APKeepAdapter._elide_passthrough_filters

def elide_as_from_zero(self, *a, **k):
    saved, self._for_updates = self._for_updates, False
    try:
        return orig_elide(self, *a, **k)
    finally:
        self._for_updates = saved

if variant == 'split':
    def build(self):
        self._for_updates = True            # frozen IPv6: a no-op at build
        return orig_build(self)
    ad.APKeepAdapter._build = build
    ad.APKeepAdapter._elide_passthrough_filters = elide_as_from_zero
elif variant == 'noelide':
    ad.APKeepAdapter._elide_passthrough_filters = lambda self, edges, elems, rules: (edges, elems, rules)
probe_variant = {'split': 'plain', 'noelide': 'plain'}.get(variant, variant)
sys.argv = [sys.argv[0], 'bench/wl_up', 'bench/wl_up/checks.json', 'bdd', probe_variant]
import io, contextlib, json
buf = io.StringIO()
with contextlib.redirect_stdout(buf):
    runpy.run_path(__file__.replace('attrib.py', 'probe.py'), run_name='__main__')
for line in buf.getvalue().splitlines():
    if line.startswith('{'):
        r = json.loads(line); r['variant'] = variant; print(json.dumps(r), flush=True)
