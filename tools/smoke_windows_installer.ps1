param(
    [string]$SetupPath = "Output\AutoRIP_Setup.exe",
    [Parameter(Mandatory = $true)][string]$ExpectedVersion,
    [int]$StartupTimeoutSeconds = 90,
    [switch]$ExercisePortFallback
)

$ErrorActionPreference = "Stop"
if ($env:OS -ne "Windows_NT" -or $env:GITHUB_ACTIONS -ne "true") {
    throw "Execute este teste de instalação somente em um runner Windows descartável do GitHub Actions."
}
$repository = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$setup = (Resolve-Path (Join-Path $repository $SetupPath)).Path
$smokeRoot = Join-Path $env:RUNNER_TEMP ("AutoRIP-Install-Smoke-" + [guid]::NewGuid().ToString("N"))
$installation = Join-Path $smokeRoot "programa com espacos"
$dataHome = Join-Path $smokeRoot "dados"
New-Item -ItemType Directory -Force -Path $dataHome | Out-Null
$settings = @{
    offline_mode = $true; auto_mode = $false; auto_update = $false; label_enabled = $false
    hot_folder = (Join-Path $dataHome "entrada")
    output_folder = (Join-Path $dataHome "saida")
    done_folder = (Join-Path $dataHome "concluidos")
    error_folder = (Join-Path $dataHome "erros")
    printed_folder = (Join-Path $dataHome "impressos")
}
[System.IO.File]::WriteAllText((Join-Path $dataHome "autorip.json"),
    ($settings | ConvertTo-Json -Compress), [System.Text.UTF8Encoding]::new($false))
$previous = @{}
foreach ($name in @('AUTORIP_HOME', 'AUTORIP_NOBROWSER', 'AUTORIP_BIND_HOST', 'AUTORIP_ALLOWED_HOSTS')) {
    $previous[$name] = [Environment]::GetEnvironmentVariable($name, 'Process')
}
$app = $null
$listener = $null
try {
    $arguments = @('/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART', '/SP-', '/NOICONS',
        '/TASKS=""', ('/DIR="{0}"' -f $installation), ('/LOG="{0}"' -f (Join-Path $smokeRoot 'install.log')))
    $installed = Start-Process -FilePath $setup -ArgumentList $arguments -Wait -PassThru
    if ($installed.ExitCode -ne 0) { throw "Inno Setup retornou $($installed.ExitCode)." }
    $exe = Join-Path $installation "AutoRIP.exe"
    $compiled = Join-Path $repository "dist\AutoRIP\AutoRIP.exe"
    if ((Get-FileHash -LiteralPath $exe -Algorithm SHA256).Hash -ne
        (Get-FileHash -LiteralPath $compiled -Algorithm SHA256).Hash) {
        throw "O executável instalado difere do compilado."
    }
    $env:AUTORIP_HOME = $dataHome
    $env:AUTORIP_NOBROWSER = '1'
    $env:AUTORIP_BIND_HOST = '127.0.0.1'
    $env:AUTORIP_ALLOWED_HOSTS = '127.0.0.1,localhost'
    if ($ExercisePortFallback) {
        try {
            $listener = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Loopback, 8765)
            $listener.ExclusiveAddressUse = $true
            $listener.Start()
        } catch {
            if ($null -ne $listener) { $listener.Stop(); $listener = $null }
            Write-Host 'Porta 8765 já ocupada; o aplicativo deverá usar outra porta.'
        }
    }
    $console = Join-Path $smokeRoot 'console.log'
    $app = Start-Process -FilePath $exe -ArgumentList '--web' -WorkingDirectory $installation -PassThru `
        -RedirectStandardOutput $console -RedirectStandardError (Join-Path $smokeRoot 'stderr.log')
    $timer = [System.Diagnostics.Stopwatch]::StartNew()
    $state = $null
    $baseUrl = $null
    while ($timer.Elapsed.TotalSeconds -lt $StartupTimeoutSeconds) {
        $app.Refresh()
        if ($app.HasExited) { throw "O aplicativo instalado encerrou antes de iniciar: $($app.ExitCode)." }
        $logs = @($console, (Join-Path $dataHome 'autorip.log')) | ForEach-Object {
            if (Test-Path -LiteralPath $_) { Get-Content -LiteralPath $_ -Raw -ErrorAction SilentlyContinue }
        }
        if (($logs -join "`n") -match 'AutoRIP em (http://127\.0\.0\.1:\d+)/') {
            $baseUrl = $Matches[1]
            try {
                $state = Invoke-RestMethod -Uri "$baseUrl/api/state" -TimeoutSec 3
                break
            } catch { }
        }
        Start-Sleep -Milliseconds 500
    }
    if ($null -eq $state) { throw "O aplicativo instalado não iniciou em $StartupTimeoutSeconds segundos." }
    if ($state.locked -ne $true -or $state.version -ne $ExpectedVersion) {
        throw "Versão incorreta ou estado anônimo inseguro no aplicativo instalado."
    }
    if ($ExercisePortFallback -and ([uri]$baseUrl).Port -eq 8765) {
        throw 'A prova de fallback não utilizou outra porta.'
    }
    if (@(Get-ChildItem -LiteralPath $settings.output_folder -Filter '*.PRT' -File).Count -ne 0) {
        throw 'O teste sem trabalhos gerou um PRT inesperado.'
    }
    $password = @{new = ('Smoke-' + [guid]::NewGuid().ToString('N'))} | ConvertTo-Json -Compress
    $login = Invoke-RestMethod -Uri "$baseUrl/api/setpass" -Method Post -ContentType 'application/json' -Body $password
    Invoke-RestMethod -Uri "$baseUrl/api/shutdown" -Method Post -ContentType 'application/json' `
        -Headers @{'X-Token' = $login.token} -Body '{}' | Out-Null
    if (-not $app.WaitForExit(30000) -or $app.ExitCode -ne 0) { throw 'O aplicativo instalado não encerrou corretamente.' }
    Write-Host "SMOKE APROVADO: instalação íntegra, versão $ExpectedVersion, API protegida, porta real e encerramento."
} finally {
    if ($null -ne $listener) { $listener.Stop() }
    if ($null -ne $app) {
        try {
            $app.Refresh()
            if (-not $app.HasExited) { & taskkill.exe /PID $app.Id /T /F | Out-Null; $app.WaitForExit(10000) | Out-Null }
        } catch { Write-Warning "Limpeza do processo: $($_.Exception.Message)" }
    }
    foreach ($name in $previous.Keys) { [Environment]::SetEnvironmentVariable($name, $previous[$name], 'Process') }
    $uninstaller = Join-Path $installation 'unins000.exe'
    if (Test-Path -LiteralPath $uninstaller) {
        try {
            $removed = Start-Process -FilePath $uninstaller -ArgumentList '/VERYSILENT /SUPPRESSMSGBOXES /NORESTART' -Wait -PassThru
            if ($removed.ExitCode -ne 0) { Write-Warning "Desinstalador retornou $($removed.ExitCode)." }
        } catch { Write-Warning "Limpeza da instalação: $($_.Exception.Message)" }
    }
}
exit 0
