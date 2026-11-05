$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$pythonExe = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonExe)) {
    py -3.12 -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw 'Install Python 3.12, then try again.' }
    & $pythonExe -m pip install -r requirements.lock.txt
    if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed.' }
}
try {
    $existing = Invoke-RestMethod -Uri 'http://127.0.0.1:4331/api/health' -TimeoutSec 15
    if ($existing.app -ne 'blendremake') { throw 'Port 4331 belongs to another application.' }
    Start-Process 'http://127.0.0.1:4331'
    return
} catch {
    if ($_.Exception.Message -like '*belongs to another*') { throw }
}
$logs = Join-Path $PSScriptRoot 'logs'
New-Item -ItemType Directory -Force -Path $logs | Out-Null
Start-Process -FilePath $pythonExe -ArgumentList '-m', 'uvicorn', 'app.server:app', '--host', '127.0.0.1', '--port', '4331' -WorkingDirectory $PSScriptRoot -WindowStyle Hidden -RedirectStandardOutput (Join-Path $logs 'server.log') -RedirectStandardError (Join-Path $logs 'server-error.log')
for ($attempt = 0; $attempt -lt 30; $attempt++) {
    Start-Sleep -Milliseconds 500
    try {
        $ready = Invoke-RestMethod -Uri 'http://127.0.0.1:4331/api/health' -TimeoutSec 2
        if ($ready.app -eq 'blendremake') {
            Start-Process 'http://127.0.0.1:4331'
            return
        }
    } catch { }
}
throw 'BlendClone did not start. Check logs\server-error.log.'
