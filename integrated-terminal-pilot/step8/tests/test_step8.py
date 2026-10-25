"""Independent hand-constructed fixtures. Never loads experimental outcomes."""
import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from contextlib import contextmanager
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import numpy as np

from statistical import (ContractError, bootstrap_draws, interval, cargo_noninferiority, nested_mean,
                         relative_difference, tails, time_label, combined_label, d24, validate_cargo,
                         wilcoxon_robustness, ranking_agreement, validate_model_checkpoint)
from evidence import verify_panel, publish, publish_bytes, safe_path, protected_source, verify_restoration, sha
from analysis import (average_rows, scenario_lookup, paired_rows, inference,
                      signed_effect, tolerant_ranks, tolerant_ranking_agreement)
from run_step8 import closure, table
from diagnostic_plan import make_plan
from reporting import number, ci_text, markdown_table


@contextmanager
def fixture_directory():
    # Python3.13 mkdtemp's Windows0700 ACL is not traversable by this sandbox's
    # restricted token. Use a normal inherited workspace ACL and preserve these
    # tiny independent fixtures, rather than masking a cleanup PermissionError.
    p=Path(__file__).resolve().parents[2]/"experiments/step8_analysis/test_work"/uuid.uuid4().hex
    p.mkdir(parents=True)
    yield str(p)


def cargo(n=10, u=2, loaded_present=1):
    return dict(N_out=n, U_not_loaded=u, loaded=n-u, T_end_min=100., R_loss_rate=u/n if n else None,
                classes=dict(LOADED_DEPARTED=n-u-loaded_present, LOADED_VESSEL_AT_TERMINAL=loaded_present,
                             NOT_LOADED_ROLLED_OVER=u, NOT_LOADED_VESSEL_PRESENT=0, NOT_LOADED_OTHER=0),
                reconciliation_ok=True, reconciliation=dict(ledger=True, classes=True))


def rows():
    sid = "itp_medium_test_seed12000000"
    return [dict(row_id=f"{sid}_{world}_{arm}_{seed}", scenario_id=sid, split="test", family="itp_medium",
                 world=world, arm=arm, training_seed=seed, status="COMPLETED",
                 pairing=dict(N_out=10, T_end_min=100., fingerprint="shared"),
                 TA=(90.+i), U=1, R=.1, n_vessels=2, waiting_total=20., wall=1., cpu=1.,
                 vessel_TA=[40.,50.+i])
            for world, identities in (("integrated", (("A1",None),("A1n",None),("B1",None),("A2",None),
                                                      ("B2",None),("B2-T",None),("A3",11),("A3",23),("A3",37))),
                                      ("reference", (("A1",None),("A2",None),("A3",11),("A3",23),("A3",37))))
            for i,(arm,seed) in enumerate(identities)]


