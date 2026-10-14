"""Predeclared independent A2/B2-T comparison fixtures. No research profile changes."""
from tests.step4_support import block, build_doc, container, crane, physics, vessel


def fixtures():
    for moves in (2, 4):
        for kind in ('single', 'competing', 'announced', 'horizon_edge', 'release_arrival', 'occupied'):
            arrival = {'announced': 10, 'horizon_edge': 240, 'release_arrival': 50 + moves / 2}.get(kind, 0)
            length = 700 if kind in ('competing', 'release_arrival') else 300
            vs = [vessel('V001', 0, length)]
            if kind != 'single':
                vs.append(vessel('V002', arrival, length))
            cs = [container(i * moves + n + 1, 'export', dest=v['vessel_id'], block='B01')
                  for i, v in enumerate(vs) for n in range(moves)]
            doc = build_doc(vessels=vs, containers=cs, cranes=[crane('QC01', 120), crane('QC02', 120)])
            yield f'{kind}_m{moves}', doc, kind == 'occupied', []
    for kind in ('rate_mismatch', 'distance_dependency', 'censoring', 'export_unavailable', 'transshipment_unavailable'):
        vs = [vessel('V001', 0, 300), vessel('V002', 10, 300)]
        cs = [container(1, 'export', dest='V001', block='B01'),
              container(2, 'export', dest='V002', block='B01')]
        overrides = {'transport.enabled': False, 'yard.constraints_enabled': False}
        if kind == 'distance_dependency':
            overrides['transport.enabled'] = True
        if kind == 'censoring':
            overrides['episode.max_drain_extension_min'] = 20
        if kind == 'export_unavailable':
            cs[0] = container(1, 'export', dest='V001', gate_in=1000)
        if kind == 'transshipment_unavailable':
            cs[0] = container(1, 'transshipment', origin='V002', dest='V001')
            vs[1] = vessel('V002', 1000, 300)
        doc = build_doc(vessels=vs, containers=cs, blocks=[block('B01', 100, y=900)],
                        cranes=[crane('QC01', 30 if kind == 'rate_mismatch' else 120), crane('QC02', 120)],
                        physics_doc=physics(**overrides))
        yield kind, doc, False, [kind]
