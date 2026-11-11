# Project 04 — onay sonrası manuel yürütme

Onaylanan kanonik profil:
`d06b10d8e04fd0d3655c22267a4ed6cb48b9caa745fec12ac71a8a7bb19dddbc`.
Gerçek kullanıcı beyanı mevcut `RecordApproval` mekanizmasıyla kaydedildi:
`experiments/research_v1_d06b10d8e04f/owner_approval.json`.
Profilin PROPOSED alanı değiştirilmedi; yetkilendirme ayrı, doğrulanan makbuzdadır.
Eski readiness belgelerindeki OWNER_APPROVAL_PENDING tarihsel durumdur; güncel
durum bu klasördeki STATUS.json dosyasındadır. Makbuz ignored çalışma dizinindedir;
başka bilgisayara taşırken gerçek makbuzu ve hash'ini koruyun, yeniden üretmeyin.

Komutları repository kökünden Windows PowerShell içinde çalıştırın. Her kod
bloğunu ayrı çalıştırın, çıktısını inceleyin ve sonraki aşamaya kendiniz geçin.
Hiçbir komut bir sonraki kampanyayı otomatik başlatmaz. Çıktı veya hata durumunu
incelemeden aşağıdaki blokları topluca çalıştırmayın.

Ek `scripts/manual/Project04.ps1` başlatıcısı onaylı mevcut
`scripts/Project04.ps1` dosyasını çağırır. Onaylı kaynak/araç/konfigürasyon
baytları değiştirilmedi. Ek başlatıcı her işlemden önce tam onay, kaynak ve
konfigürasyon hash'lerini, izole CPU ortamını, en az 2 GiB kullanılabilir RAM ve
10 GiB boş disk alanını kontrol eder. Hata durumunda durur; cihaz veya araştırma
ayarını değiştirmez. Yeni başlatıcı bilimsel bir kaynak değişikliği ya da yeni bir
plan türetme kuralı getirmez; yalnızca ek ön koşullar uygular.

Uzun işlemlerin stdout/stderr akışını yönlendirmeyin veya pipeline'a bağlamayın.
tqdm doğrudan stderr üzerinden PowerShell'e yazar; JSON stdout ayrı kalır.
Yüzde, tamamlanan/toplam iş, süre, hız ve ölçülebildiğinde ETA gerçek sayaçlardır.
PPO çubuğu SB3 num_timesteps callback'ine bağlıdır; optimizer sırasında yeni
ortam adımı tamamlanmadıkça sayacın ilerlememesi normaldir. Checkpoint ve validation
mesajları tqdm.write ile görünür; yapılandırılmış progress.jsonl kayıtları korunur.

## 1. Ortam ve onay

```powershell
.\04-rail-crane-scheduler\scripts\manual\Project04.ps1 ValidateExecution
.\04-rail-crane-scheduler\scripts\manual\Project04.ps1 ValidateEnvironment
.\04-rail-crane-scheduler\scripts\manual\Project04.ps1 ValidateProfile
```

MANUAL_EXECUTION_PREFLIGHT_VERIFIED, VERIFIED ve
owner_receipt_status=OWNER_APPROVED_ROOT_VERIFIED beklenir. Profil kontrolünün
eski genel status alanında OWNER_APPROVAL_PENDING bulunabilir: bu alan değişmez
adayın etiketidir, owner_receipt_status doğrulanmış gerçek onayı belirtir.
RAM/disk veya hash hatası varsa ilerlemeyin.

## 2. Sentetik senaryoları üret

```powershell
.\04-rail-crane-scheduler\scripts\manual\Project04.ps1 PrepareGeneration
.\04-rail-crane-scheduler\scripts\manual\Project04.ps1 Generate
```

PRIMARY_GENERATION_COMPLETE ve 896 senaryo beklenir. Sonucu inceleyip durun.

## 3. Üretimi doğrula

```powershell
.\04-rail-crane-scheduler\scripts\manual\Project04.ps1 VerifyGeneration
```

GENERATED_COHORTS_VERIFIED, toplam 896: train512 / validation128 / test256.
Hash, rol, seed ve fiziksel ayrıklık doğrulanmalıdır.

## 4. Heuristik ve CP-SAT referansları

```powershell
.\04-rail-crane-scheduler\scripts\manual\Project04.ps1 PrepareBaselines
.\04-rail-crane-scheduler\scripts\manual\Project04.ps1 Baselines
```

VALIDATION_BASELINES_COMPLETE, 640 validation hücresi beklenir; 96 CP hücresi
boyut nedeniyle açıkça uygun değildir. Başarısızlıkları ve solver durumlarını
inceleyin. TIMEOUT optimal değildir; OPTIMAL yalnızca desteklenen sonlu alt sınıfı
belirtir. Bu aşama held-out değerlendirme değildir. Sonucu inceleyip durun.

## 5. Yalnızca Seed 1103 eğitimi

```powershell
.\04-rail-crane-scheduler\scripts\manual\Project04.ps1 PrepareTraining
.\04-rail-crane-scheduler\scripts\manual\Project04.ps1 Train -Seed 1103
```

Hedef 1.048.576 gerçek timestep. Her 65.536 adımda validation ve değişmez
checkpoint beklenir. CPU cihazını ve milestone mesajlarını izleyin. Eğitim
bittikten sonra aşağıdaki kontrolü ayrıca çalıştırın.

