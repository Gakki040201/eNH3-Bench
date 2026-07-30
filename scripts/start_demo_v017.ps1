[CmdletBinding(DefaultParameterSetName = "Fixture")]
param(
    [Parameter(ParameterSetName = "Fixture")]
    [switch]$Fixture,

    [Parameter(Mandatory = $true, ParameterSetName = "Live")]
    [switch]$Live,

    [string]$PilotRoot = "F:\eNH3_Bench_API\v016_b1b0",
    [string]$GenerationRunName = "enrr_generation_pilot_v016_b1b0_20260722",
    [string]$DemoRoot = "F:\eNH3_Bench_API\v017_demo_runtime",
    [ValidateRange(1, 65535)]
    [int]$Port = 8765
)

$ErrorActionPreference = "Stop"
$Python = "C:\Python314\python.exe"
$Url = "http://127.0.0.1:$Port"
$Arguments = @(
    (Join-Path $PSScriptRoot "run_demo_v017.py"),
    "--pilot-root", $PilotRoot,
    "--generation-run-name", $GenerationRunName,
    "--demo-root", $DemoRoot,
    "--host", "127.0.0.1",
    "--port", "$Port"
)

Write-Host "eNH3-Bench M017 Demo"
Write-Host "Local URL: $Url"

if ($Live) {
    $SecureKey = Read-Host "Enter the USTC project API key for this process only" -AsSecureString
    $KeyPointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($SecureKey)
    try {
        $ProcessKey = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($KeyPointer)
        $env:ENH3BENCH_API_KEY = $ProcessKey
        $Arguments += "--enable-live-api"
        Write-Host "Live API controls enabled. No provider request is sent automatically."
        & $Python @Arguments
    }
    finally {
        Remove-Item Env:ENH3BENCH_API_KEY -ErrorAction SilentlyContinue
        $ProcessKey = $null
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($KeyPointer)
    }
}
else {
    Write-Host "Fixture-only mode. No credential or provider network call is used."
    & $Python @Arguments
}
