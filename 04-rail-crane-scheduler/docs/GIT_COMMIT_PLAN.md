# Project 04: 14 yeni commit plani

Bu komutlar repository kokunde PowerShell ile sirasiyla calistirilmak uzere hazirlandi; otomatik calistirilmadi.

Step 01 sozlesmesi zaten `b5cdcc8` commitinde. Buradaki ilk yeni commit onun tekrar kullanim denetimini ekler. Boylece mevcut gecmisi degistirmeden 14 yeni, bos olmayan commit olusur.

Bu gruplama tamamlanmis calisma agacinin dosya bazinda ayrimidir. Ortak dosyalar son hallerini icerir; her ara commit icin bagimsiz test gecisi iddia edilmez. Test kayitlari gelistirme sirasindaki calisma agacini belgeler. CP-SAT bagimlilik engeli, bekleyen bilimsel kararlar ve calistirilmamis uzun egitim/kampanyalar mevcut raporlarda korunur.

Kok `.gitignore` tum Project 04 klasorunu disladigi icin `git add -f` yalnizca tek tek listelenen kaynak, test ve belge dosyalarina uygulanir. Deney klasorleri, model dosyalari, cache ve kokteki prompt paketi dahil degildir. `git add .` veya tum proje klasorune `git add -f` kullanmayin.

Once mevcut indexin bos oldugunu kontrol edin; daha onceden stage edilmis dosyalar varsa bu plana karistirmayin:

```powershell
git status --short
```

Her blokta stage edilen listeyi inceleyin. `git add` hata verirse veya beklenmedik dosya gorurseniz ilgili `git commit` komutunu calistirmayin. Commit basarisiz olursa sonraki bloga gecmeyin. Push komutu yoktur.

## Step 01 (2 dosya)

```powershell
git add -f -- '04-rail-crane-scheduler/docs/development_run/PREFLIGHT.json'
git add -f -- '04-rail-crane-scheduler/docs/development_run/step01_receipt.json'
git commit -m "docs(project04): audit reused Step 01 scientific contract"
```

## Step 02 (18 dosya)

```powershell
git add -f -- '04-rail-crane-scheduler/.gitignore'
git add -f -- '04-rail-crane-scheduler/configs/research/step2_contract_manifest_v1.json'
git add -f -- '04-rail-crane-scheduler/docs/08_data_contracts.md'
git add -f -- '04-rail-crane-scheduler/docs/09_units_coordinates_and_time.md'
git add -f -- '04-rail-crane-scheduler/docs/10_integration_mapping.md'
git add -f -- '04-rail-crane-scheduler/docs/11_step2_validation_and_closure.md'
git add -f -- '04-rail-crane-scheduler/docs/development_run/step02_attempt001.json'
git add -f -- '04-rail-crane-scheduler/docs/development_run/step02_attempt001.xml'
git add -f -- '04-rail-crane-scheduler/docs/development_run/step02_attempt002.json'
git add -f -- '04-rail-crane-scheduler/docs/development_run/step02_attempt002.xml'
git add -f -- '04-rail-crane-scheduler/docs/development_run/step02_receipt.json'
git add -f -- '04-rail-crane-scheduler/pyproject.toml'
git add -f -- '04-rail-crane-scheduler/scripts/check_stage.py'
git add -f -- '04-rail-crane-scheduler/src/rail_crane_scheduler/__init__.py'
git add -f -- '04-rail-crane-scheduler/src/rail_crane_scheduler/contracts.py'
git add -f -- '04-rail-crane-scheduler/tests/conftest.py'
git add -f -- '04-rail-crane-scheduler/tests/fixtures/problem.json'
git add -f -- '04-rail-crane-scheduler/tests/test_step02_contracts.py'
git commit -m "feat(project04): add Step 02 versioned data contracts"
```

## Step 03 (15 dosya)