class StatisticsTests(unittest.TestCase):
    def test_nested_seeds_one_unit(self):
        self.assertEqual(nested_mean({11:1,23:2,37:9}),4)
        aggregate=average_rows([r for r in rows() if r["world"]=="integrated" and r["arm"]=="A3"])
        self.assertEqual(aggregate["TA"],97)
        self.assertEqual(interval({"medium":[aggregate["TA"]]})["n"],1)

    def test_missing_seed_never_survivor_average(self):
        with self.assertRaises(ContractError): nested_mean({11:1,23:2})

    def test_best_seed_refused(self):
        with self.assertRaises(ContractError): nested_mean({23:1})

    def test_failed_seed_invalidates_aggregate(self):
        a=[r for r in rows() if r["world"]=="integrated" and r["arm"]=="A3"]
        a[1]["status"]="FAILED"
        self.assertIsNone(average_rows(a))

    def test_blocked_seed_invalidates_aggregate(self):
        a=[r for r in rows() if r["world"]=="integrated" and r["arm"]=="A3"]
        a[2]["status"]="G_BLOCKED"
        self.assertIsNone(average_rows(a))

    def test_absolute_relative_sign_and_zero(self):
        self.assertEqual(relative_difference(90,100),-10)
        self.assertEqual(relative_difference(110,100),10)
        self.assertIsNone(relative_difference(1,0))

    def test_mean_percent_not_percent_means(self):
        a,b=[1,180],[2,200]
        paired=np.mean([relative_difference(x,y) for x,y in zip(a,b)])
        pooled=relative_difference(np.mean(a),np.mean(b))
        self.assertNotAlmostEqual(paired,pooled)

    def test_bootstrap_exact_rng_and_draw_count(self):
        v=np.array([-2.,1.,7.]); rng=np.random.default_rng(120001)
        expected=v[rng.integers(0,3,(10000,3))].mean(axis=1)
        np.testing.assert_array_equal(bootstrap_draws({"m":v}),expected)

    def test_strata_equal_weights_and_sorted_order(self):
        r=interval({"z":[10.],"a":[2.,2.]})
        self.assertEqual(r["estimate"],6); self.assertEqual(r["lower"],6)
        self.assertEqual(r["n"],3)

    def test_interval_linear_quantile(self):
        draws=bootstrap_draws({"m":[-1.,0.,3.]})
        actual=interval({"m":[-1.,0.,3.]})
        np.testing.assert_array_equal([actual["lower"],actual["upper"]],np.quantile(draws,[.025,.975],method="linear"))

    def test_deterministic_seed_reset(self):
        self.assertEqual(interval({"m":[-1,2,7]}),interval({"m":[-1,2,7]}))

    def test_nonfinite_refused(self):
        with self.assertRaises(ContractError): interval({"m":[float("nan")]})

    def test_ni_upper_not_lower(self):
        r=cargo_noninferiority({"m":[0.,0.,.06]})
        self.assertGreater(r["upper"],.01); self.assertEqual(r["verdict"],"NOT_DEMONSTRATED")
        self.assertLessEqual(r["lower_diagnostic_only"],.01)

    def test_ni_pass_and_zero_sensitivity_fail(self):
        r=cargo_noninferiority({"m":[.005]*3})
        self.assertEqual(r["verdict"],"PASSED");self.assertEqual(r["zero_margin"],"NOT_DEMONSTRATED")

    def test_zero_loss_ni_valid(self):
        r=cargo_noninferiority({"m":[0.]*3})
        self.assertEqual((r["upper"],r["verdict"],r["zero_margin"]),(0.,"PASSED","PASSED"))

    def test_ni_exact_frozen_seed(self):
        values=np.array([-.02,0,.01,.03])
        rng=np.random.default_rng(20261013)
        upper=np.percentile(values[rng.integers(0,4,(10000,4))].mean(axis=1),95)
        self.assertEqual(cargo_noninferiority({"m":values})["upper"],upper)

    def test_existing_frozen_cargo_helper_parity(self):
        from integrated_terminal_pilot.benchmark.cargo_ni import noninferiority
        values=[-.03,.01,.04,-.02]
        self.assertEqual(cargo_noninferiority({"m":values})["upper"],noninferiority(values)["upper_bound"])

    def test_existing_p03_bootstrap_helper_parity(self):
        from berth_allocation_lab.benchmark.stats import paired_bootstrap
        values={"a":[-4.,1.,2.],"z":[5.,3.,-1.]}
        original=paired_bootstrap(values,{"a":.5,"z":.5},seed=120001)
        ours=interval(values)
        self.assertEqual((ours["estimate"],ours["lower"],ours["upper"]),
                         (original["estimate_min"],original["ci_lower_min"],original["ci_upper_min"]))

    def test_primary_does_not_use_unadjusted_interval(self):
        ci=interval({"m":[-10.]*4})
        self.assertEqual(time_label(ci),"LOWER_TIME")
        self.assertTrue(time_label(ci,primary=True).startswith("BLOCKED"))

    def test_b2_cargo_better_time_worse_not_combined_win(self):
        c=cargo_noninferiority({"m":[-.01]*4})
        self.assertEqual(combined_label("HIGHER_TIME",c),"NO_ESTABLISHED_TIME_GAIN")

    def test_ppo_time_better_cargo_ni_fails(self):
        c=cargo_noninferiority({"m":[.03]*4})
        self.assertEqual(combined_label("LOWER_TIME",c),"TIME_GAIN_CARGO_NI_NOT_DEMONSTRATED")

    def test_tail_ids_ties_median_p95(self):
        r=tails([-2,0,2],list("abc"))
        self.assertEqual((r["wins"],r["ties"],r["losses"]),(1,1,1))
        self.assertEqual(r["worst_ids"],["c"]); self.assertAlmostEqual(r["p95"],1.8)

    def test_robustness_zero_and_rank(self):
        self.assertEqual(wilcoxon_robustness([0,0])["pvalue"],1)
        self.assertAlmostEqual(ranking_agreement([1,2,3],[1,2,3]),1)

    def test_float_near_ties_are_not_signed_effects(self):
        self.assertEqual(signed_effect(-1e-12),0)
        self.assertEqual(signed_effect(-2e-6),-1)
        self.assertEqual(signed_effect(2e-6),1)

    def test_tau_uses_tied_reference_costs(self):
        ranks=tolerant_ranks([100.,100.-1e-12,90.])
        np.testing.assert_array_equal(ranks,[2.5,2.5,1.])
        tau=tolerant_ranking_agreement([100.,100.-1e-12,90.],[110.,100.,90.])
        self.assertAlmostEqual(tau,np.sqrt(2/3))


