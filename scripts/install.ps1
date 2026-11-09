[CmdletBinding()]
param(
  [switch]$Server,
  [switch]$Mobile,
  [switch]$Install,
  [switch]$All
)
$ErrorActionPreference = 'Stop'
$Root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$Venv = Join-Path $Root '.venv'
$MobileDir = Join-Path $Root 'mobile'
$AndroidDir = Join-Path $MobileDir 'android'
$Apk = Join-Path $AndroidDir 'app\build\outputs\apk\debug\app-debug.apk'
if (-not ($Server -or $Mobile -or $Install -or $All)) {
  Write-Host 'Uso: .\scripts\install.ps1 -All | -Server | -Mobile [-Install]'
  exit 2
}
if ($All) { $Server = $true; $Mobile = $true }
if ($Install) { $Mobile = $true }

if ($Server) {
  if (-not (Get-Command python -ErrorAction SilentlyContinue)) { throw 'Python 3 não encontrado.' }
  if (-not (Test-Path (Join-Path $Venv 'Scripts\python.exe'))) { python -m venv $Venv }
  & (Join-Path $Venv 'Scripts\python.exe') -m pip install --upgrade pip
  & (Join-Path $Venv 'Scripts\python.exe') -m pip install -r (Join-Path $Root 'requirements.txt')
  & (Join-Path $Venv 'Scripts\python.exe') -m compileall -q (Join-Path $Root 'autorip') (Join-Path $Root 'autorip_gui.py')
  Write-Host "Servidor preparado em $Venv"
}

if ($Mobile) {
  if (-not (Get-Command node -ErrorAction SilentlyContinue)) { throw 'Node.js não encontrado.' }
  if (-not (Get-Command npm -ErrorAction SilentlyContinue)) { throw 'npm não encontrado.' }
  Push-Location $MobileDir
  try { npm ci; npx cap sync android } finally { Pop-Location }
  if (-not (Test-Path (Join-Path $AndroidDir 'gradlew.bat'))) { throw 'Gradle Android não encontrado.' }
  Push-Location $AndroidDir
  try { .\gradlew.bat assembleDebug --no-daemon } finally { Pop-Location }
  if (-not (Test-Path $Apk)) { throw 'APK não foi gerado.' }
  Get-FileHash $Apk -Algorithm SHA256
  Write-Host "APK gerado: $Apk"
}

if ($Install) {
  if (-not (Get-Command adb -ErrorAction SilentlyContinue)) { throw 'adb não encontrado. Instale Android platform-tools.' }
  $devices = @(adb devices | Select-String '\sdevice$' | ForEach-Object { ($_ -split '\s+')[0] })
  if ($devices.Count -eq 0) { adb devices; throw 'Nenhum telefone ADB autorizado. Ative Depuração USB e aceite a chave no aparelho.' }
  if ($devices.Count -gt 1) { throw "Mais de um telefone conectado: $($devices -join ', ')" }
  adb -s $devices[0] install -r $Apk
  Write-Host "APK instalado no dispositivo $($devices[0])"
}
