param([switch]$CheckOnly)
$ErrorActionPreference = 'Stop'
$taskRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $taskRoot
$taskWgCommit = '5b879f0b960ccb4a3b799ede952256e253ef74cb'
$taskRustupHash = '6f4bef66261261fcb43131be8720bab817d403a09edec7455c371974b90bdb7e'
$taskLlvmHash = 'bd88084d7a3b95906fa295453399015a1fdd7b90a38baa8f78244bd234303737'

function Confirm-TaskHash([string]$TaskPath, [string]$TaskHash) {
    if (-not (Test-Path -LiteralPath $TaskPath)) { throw "Missing $TaskPath" }
    if ((Get-FileHash -LiteralPath $TaskPath -Algorithm SHA256).Hash.ToLower() -ne $TaskHash) {
        throw "Hash mismatch: $TaskPath. Do not silently replace the pinned artifact."
    }
}

if (-not $CheckOnly) {
    New-Item -ItemType Directory -Path local/vendor,local/toolchains,local/vendor/cpython-2.7.18 -Force | Out-Null
    if (-not (Test-Path local/vendor/wg-toolkit-rs/.git)) {
        git clone --no-checkout https://github.com/theorzr/wg-toolkit-rs.git local/vendor/wg-toolkit-rs
        if ($LASTEXITCODE) { throw 'wg-toolkit clone failed' }
        git -C local/vendor/wg-toolkit-rs checkout --detach $taskWgCommit
        if ($LASTEXITCODE) { throw 'wg-toolkit checkout failed' }
    }
    if ((git -C local/vendor/wg-toolkit-rs rev-parse HEAD) -ne $taskWgCommit) { throw 'Unexpected toolkit revision' }
    git -C local/vendor/wg-toolkit-rs config submodule.serde-pickle.url https://github.com/mindstorm38/serde-pickle.git
    git -C local/vendor/wg-toolkit-rs submodule update --init
    if ($LASTEXITCODE) { throw 'Submodule checkout failed' }
    if (Test-Path local/vendor/wg-toolkit-rs/Cargo.lock) {
        if ((Get-FileHash local/vendor/wg-toolkit-rs/Cargo.lock).Hash -ne (Get-FileHash config/wg-toolkit.Cargo.lock).Hash) {
            throw 'Existing Cargo.lock differs; inspect before replacing'
        }
    } else { Copy-Item config/wg-toolkit.Cargo.lock local/vendor/wg-toolkit-rs/Cargo.lock }
    if (-not (Test-Path local/toolchains/rustup-init.exe)) {
        Invoke-WebRequest https://win.rustup.rs/x86_64 -OutFile local/toolchains/rustup-init.exe
    }
    Confirm-TaskHash local/toolchains/rustup-init.exe $taskRustupHash
    $env:CARGO_HOME = Join-Path $taskRoot 'local/toolchains/cargo'
    $env:RUSTUP_HOME = Join-Path $taskRoot 'local/toolchains/rustup'
    if (-not (Test-Path local/toolchains/rustup/toolchains/1.90.0-x86_64-pc-windows-gnu/bin/rustc.exe)) {
        & local/toolchains/rustup-init.exe -y --no-modify-path --profile minimal --default-host x86_64-pc-windows-gnu --default-toolchain 1.90.0
        if ($LASTEXITCODE) { throw 'Local Rust installation failed' }
    }
    $taskArchive = 'local/toolchains/llvm-mingw-20250910-ucrt-x86_64.zip'
    if (-not (Test-Path $taskArchive)) {
        Invoke-WebRequest https://github.com/mstorsjo/llvm-mingw/releases/download/20250910/llvm-mingw-20250910-ucrt-x86_64.zip -OutFile $taskArchive
    }
    Confirm-TaskHash $taskArchive $taskLlvmHash
    if (-not (Test-Path local/toolchains/llvm-mingw-20250910-ucrt-x86_64/bin/llvm-dlltool.exe)) {
        if (Test-Path local/toolchains/llvm-mingw-20250910-ucrt-x86_64) { throw 'Partial LLVM directory exists; inspect it first' }
        Expand-Archive -LiteralPath $taskArchive -DestinationPath local/toolchains
    }
    foreach ($taskSource in @('Lib/opcode.py','Python/marshal.c','Python/import.c')) {
        $taskDest = Join-Path 'local/vendor/cpython-2.7.18' (Split-Path -Leaf $taskSource)
        if (-not (Test-Path $taskDest)) {
            Invoke-WebRequest ('https://raw.githubusercontent.com/python/cpython/v2.7.18/'+$taskSource) -OutFile $taskDest
        }
    }
}
Confirm-TaskHash local/toolchains/rustup-init.exe $taskRustupHash
Confirm-TaskHash local/toolchains/llvm-mingw-20250910-ucrt-x86_64.zip $taskLlvmHash
if ((git -C local/vendor/wg-toolkit-rs rev-parse HEAD) -ne $taskWgCommit) { throw 'Unexpected toolkit revision' }
if ((git -C local/vendor/wg-toolkit-rs/serde-pickle rev-parse HEAD) -ne 'bb098cafb6775604614000d58a885a72dd5c495f') { throw 'Unexpected submodule revision' }
Confirm-TaskHash local/vendor/cpython-2.7.18/opcode.py 'acfe212847ecb81ca28bdab976a3caacff3568b45a9e8ca78d6957f9f3ef4884'
. ./tools/rust_env.ps1
rustc --version
if ($LASTEXITCODE) { throw 'Rust unavailable' }
cargo --version
if ($LASTEXITCODE) { throw 'Cargo unavailable' }
python --version
if ($LASTEXITCODE) { throw 'Python unavailable' }
dotnet --list-sdks
if ($LASTEXITCODE) { throw '.NET SDK unavailable' }
Write-Output 'PASS: pinned research prerequisites available; no client executable was started.'