class LedgerAndIdentityTests(unittest.TestCase):
    def test_d24_censor_all_vessels(self):
        v=[dict(vessel_id="a",arrival_time_min=0.,actual_departure_time_min=20.),
           dict(vessel_id="b",arrival_time_min=10.,actual_departure_time_min=None)]
        self.assertEqual(d24(v,100),110)

    def test_d24_departure_after_cutoff_censored(self):
        self.assertEqual(d24([dict(vessel_id="a",arrival_time_min=10.,actual_departure_time_min=150.)],100),90)

    def test_duplicate_vessel_refused(self):
        v=dict(vessel_id="a",arrival_time_min=0.,actual_departure_time_min=None)
        with self.assertRaises(ContractError):d24([v,v],100)

    def test_cargo_loaded_not_departed_counts_loaded(self):
        c=cargo();self.assertEqual(validate_cargo(c,10,100.),.2)

    def test_cargo_cannot_use_teu_denominator(self):
        c=cargo();c["R_loss_rate"]=2/16
        with self.assertRaises(ContractError):validate_cargo(c,10,100.)

    def test_cargo_d17_not_loaded(self):
        c=cargo();c["classes"]["NOT_LOADED_ROLLOVER"]=3
        with self.assertRaises(ContractError):validate_cargo(c,10,100.)

    def test_cargo_nout0_not_applicable(self):
        self.assertIsNone(validate_cargo(cargo(0,0,0),0,100.))

    def test_cargo_cutoff_mismatch(self):
        with self.assertRaises(ContractError):validate_cargo(cargo(),10,101.)

    def test_cargo_failed_original_ledger_blocks(self):
        c=cargo();c["reconciliation_ok"]=False
        with self.assertRaises(ContractError):validate_cargo(c,10,100.)

    def test_exact_model_and_traffic_inventory(self):
        verify_panel(rows())

    def test_mismatched_checkpoint_sha(self):
        with self.assertRaises(ContractError):validate_model_checkpoint(dict(training_seed=11,sha256="wrong"),11,"right")

    def test_checkpoint_swapped_identity(self):
        with self.assertRaises(ContractError):validate_model_checkpoint(dict(training_seed=23,sha256="right"),11,"right")

    def test_duplicate_row_blocks(self):
        rr=rows();rr.append(rr[0])
        with self.assertRaises(ContractError):verify_panel(rr)

    def test_missing_row_blocks(self):
        with self.assertRaises(ContractError):verify_panel(rows()[:-1])

    def test_cross_family_blocks(self):
        rr=rows();rr[0]["family"]="itp_heavy"
        with self.assertRaises(ContractError):verify_panel(rr)

    def test_cross_split_blocks(self):
        rr=rows();rr[0]["split"]="validation"
        with self.assertRaises(ContractError):verify_panel(rr)

    def test_swapped_model_seed_blocks(self):
        rr=rows();rr[-1]["training_seed"]=23
        with self.assertRaises(ContractError):verify_panel(rr)

    def test_pair_nout_drift_blocks(self):
        rr=rows();rr[0]["pairing"]=dict(rr[0]["pairing"],N_out=11)
        with self.assertRaises(ContractError):verify_panel(rr)

    def test_pair_cutoff_drift_blocks(self):
        rr=rows();rr[0]["pairing"]=dict(rr[0]["pairing"],T_end_min=101.)
        with self.assertRaises(ContractError):verify_panel(rr)

    def test_exogenous_drift_blocks(self):
        rr=rows();rr[0]["pairing"]=dict(rr[0]["pairing"],fingerprint="changed")
        with self.assertRaises(ContractError):verify_panel(rr)

    def test_failed_excluded_only_involved_contrast(self):
        rr=rows();rr[0]["status"]="FAILED"
        lookup=scenario_lookup(dict(rows=rr))
        good,excluded=paired_rows(lookup,"B2","A2")
        bad,excluded_bad=paired_rows(lookup,"A2","A1")
        self.assertEqual((len(good),len(excluded),len(bad),len(excluded_bad)),(1,0,0,1))