## 6. İlk seed sonucunu incele

```powershell
.\04-rail-crane-scheduler\scripts\manual\Project04.ps1 TrainingStatus
```

1103 için last_boundary.step=1048576 ve complete_selection_count=1 beklenir.
Model hash'leri kontrol edilir. Seed dizinindeki progress.jsonl, checkpoint
metadata ve selection.json dosyalarını inceleyin. Eksik veya başarısız seed'i
sessizce atlamayın; sorunu çözmeden ilerlemeyin.

## 7. Diğer seed'ler: her blok ayrı

```powershell
.\04-rail-crane-scheduler\scripts\manual\Project04.ps1 Train -Seed 2207
```

Durun, TrainingStatus ile sonucu inceleyin.

```powershell
.\04-rail-crane-scheduler\scripts\manual\Project04.ps1 Train -Seed 3301
```

Durun, TrainingStatus ile sonucu inceleyin.

```powershell
.\04-rail-crane-scheduler\scripts\manual\Project04.ps1 Train -Seed 4409
```

Durun, TrainingStatus ile sonucu inceleyin.

```powershell
.\04-rail-crane-scheduler\scripts\manual\Project04.ps1 Train -Seed 5501
```

```powershell
.\04-rail-crane-scheduler\scripts\manual\Project04.ps1 TrainingStatus
```

Beş seed'in de tam bütçe ve tamamlanmış validation seçimi bulunmalıdır.

## 8. Yalnızca validation ile checkpoint seçimini dondur

```powershell
.\04-rail-crane-scheduler\scripts\manual\Project04.ps1 SelectModels
```

FROZEN_SELECTIONS.json oluşturulur. Bütün seed'ler, validation sıralaması,
checkpoint hash'leri ve tam bütçeler doğrulanır. Test verisine göre seed/model
seçmeyin. Dondurulan dosyayı değiştirmeyin.

## 9. Held-out değerlendirme

```powershell
.\04-rail-crane-scheduler\scripts\manual\Project04.ps1 PrepareEvaluation
.\04-rail-crane-scheduler\scripts\manual\Project04.ps1 Evaluate
```

256 senaryo üzerinde 2.560 planlı hücre beklenir. CP için 192 hücre uygun değildir;
başarısızlıklar ve zaman aşımları kayıtlı kalır. Sonucu inceleyip durun.

## 10. Doğrulama ve nihai rapor

```powershell
.\04-rail-crane-scheduler\scripts\manual\Project04.ps1 VerifyResults
```

HELDOUT_TEST_RESULTS_VERIFIED ve rows=2560 beklenir. Bu kontrol geçerse:

```powershell
.\04-rail-crane-scheduler\scripts\manual\Project04.ps1 GenerateReport
```

Önceden belirlenen bootstrap, istatistikler, şekiller, CSV/JSON, insan okunur
rapor ve hash manifesti üretilir. Bunları inceleyin. Yazılımın çalışması veya bir
checkpoint'in oluşması PPO üstünlüğünü ya da bilimsel kapanışı kanıtlamaz.
Üstünlük iddiası yalnızca onaylı destek/failure/çoklu karşılaştırma koşullarıyla
kurulabilir; Project I canlı veri/arayüz eksikleri DATA_GAP olarak kalır.

## Kesinti sonrası yalnızca açık manuel devam

Tamamlanan değişmez çıktıları silmeyin ve başlangıç komutunu yeniden çalıştırarak
üzerlerine yazmayı denemeyin. Gerekirse aşağıdaki uygun komutlardan yalnızca birini
kendi kararınızla çalıştırın:

```powershell
.\04-rail-crane-scheduler\scripts\manual\Project04.ps1 ResumeGeneration
```

```powershell
.\04-rail-crane-scheduler\scripts\manual\Project04.ps1 ResumeBaselines
```

```powershell
.\04-rail-crane-scheduler\scripts\manual\Project04.ps1 ResumeTraining -Seed 1103
```

```powershell
.\04-rail-crane-scheduler\scripts\manual\Project04.ps1 ResumeEvaluation
```

ResumeTraining için ilgili seed'i belirtin. Yalnızca tamamlanmış optimizer
sınırları kullanılabilir; ilk checkpoint öncesi kesintide güvenli devam yoktur.
Yeni deneme için kayıtları koruyup açık bir karar gerekir. Resume, kesintisiz
eğitimle bit düzeyinde aynı değildir. Gerçek optimizer/resume çalıştırılmadı;
hazırlık testlerinde optimizer güncellemesi kesinlikle yapılmadı.

## Bu hazırlıkta çalıştırılanlar

Gerçek onay kaydı, salt okunur ön kontroller, parametre planı doğrulaması,
dokuz güvenli mühendislik testi ve iki adet TEST_FIXTURE_SYNTHETIC senaryosuyla
görünür tqdm kontrolü. Bilimsel 2–10 aşamaları çalıştırılmadı; primary üretim,
baseline kampanyası, PPO optimizasyonu, beş araştırma seed'i, held-out değerlendirme
ve bilimsel istatistik/rapor kampanyası başlatılmadı. Commit/push yapılmadı.
