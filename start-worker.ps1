# Start the pipeline worker.
# Default adapter: claude. Switch to gemini with: .\start-worker.ps1 gemini
param(
    [string]$Adapter = "claude",
    [string]$Model   = ""
)

Set-Location $PSScriptRoot

# Load root .env so GEMINI_API_KEY and other secrets are available to the worker
Get-Content ".env" | Where-Object { $_ -match '^\s*[^#].*=.*' } | ForEach-Object {
    $k, $v = $_ -split '=', 2
    [System.Environment]::SetEnvironmentVariable($k.Trim(), $v.Trim(), 'Process')
}

$modelFlag = if ($Model) { "--adapter-model $Model" }
             elseif ($Adapter -eq "gemini") { "--adapter-model gemini-3.1-pro-preview" }
             else { "" }

$cmd = ".\.venv\Scripts\python.exe scripts\run_pipeline.py --adapter $Adapter $modelFlag --api-url http://localhost:8000 --api-key changeme"
Write-Host ">> $cmd" -ForegroundColor Cyan
Invoke-Expression $cmd