```powershell
git add -f -- '04-rail-crane-scheduler/docs/development_run/step03_attempt001.json'
git add -f -- '04-rail-crane-scheduler/docs/development_run/step03_attempt001.xml'
git add -f -- '04-rail-crane-scheduler/docs/development_run/step03_attempt002.json'
git add -f -- '04-rail-crane-scheduler/docs/development_run/step03_attempt002.xml'
git add -f -- '04-rail-crane-scheduler/docs/development_run/step03_attempt003.json'
git add -f -- '04-rail-crane-scheduler/docs/development_run/step03_attempt003.xml'
git add -f -- '04-rail-crane-scheduler/docs/development_run/step03_attempt004.json'
git add -f -- '04-rail-crane-scheduler/docs/development_run/step03_attempt004.xml'
git add -f -- '04-rail-crane-scheduler/docs/development_run/step03_attempt005.json'
git add -f -- '04-rail-crane-scheduler/docs/development_run/step03_attempt005.xml'
git add -f -- '04-rail-crane-scheduler/docs/development_run/step03_receipt.json'
git add -f -- '04-rail-crane-scheduler/docs/step03_generator.md'
git add -f -- '04-rail-crane-scheduler/src/rail_crane_scheduler/scenarios.py'
git add -f -- '04-rail-crane-scheduler/tests/fixtures/generator_config.json'
git add -f -- '04-rail-crane-scheduler/tests/test_step03_generator.py'
git commit -m "feat(project04): add Step 03 deterministic scenario generation"
```

## Step 04 (7 dosya)

```powershell
git add -f -- '04-rail-crane-scheduler/docs/development_run/step04_attempt001.json'
git add -f -- '04-rail-crane-scheduler/docs/development_run/step04_attempt001.xml'
git add -f -- '04-rail-crane-scheduler/docs/development_run/step04_receipt.json'
git add -f -- '04-rail-crane-scheduler/docs/step04_physics_validation.md'
git add -f -- '04-rail-crane-scheduler/src/rail_crane_scheduler/kernel.py'
git add -f -- '04-rail-crane-scheduler/src/rail_crane_scheduler/validator.py'
git add -f -- '04-rail-crane-scheduler/tests/test_step04_physics.py'
git commit -m "feat(project04): add Step 04 scheduling kernel and independent validator"
```

## Step 05 (6 dosya)

```powershell
git add -f -- '04-rail-crane-scheduler/docs/development_run/step05_attempt001.json'
git add -f -- '04-rail-crane-scheduler/docs/development_run/step05_attempt001.xml'
git add -f -- '04-rail-crane-scheduler/docs/development_run/step05_receipt.json'
git add -f -- '04-rail-crane-scheduler/docs/step05_baselines.md'
git add -f -- '04-rail-crane-scheduler/src/rail_crane_scheduler/baselines.py'
git add -f -- '04-rail-crane-scheduler/tests/test_step05_baselines.py'
git commit -m "feat(project04): add Step 05 heuristic baselines"
```

## Step 06 (6 dosya)

```powershell
git add -f -- '04-rail-crane-scheduler/docs/development_run/step06_attempt001.json'
git add -f -- '04-rail-crane-scheduler/docs/development_run/step06_attempt001.xml'
git add -f -- '04-rail-crane-scheduler/docs/development_run/step06_receipt.json'
git add -f -- '04-rail-crane-scheduler/docs/step06_cpsat_formulation_and_limits.md'
git add -f -- '04-rail-crane-scheduler/src/rail_crane_scheduler/cpsat.py'
git add -f -- '04-rail-crane-scheduler/tests/test_step06_cpsat.py'
git commit -m "feat(project04): add Step 06 bounded CP-SAT infrastructure"
```

## Step 07 (6 dosya)

```powershell
git add -f -- '04-rail-crane-scheduler/docs/development_run/step07_attempt001.json'
git add -f -- '04-rail-crane-scheduler/docs/development_run/step07_attempt001.xml'
git add -f -- '04-rail-crane-scheduler/docs/development_run/step07_receipt.json'
git add -f -- '04-rail-crane-scheduler/docs/step07_protocol.md'
git add -f -- '04-rail-crane-scheduler/src/rail_crane_scheduler/research.py'
git add -f -- '04-rail-crane-scheduler/tests/test_step07_research.py'
git commit -m "feat(project04): add Step 07 research protocol and execution gates"
```

