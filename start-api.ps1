# Start FastAPI with hot-reload. Prompts are NOT auto-reloaded - run load-prompts.ps1 after prompt changes.
Set-Location $PSScriptRoot
.\.venv\Scripts\python.exe -m uvicorn main:app --reload --app-dir api
