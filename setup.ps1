$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
if (!(Test-Path .upstream)) {
    git clone https://github.com/markrai/fitbaus-transcriber.git .upstream
    if ($LASTEXITCODE -ne 0) { throw "Dependency clone failed" }
}
git -C .upstream checkout --detach adb1e9530ef8f03758138703ebd737ff8e2bfe24
if ($LASTEXITCODE -ne 0) { throw "Dependency checkout failed" }
if (!(Test-Path .venv)) {
    py -3.12 -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw "Virtual environment setup failed" }
}
& .venv\Scripts\python.exe -m pip install -r requirements.txt
if ($LASTEXITCODE -ne 0) { throw "Dependency installation failed" }
& .venv\Scripts\python.exe -c "import ctranslate2; print('CUDA devices:', ctranslate2.get_cuda_device_count()); assert ctranslate2.get_cuda_device_count() > 0"
if ($LASTEXITCODE -ne 0) { throw "CUDA runtime unavailable" }