## Step 08 (10 dosya)

```powershell
git add -f -- '04-rail-crane-scheduler/docs/development_run/step08_attempt001.json'
git add -f -- '04-rail-crane-scheduler/docs/development_run/step08_attempt001.xml'
git add -f -- '04-rail-crane-scheduler/docs/development_run/step08_attempt002.json'
git add -f -- '04-rail-crane-scheduler/docs/development_run/step08_attempt002.xml'
git add -f -- '04-rail-crane-scheduler/docs/development_run/step08_attempt003.json'
git add -f -- '04-rail-crane-scheduler/docs/development_run/step08_attempt003.xml'
git add -f -- '04-rail-crane-scheduler/docs/development_run/step08_receipt.json'
git add -f -- '04-rail-crane-scheduler/docs/step08_environment.md'
git add -f -- '04-rail-crane-scheduler/src/rail_crane_scheduler/environment.py'
git add -f -- '04-rail-crane-scheduler/tests/test_step08_environment.py'
git commit -m "feat(project04): add Step 08 crane scheduling environment"
```

## Step 09 (6 dosya)

```powershell
git add -f -- '04-rail-crane-scheduler/docs/development_run/step09_attempt001.json'
git add -f -- '04-rail-crane-scheduler/docs/development_run/step09_attempt001.xml'
git add -f -- '04-rail-crane-scheduler/docs/development_run/step09_receipt.json'
git add -f -- '04-rail-crane-scheduler/docs/step09_rl_interface.md'
git add -f -- '04-rail-crane-scheduler/src/rail_crane_scheduler/encoding.py'
git add -f -- '04-rail-crane-scheduler/tests/test_step09_encoding.py'
git commit -m "feat(project04): add Step 09 masked RL interface"
```

## Step 10 (9 dosya)

```powershell
git add -f -- '04-rail-crane-scheduler/docs/development_run/step10_attempt001.json'
git add -f -- '04-rail-crane-scheduler/docs/development_run/step10_attempt001.xml'
git add -f -- '04-rail-crane-scheduler/docs/development_run/step10_attempt002.json'
git add -f -- '04-rail-crane-scheduler/docs/development_run/step10_attempt002.xml'
git add -f -- '04-rail-crane-scheduler/docs/development_run/step10_receipt.json'
git add -f -- '04-rail-crane-scheduler/docs/step10_training.md'
git add -f -- '04-rail-crane-scheduler/src/rail_crane_scheduler/training.py'
git add -f -- '04-rail-crane-scheduler/tests/fixtures/training_plan_fixture.json'
git add -f -- '04-rail-crane-scheduler/tests/test_step10_training.py'
git commit -m "feat(project04): add Step 10 manual PPO training infrastructure"
```

## Step 11 (6 dosya)

```powershell
git add -f -- '04-rail-crane-scheduler/docs/development_run/step11_attempt001.json'
git add -f -- '04-rail-crane-scheduler/docs/development_run/step11_attempt001.xml'
git add -f -- '04-rail-crane-scheduler/docs/development_run/step11_receipt.json'
git add -f -- '04-rail-crane-scheduler/docs/step11_evaluation.md'
git add -f -- '04-rail-crane-scheduler/src/rail_crane_scheduler/evaluation.py'
git add -f -- '04-rail-crane-scheduler/tests/test_step11_evaluation.py'
git commit -m "feat(project04): add Step 11 scientific evaluation tools"
```

## Step 12 (7 dosya)

