param(
    [string]$SetupPath = "Output\AutoRIP_Setup.exe",
    [int]$StartupTimeoutSeconds = 90
)

$ErrorActionPreference = "Stop"
if ($env:OS -ne "Windows_NT") {
    throw "O smoke test do instalador exige Windows."
}

$repository = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$setup = (Resolve-Path (Join-Path $repository $SetupPath)).Path
$temporaryRoot = if ($env:RUNNER_TEMP) { $env:RUNNER_TEMP } else { $env:TEMP }
$smokeRoot = Join-Path $temporaryRoot ("AutoRIP-Install-Smoke-" + [guid]::NewGuid().ToString("N"))
$installation = Join-Path $smokeRoot "programa"
$dataHome = Join-Path $smokeRoot "dados"
New-Item -ItemType Directory -Force -Path $dataHome | Out-Null

# Isolar totalmente o estado do teste: nada deve sair para a impressora.
$settings = @{
    offline_mode = $true
    auto_mode = $false
    label_enabled = $false
    hot_folder = (Join-Path $dataHome "entrada")
    output_folder = (Join-Path $dataHome "saida")
    done_folder = (Join-Path $dataHome "concluidos")
    error_folder = (Join-Path $dataHome "erros")
    printed_folder = (Join-Path $dataHome "impressos")
}
$json = $settings | ConvertTo-Json -Compress
$utf8 = New-Object System.Text.UTF8Encoding($false)
[System.IO.File]::WriteAllText((Join-Path $dataHome "autorip.json"), $json, $utf8)

$app = $null
$previousHome = $env:AUTORIP_HOME
$previousBrowser = $env:AUTORIP_NOBROWSER
try {
    Write-Host "Instalando AutoRIP em diretorio descartavel (sem impressora)..."
    $setupArgs = @("/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/SP-", "/DIR=$installation")
    $installerProcess = Start-Process -FilePath $setup -ArgumentList $setupArgs -Wait -PassThru
    if ($installerProcess.ExitCode -ne 0) {
        throw "Inno Setup retornou codigo $($installerProcess.ExitCode)."
    }

    $exe = Join-Path $installation "AutoRIP.exe"
    if (-not (Test-Path -LiteralPath $exe -PathType Leaf)) {
        throw "O instalador terminou sem criar AutoRIP.exe."
    }

    # Confere integridade dos bytes instalados, nao somente o status do setup.
    $compiledExe = Join-Path $repository "dist\AutoRIP\AutoRIP.exe"
    $compiledHash = (Get-FileHash -LiteralPath $compiledExe -Algorithm SHA256).Hash
    $installedHash = (Get-FileHash -LiteralPath $exe -Algorithm SHA256).Hash
    if ($compiledHash -ne $installedHash) {
        throw "O executavel instalado difere do executavel compilado."
    }

    $env:AUTORIP_HOME = $dataHome
    $env:AUTORIP_NOBROWSER = "1"
    Write-Host "Iniciando AutoRIP instalado em modo web local e offline..."
    $app = Start-Process -FilePath $exe -ArgumentList "--web" -WorkingDirectory $installation -PassThru
    $deadline = (Get-Date).AddSeconds($StartupTimeoutSeconds)
    $received = $null
    while ((Get-Date) -lt $deadline) {
        $app.Refresh()
        if ($app.HasExited) {
            throw "AutoRIP encerrou antes de disponibilizar o painel (exit $($app.ExitCode))."
        }
        try {
            $response = Invoke-WebRequest -Uri "http://127.0.0.1:8765/api/state" -UseBasicParsing -TimeoutSec 3
            if ($response.StatusCode -eq 200) {
                $received = $response.Content | ConvertFrom-Json
                break
            }
        }
        catch {
            Start-Sleep -Seconds 2
        }
    }

    if ($null -eq $received) {
        throw "Painel local nao respondeu em $StartupTimeoutSeconds segundos."
    }
    if ($received.locked -ne $true -or !$received.version) {
        throw "Estado anonimo inseguro ou resposta incompleta ao iniciar o AutoRIP."
    }
    $outputs = @(Get-ChildItem -LiteralPath $settings.output_folder -Filter "*.PRT" -File -ErrorAction SilentlyContinue)
    if ($outputs.Count -gt 0) {
        throw "Smoke test sem trabalhos gerou inesperadamente um arquivo PRT."
    }
    Write-Host "SMOKE APROVADO: instalado, SHA-256 conferente, processo iniciou e API local bloqueia detalhes sem login."
}
finally {
    if ($null -ne $app) {
        try {
            $app.Refresh()
            if (-not $app.HasExited) {
                Stop-Process -Id $app.Id -Force -ErrorAction SilentlyContinue
                $app.WaitForExit(10000) | Out-Null
            }
        }
        catch {
            Write-Warning "Nao foi possivel parar processo de smoke: $($_.Exception.Message)"
        }
    }
    $env:AUTORIP_HOME = $previousHome
    $env:AUTORIP_NOBROWSER = $previousBrowser
}
