"""BDD-APKeep's wl_cloud cells beyond A S2, trialled before D16 includes them
(owner, 2026-10-17: "try BDD cloud before inclusion"). The first 50 updates
of each D16 cell kind the calibration did not run for the pair; the D16
limits. Run from fave/: python3 <this>. Writes queue.json."""
import json, os
HERE = os.path.dirname(os.path.abspath(__file__))
base = {'workload': 'bench/wl_cloud', 'engine': 'apkeep', 'mem_mb': 18432,
        'limit-wall': 12 * 3600, 'limit-updates': 50, 'est_h': 0.6}
cells = [
    dict(base, name='A_wl_cloud_apkeep_s1', stream='s1'),
    dict(base, name='A_wl_cloud_apkeep_s3', stream='s3'),
    dict(base, name='B_wl_cloud_apkeep_s2_b10', stream='s2', batch=10),
    dict(base, name='C_wl_cloud_apkeep_s4', stream='s4'),
    dict(base, name='D_wl_cloud_apkeep_s1_coarse', stream='s1', footprint='coarse'),
    dict(base, name='D_wl_cloud_apkeep_s2_coarse', stream='s2', footprint='coarse'),
    dict(base, name='D_wl_cloud_apkeep_s3_coarse', stream='s3', footprint='coarse'),
    dict(base, name='E_wl_cloud_apkeep_s2_oracle', stream='s2',
         **{'oracle-sample': 50, 'oracle-every': 1000}),
]
with open(os.path.join(HERE, 'queue.json'), 'w') as out:
    json.dump(cells, out, indent=1)
print(len(cells), 'cells')
