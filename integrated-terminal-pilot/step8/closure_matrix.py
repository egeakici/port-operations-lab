"""Contract-to-executable §11 registry. Planning never generates scenarios."""
import copy
from diagnostic_plan import make_plan
from evidence import s, EXPECTED_LOCK
from statistical import ContractError

YARD = 'yard_occupancy_balance_v1'
VERSION = 'step8_diagnostics_v1'


def matrix():
    old = make_plan()
    rows = []
    for c in old['sensitivity_cells']:
        condition = c['condition']
        unsupported = c['status'].startswith('UNSUPPORTED')
        rows.append(dict(cell_id=c['cell_id'], requirement_kind='physical_sensitivity',
            source_requirement_id='PROTOCOL11_SENSITIVITY' if 'D17' not in condition else 'AM03_D17_SENSITIVITY',
            source_path='integrated-terminal-pilot/docs/scientific_experiment_protocol.md', source_section='6.5/11; AM03',
            family=c['family'], role='DIAGNOSTIC_13M_NOT_PRIMARY_TEST', split='diagnostic',
            scenario_id=f"{c['family']}_diagnostic_seed{c['scenario_seed']}", scenario_seed=c['scenario_seed'],
            arm=c['arm'], training_seed=c['training_seed'], condition=condition,
            physical_profile='QC8_BALANCED_OFAT_V1' if not c['changed_values'] else 'STEP8_OFAT_DERIVED_V1',
            changed_values=c['changed_values'], model_variant='both',
            switch_scope='OUTER_PHYSICS_AND_ITS_CORRECT_FORWARD_MODEL', paired_comparator='A2 and A1 within same condition',
            required_status='MANDATORY_DIAGNOSTIC', training_envelope='CHECK_FROZEN_A3_GATE_BEFORE_EXECUTION' if c['arm']=='A3' else 'NOT_APPLICABLE',
            status='UNSUPPORTED' if unsupported else 'RUNNABLE',
            reason='Locked analysis explicitly says Heavy occupancy0.3 unsupported; no cargo resampling or successful output permitted' if unsupported else None,
            expected_effort='Historical family/arm wall-time proxy; measured run costs recorded per cell',
            alias_of=None))
    for c in old['coupling_cells']:
        base = f"base__{c['family']}__seed{c['scenario_seed']}__B2"
        rows.append(dict(cell_id=f"coupling={c['variant']}__{c['family']}__seed{c['scenario_seed']}__B2",
            requirement_kind='model_coupling', source_requirement_id='PROTOCOL11_COUPLING',
            source_path='integrated-terminal-pilot/docs/scientific_experiment_protocol.md', source_section='6.5/11; scoped AM09/Q6',
            family=c['family'], role='DIAGNOSTIC_13M_NOT_PRIMARY_TEST', split='diagnostic',
            scenario_id=f"{c['family']}_diagnostic_seed{c['scenario_seed']}", scenario_seed=c['scenario_seed'],
            arm='B2', training_seed=None, condition='base', physical_profile='QC8_BALANCED_OFAT_V1',
            changed_values={}, model_variant=c['variant'], switch_scope='CANDIDATE_FORWARD_MODEL_ONLY',
            paired_comparator='both B2 and A2 on same outer physics', required_status='MANDATORY_DIAGNOSTIC',
            training_envelope='NOT_APPLICABLE', status='ALIAS' if c['variant']=='both' else 'RUNNABLE',
            reason='Byte-identical both evaluator; reuse verified base B2 result' if c['variant']=='both' else None,
            expected_effort='Historical full-model B2 proxy; variants may differ substantially',
            alias_of=base if c['variant']=='both' else None))
    for r in rows:
        if not 13_000_000 <= r['scenario_seed'] <= 13_999_999 or r['family'] not in ('itp_medium','itp_heavy'):
            raise ContractError('13M seed/primary family gate')
        r['fingerprint'] = s.digest(dict(version=VERSION,lock=EXPECTED_LOCK,cell=r))
        r['output_path'] = f"cells/{r['fingerprint']}/result.json"
    if len({r['cell_id'] for r in rows}) != len(rows):
        raise ContractError('Duplicate requirements')
    return dict(schema=VERSION, cells=rows, conditions=old['conditions'],
                counts=dict(requirements=len(rows), sensitivity=4320, coupling=160,
                    aliases=sum(r['status']=='ALIAS' for r in rows),
                    unique=sum(r['status']!='ALIAS' for r in rows),
                    runnable=sum(r['status']=='RUNNABLE' for r in rows),
                    unsupported=sum(r['status']=='UNSUPPORTED' for r in rows), optional=0),
                scientific_status='POST_HOC_CONTRACT_RESOLUTION_REQUIRES_OWNER_PACKET',
                original_seed_choice='First20 diagnostic seeds fixed in prior Step8 inventory before generation')


