# Functions only. Sourcing this file never downloads, installs or starts Python.
# The owner-started Complete-Step7.ps1 invokes this before any scientific session.
function Assert-Step7RuntimeArchive {
    param([string]$Path, $Specification)
    if (!(Test-Path -LiteralPath $Path -PathType Leaf)) { throw "Missing Python archive: $Path" }
    if ((Get-Item -LiteralPath $Path).Length -ne $Specification.bytes) {
        throw "Python archive length mismatch; preserved without execution: $Path"
    }
    $step7ExpectedHash = [BitConverter]::ToString([Convert]::FromBase64String($Specification.sha512_base64)).Replace('-','')
    if ((Get-FileHash -LiteralPath $Path -Algorithm SHA512).Hash -ne $step7ExpectedHash) {
        throw "Python archive checksum mismatch; preserved without extraction or execution: $Path"
    }
}

function Expand-Step7RuntimeArchive {
    param([string]$Archive, [string]$Destination, $Specification)
    Assert-Step7RuntimeArchive -Path $Archive -Specification $Specification
    # A fresh destination is mandatory: interruption can never create a half-ready runtime.
    if (Test-Path -LiteralPath $Destination) { throw "Extraction destination already exists: $Destination" }
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $step7Zip = [IO.Compression.ZipFile]::OpenRead($Archive)
    try {
        $step7Prefix = [IO.Path]::GetFullPath($Destination).TrimEnd('\') + '\'
        foreach ($step7Entry in $step7Zip.Entries) {
            $step7EntryPath = [IO.Path]::GetFullPath((Join-Path $Destination $step7Entry.FullName))
            if (!$step7EntryPath.StartsWith($step7Prefix, [StringComparison]::OrdinalIgnoreCase)) {
                throw 'Unsafe path in Python archive; no files extracted.'
            }
        }
        foreach ($step7Required in $Specification.required_members) {
            if ($null -eq $step7Zip.GetEntry($step7Required)) { throw "Python archive lacks $step7Required" }
        }
    } finally { $step7Zip.Dispose() }
    [IO.Compression.ZipFile]::ExtractToDirectory($Archive, $Destination)
}

function Get-Step7ReferencePython {
    param([string]$BootstrapDirectory, [string]$SpecificationPath, [string]$EvidenceDirectory)
    $step7BootstrapSpec = Get-Content -LiteralPath $SpecificationPath -Raw | ConvertFrom-Json
    $step7BootstrapSpecHash = (Get-FileHash -LiteralPath $SpecificationPath -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($step7BootstrapSpec.python -ne '3.13.2') { throw 'Unexpected reference runtime specification.' }
    $step7PortableRoot = Join-Path $BootstrapDirectory 'cpython3132-nuget'
    $step7PortablePython = Join-Path $step7PortableRoot 'tools\python.exe'
    $step7PortableReceipt = Join-Path $step7PortableRoot 'step7_bootstrap_receipt.json'
    New-Item -ItemType Directory -Path $BootstrapDirectory -Force | Out-Null
    if (!(Test-Path -LiteralPath $step7PortableRoot)) {
        $step7Archive = Join-Path $BootstrapDirectory 'python.3.13.2.nupkg'
        if (!(Test-Path -LiteralPath $step7Archive)) {
            Write-Host 'Downloading verified standalone CPython 3.13.2 x64 (14.3 MB); no Windows installer...'
            [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
            $step7Download = $step7Archive + '.' + [guid]::NewGuid().ToString('N') + '.partial'
            Invoke-WebRequest -UseBasicParsing -Uri $step7BootstrapSpec.url -OutFile $step7Download
            Assert-Step7RuntimeArchive -Path $step7Download -Specification $step7BootstrapSpec
            Move-Item -LiteralPath $step7Download -Destination $step7Archive
        }
        $step7Stage = Join-Path $BootstrapDirectory ('extract_' + [guid]::NewGuid().ToString('N'))
        Expand-Step7RuntimeArchive -Archive $step7Archive -Destination $step7Stage -Specification $step7BootstrapSpec
        $step7StagedPython = Join-Path $step7Stage 'tools\python.exe'
        # Bounded interpreter/import checks, not a test suite, benchmark or simulation.
        $step7Probe = "import sys,struct,sysconfig,venv,ensurepip; assert sys.version_info[:3]==(3,13,2),sys.version; assert struct.calcsize('P')==8; assert not sysconfig.get_config_var('Py_GIL_DISABLED'); assert sys.prefix==sys.base_prefix"
        & $step7StagedPython -I -S -c $step7Probe
        if ($LASTEXITCODE -ne 0) { throw "Reference runtime self-check failed; staging directory preserved: $step7Stage" }
        @{
            schema='step7_python_bootstrap_receipt_v1'; specification_sha256=$step7BootstrapSpecHash
            archive_sha512_base64=$step7BootstrapSpec.sha512_base64
            python_exe_sha256=(Get-FileHash -LiteralPath $step7StagedPython -Algorithm SHA256).Hash.ToLowerInvariant()
            python_dll_sha256=(Get-FileHash -LiteralPath (Join-Path $step7Stage 'tools\python313.dll') -Algorithm SHA256).Hash.ToLowerInvariant()
        } | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $step7Stage 'step7_bootstrap_receipt.json') -Encoding UTF8
        # Same-volume directory rename; the final directory appears only after all checks succeed.
        [IO.Directory]::Move($step7Stage, $step7PortableRoot)
    }
    if (!(Test-Path -LiteralPath $step7PortablePython -PathType Leaf) -or !(Test-Path -LiteralPath $step7PortableReceipt -PathType Leaf)) {
        throw "Incomplete reference runtime, preserved without use: $step7PortableRoot"
    }
    $step7Receipt = Get-Content -LiteralPath $step7PortableReceipt -Raw | ConvertFrom-Json
    if ($step7Receipt.specification_sha256 -ne $step7BootstrapSpecHash -or
        $step7Receipt.archive_sha512_base64 -ne $step7BootstrapSpec.sha512_base64 -or
        $step7Receipt.python_exe_sha256 -ne (Get-FileHash -LiteralPath $step7PortablePython -Algorithm SHA256).Hash.ToLowerInvariant() -or
        $step7Receipt.python_dll_sha256 -ne (Get-FileHash -LiteralPath (Join-Path $step7PortableRoot 'tools\python313.dll') -Algorithm SHA256).Hash.ToLowerInvariant()) {
        throw 'Reference runtime integrity differs; do not overwrite or execute it.'
    }
    New-Item -ItemType Directory -Path $EvidenceDirectory -Force | Out-Null
    $step7EvidenceReceipt = Join-Path $EvidenceDirectory 'python_bootstrap_receipt.json'
    if (Test-Path -LiteralPath $step7EvidenceReceipt) {
        if ((Get-FileHash -LiteralPath $step7EvidenceReceipt).Hash -ne (Get-FileHash -LiteralPath $step7PortableReceipt).Hash) {
            throw 'Retained Python bootstrap receipt differs; evidence is never overwritten.'
        }
    } else { Copy-Item -LiteralPath $step7PortableReceipt -Destination $step7EvidenceReceipt }
    Write-Host "Verified reference Python: $step7PortablePython"
    return $step7PortablePython
}