```powershell
git add -f -- '04-rail-crane-scheduler/docs/development_run/step12_attempt001.json'
git add -f -- '04-rail-crane-scheduler/docs/development_run/step12_attempt001.xml'
git add -f -- '04-rail-crane-scheduler/docs/development_run/step12_receipt.json'
git add -f -- '04-rail-crane-scheduler/docs/step12_replay.md'
git add -f -- '04-rail-crane-scheduler/frontend/replay_app.py'
git add -f -- '04-rail-crane-scheduler/src/rail_crane_scheduler/replay.py'
git add -f -- '04-rail-crane-scheduler/tests/test_step12_replay.py'
git commit -m "feat(project04): add Step 12 replay visualization"
```

## Step 13 (6 dosya)

```powershell
git add -f -- '04-rail-crane-scheduler/docs/development_run/step13_attempt001.json'
git add -f -- '04-rail-crane-scheduler/docs/development_run/step13_attempt001.xml'
git add -f -- '04-rail-crane-scheduler/docs/development_run/step13_receipt.json'
git add -f -- '04-rail-crane-scheduler/docs/step13_integration_matrix.md'
git add -f -- '04-rail-crane-scheduler/src/rail_crane_scheduler/integration.py'
git add -f -- '04-rail-crane-scheduler/tests/test_step13_integration.py'
git commit -m "feat(project04): add Step 13 integration adapters"
```

## Step 14 (26 dosya)

```powershell
git add -f -- '04-rail-crane-scheduler/README.md'
git add -f -- '04-rail-crane-scheduler/docs/ARCHITECTURE.md'
git add -f -- '04-rail-crane-scheduler/docs/CLAIM_AUDIT.md'
git add -f -- '04-rail-crane-scheduler/docs/EXECUTIVE_SUMMARY.md'
git add -f -- '04-rail-crane-scheduler/docs/GIT_COMMIT_PLAN.md'
git add -f -- '04-rail-crane-scheduler/docs/MANUAL_EXECUTION.md'
git add -f -- '04-rail-crane-scheduler/docs/development_run/ARTIFACT_INTEGRITY.json'
git add -f -- '04-rail-crane-scheduler/docs/development_run/CHANGED_FILES.json'
git add -f -- '04-rail-crane-scheduler/docs/development_run/CLI_SMOKE.json'
git add -f -- '04-rail-crane-scheduler/docs/development_run/CLI_SMOKE_FINAL.json'
git add -f -- '04-rail-crane-scheduler/docs/development_run/CONTINUATION.md'
git add -f -- '04-rail-crane-scheduler/docs/development_run/FINAL_REPORT.md'
git add -f -- '04-rail-crane-scheduler/docs/development_run/FINAL_STATIC_CHECKS.json'
git add -f -- '04-rail-crane-scheduler/docs/development_run/FINAL_STATUS.json'
git add -f -- '04-rail-crane-scheduler/docs/development_run/OWNER_DECISIONS.md'
git add -f -- '04-rail-crane-scheduler/docs/development_run/PROGRESS.md'
git add -f -- '04-rail-crane-scheduler/docs/development_run/step14_attempt001.json'
git add -f -- '04-rail-crane-scheduler/docs/development_run/step14_attempt001.xml'
git add -f -- '04-rail-crane-scheduler/docs/development_run/step14_attempt002.json'
git add -f -- '04-rail-crane-scheduler/docs/development_run/step14_attempt002.xml'
git add -f -- '04-rail-crane-scheduler/docs/development_run/step14_attempt003.json'
git add -f -- '04-rail-crane-scheduler/docs/development_run/step14_attempt003.xml'
git add -f -- '04-rail-crane-scheduler/docs/development_run/step14_receipt.json'
git add -f -- '04-rail-crane-scheduler/src/rail_crane_scheduler/__main__.py'
git add -f -- '04-rail-crane-scheduler/src/rail_crane_scheduler/cli.py'
git add -f -- '04-rail-crane-scheduler/tests/test_step14_audit.py'
git commit -m "docs(project04): consolidate Step 14 CLI audit and handoff"
```

## Son kontrol

```powershell
git log -14 --oneline
git status --short
```

Kokteki `00_MASTER_ORCHESTRATOR.md` ve `Project04_Batch_Prompt_Package/` bu planin disinda oldugu icin untracked kalabilir.
