$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoDir = Split-Path -Parent $ScriptDir
$PythonExe = "C:\Users\marco\AppData\Local\Programs\Python\Python311\python.exe"
$apiLog = Join-Path $RepoDir "runtime\logs\api-8002-glm.txt"
$apiErrLog = Join-Path $RepoDir "runtime\logs\api-8002-glm.err.txt"

$env:PYTHONPATH = "src"

Start-Process -FilePath $PythonExe `
    -ArgumentList @("-m", "agent_server.main") `
    -WorkingDirectory $RepoDir `
    -WindowStyle Hidden `
    -RedirectStandardOutput $apiLog `
    -RedirectStandardError $apiErrLog

Write-Host "Started agent_server.main detached."
