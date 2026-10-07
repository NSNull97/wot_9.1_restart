# Dot-source from the workspace to use only the locally installed toolchain.
$taskRoot = Split-Path -Parent $PSScriptRoot
$env:CARGO_HOME = Join-Path $taskRoot 'local/toolchains/cargo'
$env:RUSTUP_HOME = Join-Path $taskRoot 'local/toolchains/rustup'
$taskRustBase = Join-Path $env:RUSTUP_HOME 'toolchains/1.90.0-x86_64-pc-windows-gnu/lib/rustlib/x86_64-pc-windows-gnu'
$taskLlvmBin = Join-Path $taskRoot 'local/toolchains/llvm-mingw-20250910-ucrt-x86_64/bin'
$taskCargoBin = Join-Path $env:CARGO_HOME 'bin'
$taskRustBin = Join-Path $taskRustBase 'bin/self-contained'
$env:PATH = "$taskLlvmBin;$taskRustBin;$taskCargoBin;" + $env:PATH
$env:CARGO_TARGET_X86_64_PC_WINDOWS_GNU_LINKER = Join-Path $taskRustBin 'x86_64-w64-mingw32-gcc.exe'
$env:RUSTFLAGS = '-L native=' + (Join-Path $taskRustBase 'lib/self-contained')
$env:CARGO_TARGET_DIR = Join-Path $taskRoot 'local/vendor/wg-toolkit-rs/target'