def scenario_key(cell):
    return s.digest(dict(family=cell['family'], seed=cell['scenario_seed'], changes=cell['changed_values'], version=VERSION))


def physical_document(config, cell):
    """Only called by run/resume or explicitly authorized engineering fixtures.

    Occupancy changes the background generator target on an isolated config copy;
    all random keys and cargo semantics stay frozen. No register is re-approved.
    """
    from dataclasses import replace
    from integrated_terminal_pilot.scenarios.generator import generate_scenario_with_diagnostics
    from integrated_terminal_pilot.scenarios.fingerprints import with_fingerprints
    from integrated_terminal_pilot.simulator.diagnostics import derive_fleet
    from integrated_terminal_pilot.simulator.catalog import ScenarioCatalog
    if cell['status'] == 'UNSUPPORTED':
        raise ContractError('Unsupported cell cannot be generated')
    if not 13_000_000 <= cell['scenario_seed'] < 14_000_000:
        raise ContractError('Diagnostic seed band violation')
    original = s.digest(config.parameters)
    params = copy.deepcopy(config.parameters)
    changes = cell['changed_values']
    if 'initial_occupancy' in changes:
        params['families'][cell['family']]['yard']['initial_occupancy_fraction'] = changes['initial_occupancy']
    fork_config = replace(config, parameters=params)
    generated = generate_scenario_with_diagnostics(fork_config,cell['family'],'diagnostic',cell['scenario_seed'])
    if generated.diagnostics.get('initial_inventory',{}).get('target_status','MET') != 'MET':
        error=ContractError('UNEXPECTED_OCCUPANCY_INFEASIBLE: retain failed input, do not count an unachieved target as the requested condition')
        error.generated_input=dict(document=generated.scenario,generation_diagnostics=generated.diagnostics)
        raise error
    doc = copy.deepcopy(derive_fleet(generated.scenario, changes.get('cranes',8)))
    p = doc['physics']
    if 'crane_moves_per_hour' in changes:
        for crane in doc['resources']['quay_cranes']:
            crane['nominal_moves_per_hour'] = changes['crane_moves_per_hour']
    if 'efficiency' in changes:
        p['crane']['efficiency'] = dict.fromkeys(('one','two','three','four_plus'),1.)
    if 'transport_units' in changes: p['transport']['units_per_crane'] = changes['transport_units']
    if 'transport_speed_m_per_min' in changes: p['transport']['speed_m_per_min'] = changes['transport_speed_m_per_min']
    if 'yard_capacity_multiplier' in changes:
        for b in doc['terminal']['yard_blocks']:
            b['handling_capacity_moves_per_hour'] *= changes['yard_capacity_multiplier']
    if 'g_min' in changes: p['yard']['congestion_g_min'] = changes['g_min']
    if 'D17_wait_min' in changes: p['work']['max_load_wait_min'] = changes['D17_wait_min']
    doc = with_fingerprints(doc,generator_config_fingerprint=fork_config.parameters_fingerprint)
    catalog = ScenarioCatalog.from_document(doc,validate=True)
    if (len(catalog.cranes) != changes.get('cranes',8) or catalog.physics.batch_size_containers != 10
            or catalog.physics.max_load_wait_min != changes.get('D17_wait_min',240)
            or catalog.physics.efficiency_basis != 'assigned'):
        raise ContractError('Physical condition invariant failed')
    if s.digest(config.parameters) != original:
        raise ContractError('Shared generator mutation')
    return dict(document=doc, generation_diagnostics=generated.diagnostics,
                derivation=dict(version=VERSION,changed_values=changes,
                    canonical_parameters_sha256=original, diagnostic_parameters_sha256=fork_config.parameters_fingerprint,
                    note='Derived sensitivity input, never an unchanged primary scenario or approval-register edit'))
