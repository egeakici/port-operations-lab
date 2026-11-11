# Isolated Project 04 research environment

Installed and verified on 2026-11-11 (Europe/Istanbul):
`04-rail-crane-scheduler/.venv-research/`, CPython 3.13.2, Windows AMD64.
No shared/global/legacy Python package was installed or upgraded.

The selected device is explicitly CPU. Registry reports Intel Iris Xe graphics;
no NVIDIA tool was found, PyTorch's CUDA build is null and CUDA availability is
false. Real CPU tensor matrix multiplication passed. A CUDA tensor test is not
claimed. The i7-1355U has 10 physical /12 logical CPUs and 16.77 GB RAM; torch
uses 2 threads for the proposed study, one DummyVecEnv. No CPU/GPU speed comparison
or optimizer benchmark was performed, so no training-runtime promise is made.

Available RAM was initially only 0.41 GB, later about 1.06 GB. Availability changes
with other applications. Training/evaluation fail before starting if less than
2 GiB is available, or less than 10 GiB disk is free. Close other applications
before manual training; the tool never kills user processes. Initial free disk
was about 589 GB. These are observed host values, not training requirements
measured by a pilot optimization run.

## Exact environment and hashes

`configs/research/environment_lock_v1.json` pins the Python/platform and all
70 installed distributions (including local package/pip). The top-level capability
versions are NumPy 2.2.3, SciPy 1.15.2, pandas 2.3.3, pytest 9.1.1, tqdm 4.67.1,
Gymnasium 1.2.3, SB3 2.8.0, sb3-contrib 2.8.0, PyTorch 2.6.0 CPU, OR-Tools
9.12.4544, Matplotlib 3.10.1, Streamlit 1.61.1 and psutil 7.2.2. pandas is also
required by the actual solver/frontend dependency graph; no unrelated ML stack
was installed. `INSTALLED_PACKAGES.md` lists every exact distribution/version.

`configs/research/requirements-research.lock` contains the 68 dependency wheels
with their actual SHA-256 archive hashes, obtained from pip's installation report.
The local editable package and pip bootstrap are handled separately. These are
Windows CPython 3.13 wheels, not a cross-platform lock. `requirements-resolved.txt`
records the complete freeze. INSTALL_REPORT.json retains URLs, archive hashes and
package metadata; PACKAGING_INSTALL_REPORT.json records the editable install.
Local raw install/test `.log` files are retained and ignored; JUnit and JSON
receipts are trackable.

Actual installation commands (project-root relative, run in this task):

```powershell
python -m venv .\04-rail-crane-scheduler\.venv-research
# Managed sandbox ensurepip initially failed on temporary-directory permissions.
.\04-rail-crane-scheduler\.venv-research\Scripts\python.exe -m ensurepip --upgrade --default-pip
.\04-rail-crane-scheduler\.venv-research\Scripts\python.exe -m pip install --disable-pip-version-check --cache-dir .\04-rail-crane-scheduler\experiments\pip-cache --report .\04-rail-crane-scheduler\docs\research_readiness\INSTALL_REPORT.json numpy==2.2.3 scipy==1.15.2 pandas==2.3.3 pytest==9.1.1 tqdm==4.67.1 gymnasium==1.2.3 stable-baselines3==2.8.0 sb3-contrib==2.8.0 torch==2.6.0 ortools==9.12.4544 matplotlib==3.10.1 streamlit==1.61.1 psutil==7.2.2
.\04-rail-crane-scheduler\.venv-research\Scripts\python.exe -m pip install --no-deps -e .\04-rail-crane-scheduler
.\04-rail-crane-scheduler\.venv-research\Scripts\python.exe -m pip check
```

Sandbox execution elevation was needed for ensurepip/pip temporary directories
and network downloads; this did not modify OS-wide privileges or install globally.
Both initial permission failures remain described in WORKLOG.md. Compatible
binary wheels were installed rather than changing the scheduling problem.

To reproduce after preserving any old environment, on a matching Python host:

```powershell
.\04-rail-crane-scheduler\scripts\Setup-ResearchEnvironment.ps1
.\04-rail-crane-scheduler\scripts\Project04.ps1 ValidateEnvironment
```

The setup script validates an existing environment and refuses to silently repair
or upgrade a drifted one. It uses hashed wheels and no-deps local packaging for a
fresh environment. This task verified the installed environment and packaging;
it did not delete/recreate the verified environment merely to test installation
again. Syntax and the existing-environment validation branch are tested.

Sources: [OR-Tools 9.12 CPython 3.13 Windows wheel](https://pypi.org/project/ortools/9.12.4544/),
[PyTorch official 2.6 build choices](https://docs.pytorch.org/get-started/previous-versions/).
Actual local imports/tensor/solver tests establish compatibility on this host.
