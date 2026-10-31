# ==============================================================================
# AgentCorp - Windows Background Task Setup (PowerShell)
# Configures AgentCorp to run automatically in the background at Windows startup
# ==============================================================================

param(
    [string]$AgentName = "Agent-$env:COMPUTERNAME",
    [string]$Persona = "frontend_fiona"
)

$ScriptDir = Split-Path -Parent $PSScriptRoot
$VenvPython = Join-Path $ScriptDir ".venv\Scripts\python.exe"
$RunMeshPy = Join-Path $ScriptDir "run_mesh.py"

Write-Host "=================================================================="
Write-Host "  ⚡ Cài đặt AgentCorp Background Task trên Windows ⚡"
Write-Host "=================================================================="
Write-Host "  Thư mục: $ScriptDir"
Write-Host "  Agent  : $AgentName ($Persona)"

if (-not (Test-Path $VenvPython)) {
    Write-Host "Tạo môi trường ảo .venv..."
    python -m venv "$ScriptDir\.venv"
    & "$ScriptDir\.venv\Scripts\pip.exe" install -r "$ScriptDir\requirements.txt"
}

$Action = New-ScheduledTaskAction -Execute $VenvPython -Argument "`"$RunMeshPy`" --name `"$AgentName`" --persona `"$Persona`"" -WorkingDirectory $ScriptDir
$Trigger = New-ScheduledTaskTrigger -AtLogon
$Principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive -RunLevel Highest
$Settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit 0 -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1)

$TaskName = "AgentCorpMesh"
Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger -Principal $Principal -Settings $Settings -Force

Write-Host "✅ Đã đăng ký thành công Scheduled Task '$TaskName'!"
Write-Host "AgentCorp sẽ tự động chạy ngầm mỗi khi bạn đăng nhập Windows."
Write-Host "Để khởi động ngay: Start-ScheduledTask -TaskName '$TaskName'"
