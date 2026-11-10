"""Explicit bounded commands. No command launches work at import time."""
import argparse
import json
from pathlib import Path
from .contracts import ContractError,QCSPProblem,strict_json,digest,canonical,require


def _emit_plan(payload,output=None,**extra):
    from .research import source_snapshot
    planned=dict(payload); planned['source_sha256']=source_snapshot()
    if output:
        from .scenarios import write_new
        write_new(output,canonical(planned))
    print(json.dumps({'status':'PENDING_OWNER_APPROVAL','plan_hash':digest(planned),'payload':planned,'saved_to':output,**extra}))


def main(argv=None):
    parser = argparse.ArgumentParser(prog="rail_crane_scheduler")
    sub = parser.add_subparsers(dest="command", required=True)
    gen = sub.add_parser("generator")
    gen.add_argument("--config", required=True)
    gen.add_argument("--mode", choices=["validate", "manifest", "generate-fixture", "plan-manual", "generate-manual"], required=True)
    gen.add_argument("--output")
    gen.add_argument('--approval'); gen.add_argument('--manual-confirm')
    for command,modes in [
        ('benchmark',['plan','status','validate','run-development-small']),
        ('training',['check','plan','status','smoke-fixture','train','resume','validate']),
        ('evaluation',['status','verify','prepare-test-manifest','evaluate','analyze-existing','render-existing','render-plots']),
        ('solver',['check','smoke']),
        ('replay',['render'])]:
        p=sub.add_parser(command); p.add_argument('--mode',choices=modes,required=True)
        for name in ('config','problem','schedule','output','existing','approval','manual-confirm','checkpoint','resume-checkpoint'):
            p.add_argument('--'+name)
        p.add_argument('--seed',type=int); p.add_argument('--resume',action='store_true')
        p.add_argument('--tick-min',type=float); p.add_argument('--wall-limit-s',type=float); p.add_argument('--max-nodes',type=int)
    args = parser.parse_args(argv)
    try:
        if args.command == "generator":
            from .scenarios import GeneratorConfig, generate, write_fixture,generate_manual
            if args.mode=='plan-manual':
                payload=strict_json(Path(args.config).read_text(encoding='utf-8'))
                configs=tuple(GeneratorConfig.from_dict(raw) for raw in payload['configs'])
                require(bool(configs),'EMPTY_COHORT','configs','explicit configuration list required')
                _emit_plan(payload,args.output,scenario_count=len(configs),scientific_execution=False)
                return 0
            if args.mode=='generate-manual':
                require(all((args.approval,args.manual_confirm,args.output)),'OWNER_APPROVAL_REQUIRED','command','separate approval, exact digest and new output required')
                payload=strict_json(Path(args.config).read_text(encoding='utf-8'))
                print(json.dumps(generate_manual(payload,args.approval,args.manual_confirm,args.output)))
                return 0
            config = GeneratorConfig.from_json(Path(args.config).read_text(encoding="utf-8"))
            if args.mode == "validate":
                print(json.dumps({"status": "CONFIG_VALID", "config_hash": config.fingerprint}))
            elif args.mode == "manifest":
                p = generate(config)
                print(json.dumps({"config_hash": config.fingerprint, "problem_hash": p.fingerprint, "origin": p.metadata.origin}))
            else:
                if not args.output: parser.error("--output required")
                print(json.dumps(write_fixture(config, args.output)))
        elif args.command=='benchmark':
            from .research import candidate_lock,write_development,verify_records
            from .baselines import paired_development
            if args.mode in {'plan','status'}: print(json.dumps(candidate_lock()))
            else:
                require(bool(args.problem),'CLI_INPUT','problem','explicit development problem required')
                p=QCSPProblem.from_json(Path(args.problem).read_text(encoding='utf-8'))
                require(p.metadata.role in {'development','diagnostic'},'SPLIT_GUARD','problem','no held-out benchmark via development command')
                require(len(p.tasks)<=32,'DEVELOPMENT_BOUND','problem.tasks','small fixture runner permits at most 32 jobs')
                rows=paired_development(p)
                if args.mode=='validate': print(json.dumps({'status':'DEVELOPMENT_VALIDATED','rows':len(rows),'verified':verify_records(rows,p)}))
                else:
                    require(bool(args.output),'CLI_OUTPUT','output','new output directory required')
                    print(json.dumps(write_development(p,rows,args.output)))
        elif args.command=='solver':
            import importlib.util
            if args.mode=='check': print(json.dumps({'status':'AVAILABLE_UNVERIFIED' if importlib.util.find_spec('ortools') else 'DEPENDENCY_PENDING'}))
            else:
                from .cpsat import solve
                require(all(x is not None for x in (args.problem,args.tick_min,args.wall_limit_s,args.max_nodes)),'CLI_INPUT','solver','explicit problem/grid/time/node budgets required')
                p=QCSPProblem.from_json(Path(args.problem).read_text(encoding='utf-8'))
                r=solve(p,tick_min=args.tick_min,wall_limit_s=args.wall_limit_s,max_nodes=args.max_nodes)
                print(json.dumps({'status':r.status,'objective_min':r.objective_min,'bound_min':r.bound_min,'detail':r.detail}))
        elif args.command=='training':
            import importlib.metadata
            if args.mode=='check':
                names=['numpy','gymnasium','torch','stable-baselines3','sb3-contrib']
                print(json.dumps({'status':'DEPENDENCY_METADATA_ONLY_NOT_TRAINING','versions':{n:importlib.metadata.version(n) for n in names}}))
            elif args.mode=='status':
                paths=sorted(Path(args.existing).rglob('selection.json')) if args.existing and Path(args.existing).exists() else []
                print(json.dumps({'selection_receipts':[str(p) for p in paths],'scientific_training_status':'REQUIRES_VERIFIED_OWNER_RUN' if paths else 'NOT_RUN'}))
            else:
                from .training import TrainingConfig,make_env,make_model,save_checkpoint,train_manual,validate_manual
                from .research import source_snapshot
                require(bool(args.config),'CLI_INPUT','config','explicit config required')
                payload=strict_json(Path(args.config).read_text(encoding='utf-8'))
                config=TrainingConfig.from_dict(payload['training_config'])
                if args.mode=='plan':
                    _emit_plan(payload,args.output,estimated_work_steps=len(config.seeds)*config.total_steps,runtime_estimate=None)
                elif args.mode=='smoke-fixture':
                    require(bool(args.problem) and bool(args.output) and config.device=='cpu','SMOKE_CONFIG','smoke','explicit fixture/output and CPU config required')
                    p=QCSPProblem.from_json(Path(args.problem).read_text(encoding='utf-8'))
                    require(p.metadata.origin=='TEST_FIXTURE_SYNTHETIC','SMOKE_CONFIG','problem','fixture-only; no research model')
                    env=make_env(p,config); model=make_model(env,config,config.seeds[0]); obs,_=env.reset(seed=config.seeds[0])
                    action,_=model.predict(obs,deterministic=True,action_masks=env.action_masks())
                    data=save_checkpoint(model,args.output,config,env,seed=config.seeds[0],label='SMOKE_UNTRAINED_NOT_RESEARCH')
                    print(json.dumps({'status':'SMOKE_UNTRAINED_NOT_RESEARCH','action':int(action),'trained_steps':data['trained_steps']}))
                else:
                    require(bool(args.approval) and bool(args.manual_confirm),'OWNER_APPROVAL_REQUIRED','command','separate approval file and exact plan digest required')
                    if args.mode=='validate':
                        require(bool(args.checkpoint),'CLI_INPUT','checkpoint','trained checkpoint required')
                        print(json.dumps(validate_manual(payload,args.approval,args.manual_confirm,args.checkpoint)))
                    else:
                        require(bool(args.output),'CLI_OUTPUT','output','new run directory required')
                        if args.mode=='resume': require(bool(args.resume_checkpoint) and args.seed is not None,'RESUME_CONFIG','resume','explicit checkpoint and predeclared seed required')
                        print(json.dumps(train_manual(payload,args.approval,args.manual_confirm,args.output,resume_checkpoint=args.resume_checkpoint if args.mode=='resume' else None,only_seed=args.seed)))
        elif args.command=='evaluation':
            from .evaluation import read_existing,render_report,evaluate_manual,analyze_rows
            from .research import source_snapshot
            if args.mode=='prepare-test-manifest':
                require(bool(args.config),'CLI_INPUT','config','explicit proposed evaluation plan required')
                payload=strict_json(Path(args.config).read_text(encoding='utf-8'))
                _emit_plan(payload,args.output,test_inputs_read=False)
            elif args.mode=='evaluate':
                require(all((args.config,args.approval,args.manual_confirm,args.output)),'OWNER_APPROVAL_REQUIRED','evaluation','explicit plan/approval/confirmation/new output required')
                payload=strict_json(Path(args.config).read_text(encoding='utf-8'))
                print(json.dumps(evaluate_manual(payload,args.approval,args.manual_confirm,args.output,resume=args.resume)))
            else:
                rows=read_existing(args.existing) if args.existing else []
                if args.mode in {'status','verify'}: print(json.dumps({'status':'RECORDED_CELLS_VERIFIED' if rows else 'SCIENTIFIC_EVIDENCE_NOT_YET_RUN','rows':len(rows),'scientifically_closed':False}))
                elif args.mode=='render-existing':
                    analysis=None
                    if rows:
                        payload=strict_json((Path(args.existing)/'plan.json').read_text(encoding='utf-8'))
                        analysis=analyze_rows(rows,seeds=tuple(payload['training_config']['seeds']),**payload['analysis'])
                    report=render_report(rows,analysis,args.existing)
                    if args.output:
                        from .scenarios import write_new
                        write_new(args.output,report.encode('utf-8'))
                    else: print(report)
                elif args.mode=='render-plots':
                    from .evaluation import analysis_figures
                    from .replay import png_bytes
                    from .scenarios import write_new
                    require(bool(rows) and bool(args.output),'NO_EVIDENCE','plots','existing verified rows and new plot directory required')
                    payload=strict_json((Path(args.existing)/'plan.json').read_text(encoding='utf-8'))
                    analysis=analyze_rows(rows,seeds=tuple(payload['training_config']['seeds']),**payload['analysis'])
                    figures=analysis_figures(rows,analysis)
                    out=Path(args.output); require(not out.exists(),'OUTPUT_EXISTS','plots','new output directory required'); out.mkdir(parents=True)
                    for name,figure in figures.items(): write_new(out/(name+'.png'),png_bytes(figure))
                    print(json.dumps({'status':'RENDERED_EXISTING_RECORDS_ONLY','plots':list(figures)}))
                else:
                    require(bool(args.existing) and bool(rows),'NO_EVIDENCE','analysis','actual verified records required')
                    payload=strict_json((Path(args.existing)/'plan.json').read_text(encoding='utf-8'))
                    print(json.dumps(analyze_rows(rows,seeds=tuple(payload['training_config']['seeds']),**payload['analysis'])))
        elif args.command=='replay':
            from .replay import load_replay,gantt_figure,png_bytes
            from .scenarios import write_new
            require(all((args.problem,args.schedule,args.output)),'CLI_INPUT','replay','explicit existing input/trace and new PNG output required')
            replay=load_replay(Path(args.problem).read_bytes(),Path(args.schedule).read_bytes())
            write_new(args.output,png_bytes(gantt_figure(replay)))
            print(json.dumps({'status':'RENDERED_RECORDED_TRACE','valid_complete':replay.verdict.valid_complete}))
        return 0
    except (ContractError, OSError, KeyError, ImportError, ValueError) as exc:
        print(json.dumps({"status": "REJECTED", "error": str(exc)}))
        return 2
