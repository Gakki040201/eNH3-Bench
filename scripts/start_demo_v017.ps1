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
    [int]$Port = 8765,
    [ValidateRange(1, 2147483647)]
    [int]$MaxOutputTokens = 4096,
    [ValidateScript({ $_ -gt 0 -and -not [double]::IsNaN($_) -and -not [double]::IsInfinity($_) })]
    [double]$TimeoutSeconds = 900
)

$ErrorActionPreference = "Stop"
$PythonCommand = $null
$PythonPrefixArguments = @()
$PreferredPython = "C:\Python314\python.exe"

if (Test-Path -LiteralPath $PreferredPython -PathType Leaf) {
    $PythonCommand = $PreferredPython
}
elseif ($PythonCandidate = Get-Command python.exe -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1) {
    $PythonCommand = $PythonCandidate.Source
}
elseif ($PythonCandidate = Get-Command python -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1) {
    $PythonCommand = $PythonCandidate.Source
}
elseif ($PythonCandidate = Get-Command py -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1) {
    $PythonCommand = $PythonCandidate.Source
    $PythonPrefixArguments = @("-3")
}
else {
    throw "Python 3.10 or newer was not found."
}

$PythonVersionText = & $PythonCommand @PythonPrefixArguments -c "import sys; print('.'.join(str(part) for part in sys.version_info[:3]))"
if ($LASTEXITCODE -ne 0) {
    throw "The selected Python command could not report its version."
}
$PythonVersion = [version]$PythonVersionText.Trim()
if ($PythonVersion -lt [version]"3.10") {
    throw "Python 3.10 or newer is required; selected version is $PythonVersion."
}

$Url = "http://127.0.0.1:$Port"
$Arguments = @(
    (Join-Path $PSScriptRoot "run_demo_v017.py"),
    "--pilot-root", $PilotRoot,
    "--generation-run-name", $GenerationRunName,
    "--demo-root", $DemoRoot,
    "--host", "127.0.0.1",
    "--port", "$Port",
    "--max-output-tokens", "$MaxOutputTokens",
    "--timeout-seconds", "$TimeoutSeconds"
)

$SelectedPythonDisplay = (@($PythonCommand) + $PythonPrefixArguments) -join " "
$Mode = if ($Live) { "Live" } else { "Fixture" }
Write-Host "selected Python command = $SelectedPythonDisplay"
Write-Host "Python version = $PythonVersion"
Write-Host "mode = $Mode"
Write-Host "local URL = $Url"
Write-Host "pilot root = $PilotRoot"
Write-Host "demo root = $DemoRoot"
Write-Host "Live max_tokens = $MaxOutputTokens"
Write-Host "Live timeout seconds = $TimeoutSeconds"

if ($Live) {
    $SecureKey = $null
    $KeyPointer = [IntPtr]::Zero
    try {
        $SecureKey = Read-Host "Enter the USTC project API key for this process only" -AsSecureString
        $KeyPointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($SecureKey)
        $ProcessKey = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($KeyPointer)
        if ([string]::IsNullOrWhiteSpace($ProcessKey)) {
            throw "The API key must not be empty."
        }
        $env:ENH3BENCH_API_KEY = $ProcessKey
        Remove-Variable ProcessKey -ErrorAction SilentlyContinue
        $Arguments += "--enable-live-api"
        & $PythonCommand @PythonPrefixArguments @Arguments
    }
    finally {
        Remove-Item Env:ENH3BENCH_API_KEY -ErrorAction SilentlyContinue
        Remove-Variable ProcessKey -ErrorAction SilentlyContinue
        $SecureKey = $null
        Remove-Variable SecureKey -ErrorAction SilentlyContinue
        if ($KeyPointer -ne [IntPtr]::Zero) {
            [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($KeyPointer)
            $KeyPointer = [IntPtr]::Zero
        }
    }
}
else {
    & $PythonCommand @PythonPrefixArguments @Arguments
}