class IntegrityAndClosureTests(unittest.TestCase):
    def test_immutable_same_value_resume_and_collision(self):
        with fixture_directory() as d:
            p=Path(d)/"x.json";publish(p,{"a":1});publish(p,{"a":1})
            with self.assertRaises(ContractError):publish(p,{"a":2})

    def test_path_traversal_refused(self):
        with self.assertRaises(ContractError):safe_path(Path.cwd(),"../escape")

    def test_scientific_source_hash_drift_refuses(self):
        with fixture_directory() as d:
            base=Path(d);repo=base/"repo";bundle=base/"bundle";repo.mkdir()
            archive=bundle/"source_snapshot/x.py";archive.parent.mkdir(parents=True);archive.write_bytes(b"a\n")
            local=repo/"x.py";local.write_bytes(b"b\n")
            lock={"source_sha256":{"x.py":sha(archive)}}
            with patch("evidence.REPO",repo),patch("evidence.s.source_manifest",return_value={"x.py":sha(local)}):
                with self.assertRaises(ContractError):protected_source(lock,bundle)

    def test_doc_only_head_change_not_parameter_reapproval(self):
        with fixture_directory() as d:
            base=Path(d);repo=base/"repo";bundle=base/"bundle";repo.mkdir()
            archive=bundle/"source_snapshot/x.py";archive.parent.mkdir(parents=True);archive.write_bytes(b"a\n")
            local=repo/"x.py";local.write_bytes(b"a\r\n")
            lock={"source_revision":"historic", "source_sha256":{"x.py":sha(archive)}}
            with patch("evidence.REPO",repo),patch("evidence.s.source_manifest",return_value={"x.py":sha(local)}):
                result=protected_source(lock,bundle)
                self.assertEqual(result["scientific_content"],"UNCHANGED")
                self.assertEqual(result["newline_only"],["x.py"])

    def test_added_protected_path_blocks(self):
        with patch("evidence.s.source_manifest",return_value={"extra.py":"x"}):
            with self.assertRaises(ContractError):protected_source({"source_sha256":{}},Path.cwd())

    def test_seven_restore_paths_and_hashes(self):
        with fixture_directory() as d:
            base=Path(d);(base/"assets").mkdir();(base/"assets/step7_remote_inputs_v2.zip").write_bytes(b"original")
            bundle=base/"b";bundle.mkdir();rr=[];files={}
            for i in range(7):
                p=bundle/f"ref{i}";p.write_bytes(bytes([i]));v=dict(path=p.name,sha256=sha(p),bytes=1)
                rr.append(v);files[p.name]=dict(sha256=v["sha256"],bytes=1)
            receipt=dict(restored=rr,scientific_results_modified=False,models_loaded=False,
                         archive_sha256=sha(base/"assets/step7_remote_inputs_v2.zip"))
            with patch("evidence.PROJECT",base):
                verify_restoration(receipt,dict(files=files),bundle)
                receipt["restored"]=rr[:6]
                with self.assertRaises(ContractError):verify_restoration(receipt,dict(files=files),bundle)

    def test_pending_return_cannot_close(self):
        status=closure({"RETURN_VERIFY":"BYTES_METADATA_ONLY_PENDING"},make_plan(),True)
        self.assertEqual(status["PROJECT_I_FINAL_CLOSED"],"NO")
        self.assertEqual(status["STEP8_CARGO_NONINFERIORITY"],"PROVISIONAL")

    def test_return_pass_alone_cannot_close(self):
        status=closure({"RETURN_VERIFY":"VERIFIED_FULL_CANONICAL"},make_plan(),True)
        self.assertEqual(status["PROJECT_I_FINAL_CLOSED"],"NO")
        self.assertEqual(status["STEP8_DIAGNOSTIC_ABLATIONS"],"BLOCKED")
        self.assertEqual(status["STEP8_S2_INFERENCE"],"BLOCKED")

    def test_plan_keeps_all_models_and_unsupported(self):
        p=make_plan();self.assertTrue(p["sensitivity_explicit_unsupported"])
        seeds={r["training_seed"] for r in p["sensitivity_cells"] if r["arm"]=="A3"}
        self.assertEqual(seeds,{11,23,37});self.assertEqual(p["executed_episodes"],0)
        self.assertEqual(p["coupling_episode_count"],160)

    def test_formatting_known_fixture(self):
        self.assertEqual(number(1.23456),"1.235")
        self.assertEqual(ci_text(dict(estimate=1,lower=0,upper=2)),"1.000 [0.000, 2.000]")
        self.assertEqual(markdown_table(["x"],[[2]]),"| x |\n| --- |\n| 2 |")

    def test_csv_deterministic_fixture(self):
        with fixture_directory() as d:
            p=Path(d)/"x.csv";table(p,[dict(x=1,y=[2,3])]);data=p.read_bytes()
            table(p,[dict(x=1,y=[2,3])]);self.assertEqual(data,p.read_bytes())

    def test_all_figure_outputs_reproducible_independent_fixture(self):
        from figures import render, COLORS
        groups=[]; results=[]; diagnostics=[]
        comparisons={"B2-A2","B2-A1","A3-A1","A3-A2","B2-B2-T","A2-A1","B1-A1","B2-T-A2"}
        for family in ("itp_medium","itp_heavy"):
            for a in (*COLORS,"A3-train11","A3-train23","A3-train37"):
                groups.append(dict(split="test",world="integrated",family=family,arm=a,
                    mean_TA_per_vessel=10.,pooled_vessel_median_TA=9.,pooled_vessel_p95_TA=14.,
                    mean_waiting=2.,mean_p95_waiting=3.,mean_U=1.,mean_R=.005,mean_wall_seconds=2.))
                diagnostics.append(dict(split="test",family=family,arm=a,waits=1,decisions=10,
                                        cost=dict(mean=.1,p95=.2),TA_error=dict(mean=-1.)))
            for c in sorted(comparisons):
                ci=dict(estimate=-1.,lower=-2.,upper=0.)
                results.append(dict(family=family,comparison=c,TA_per_vessel_CI95=ci,
                    paired_percent_CI95=ci,U_CI95=ci,tail=dict(wins=20,losses=10,ties=20),
                    cargo_NI=dict(estimate=0.,upper=.005,verdict="PASSED",zero_margin="NOT_DEMONSTRATED")))
        data=dict(groups=groups,results=results);diag=dict(rows=diagnostics)
        with fixture_directory() as d:
            p=Path(d); names=render(p,data,diag,dict(manifest_sha256="f"*64))
            before={f.name:sha(f) for f in (p/"figures").iterdir()}
            render(p,data,diag,dict(manifest_sha256="f"*64))
            after={f.name:sha(f) for f in (p/"figures").iterdir()}
            self.assertEqual(len(names),8);self.assertEqual(len(before),16);self.assertEqual(before,after)


if __name__=="__main__":unittest.main()
