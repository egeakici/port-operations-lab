"""Convenient foreground actions. Preparing a plan never authorizes execution."""
import argparse
import json
from pathlib import Path
from .contracts import ContractError, require, canonical, digest
from .readiness import PROJECT,PROFILE_PATH,environment,validate_profile
from .campaign import Campaign,read,immutable_json

ACTIONS=('Status','ValidateEnvironment','ValidateProfile','PrepareGeneration','Generate','ResumeGeneration','VerifyGeneration',
         'PrepareBaselines','Baselines','ResumeBaselines','PrepareTraining','Train','ResumeTraining','TrainingStatus',
         'SelectModels','PrepareEvaluation','Evaluate','ResumeEvaluation','VerifyResults','GenerateReport','RecordApproval')


def approval_text(profile_hash):
    return (f'I APPROVE PROJECT04 PROFILE {profile_hash} O1-O6 AND EXACT DERIVED PLANS '
            'p04_exact_campaign_derivation_v1 FOR MANUAL FOREGROUND GENERATION BASELINES FIVE-SEED PPO '
            'VALIDATION-ONLY SELECTION HELDOUT EVALUATION AND REPORTING WITH THE DECLARED BUDGETS. '
            'NO AUTOMATIC CAMPAIGNS OR SCIENTIFIC CLOSURE.')


def main(argv=None):
    parser=argparse.ArgumentParser(prog='Project04 research')
    parser.add_argument('action',choices=ACTIONS)
    parser.add_argument('--profile',default=str(PROFILE_PATH))
    parser.add_argument('--workdir'); parser.add_argument('--approval')
    parser.add_argument('--seed',type=int)
    parser.add_argument('--approval-text'); parser.add_argument('--owner-evidence')
    args=parser.parse_args(argv)
    try:
        if args.action=='ValidateEnvironment': result=environment()
        else:
            c=Campaign(args.profile,workdir=args.workdir,approval_path=args.approval)
            if args.action=='Status': result=c.status()
            elif args.action=='ValidateProfile':
                result=validate_profile(c.profile)
                result['exact_owner_approval_text']=approval_text(c.profile_hash)
                result['approval_path']=str(c.approval)
                result['owner_receipt_status']='OWNER_APPROVAL_PENDING'
                if c.approval.exists():
                    from .research import manual_gate
                    environment(); manual_gate(c.profile,c.approval,c.profile_hash)
                    result['owner_receipt_status']='OWNER_APPROVED_ROOT_VERIFIED'
            elif args.action.startswith('Prepare'):
                op={'PrepareGeneration':'generation','PrepareBaselines':'baselines','PrepareTraining':'training','PrepareEvaluation':'evaluation'}[args.action]
                environment(); result=c.prepare(op)
            elif args.action in {'Generate','ResumeGeneration'}: result=c.generate(resume=args.action=='ResumeGeneration')
            elif args.action=='VerifyGeneration':
                m=c.verify_generation(); result={'status':'GENERATED_COHORTS_VERIFIED','count':m['count'],'roles':['train','validation','test']}
            elif args.action in {'Baselines','ResumeBaselines'}: result=c.baselines(resume=args.action=='ResumeBaselines')
            elif args.action in {'Train','ResumeTraining'}: result=c.train(args.seed,resume=args.action=='ResumeTraining')
            elif args.action=='TrainingStatus': result=c.training_status()
            elif args.action=='SelectModels':
                selections=c.selections(require_all=True)
                result=immutable_json(c.work/'FROZEN_SELECTIONS.json',{'status':'VALIDATION_RESULTS','profile_sha256':c.profile_hash,'selection_receipts':selections,'test_read':False})
            elif args.action in {'Evaluate','ResumeEvaluation'}:
                frozen=read(c.work/'FROZEN_SELECTIONS.json')
                require(frozen['selection_receipts']==c.selections(require_all=True) and frozen['profile_sha256']==c.profile_hash,
                        'FROZEN_SELECTIONS','evaluation','select and freeze every seed before test')
                result=c.evaluate(resume=args.action=='ResumeEvaluation')
            elif args.action=='VerifyResults': result=c.verify_results()
            elif args.action=='GenerateReport':
                from .statistics_report import produce_report
                result=produce_report(c)
            else:
                # This action is only a manual owner declaration. It is never
                # called by installation/preparation/tests or any other action.
                environment(); validate_profile(c.profile)
                require(args.approval_text==approval_text(c.profile_hash) and bool(args.owner_evidence and args.owner_evidence.strip()),
                        'EXPLICIT_OWNER_DECLARATION_REQUIRED','approval','exact quoted text and genuine owner evidence required')
                require(not c.approval.exists(),'APPROVAL_EXISTS','approval','immutable receipt already exists')
                receipt={'status':'OWNER_APPROVED','approved_payload_sha256':c.profile_hash,'owner_evidence':args.owner_evidence,
                         'owner_declaration':args.approval_text,'scope':c.profile['approval_scope']}
                from .scenarios import write_new
                write_new(c.approval,canonical(receipt))
                result={'status':'OWNER_RECEIPT_RECORDED_NO_CAMPAIGN_STARTED','path':str(c.approval)}
        print(json.dumps(result,allow_nan=False)); return 0
    except KeyboardInterrupt:
        print(json.dumps({'status':'INTERRUPTED','recovery':'Use Status/TrainingStatus and resume only committed boundaries; partial files retained.'}))
        return 130
    except (ContractError,OSError,KeyError,ValueError,ImportError) as exc:
        print(json.dumps({'status':'REJECTED','error':str(exc)})); return 2


if __name__=='__main__':
    raise SystemExit(main())
