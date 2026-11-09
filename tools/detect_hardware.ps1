[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$OutputPath
)

$ErrorActionPreference = 'Stop'

$cpu = Get-CimInstance Win32_Processor | Select-Object -First 1
$computer = Get-CimInstance Win32_ComputerSystem
$disks = @(Get-CimInstance Win32_DiskDrive | ForEach-Object {
    [ordered]@{
        model = [string]$_.Model
        media_type = [string]$_.MediaType
        size_bytes = [int64]$_.Size
    }
})
$gpus = @(Get-CimInstance Win32_VideoController -ErrorAction SilentlyContinue | ForEach-Object {
    [string]$_.Name
})

$logical = [int]$cpu.NumberOfLogicalProcessors
$cores = [int]$cpu.NumberOfCores
$ram = [int64]$computer.TotalPhysicalMemory
$ramGiB = [math]::Round($ram / 1GB, 2)

if ($ram -ge (24GB) -and $cores -ge 6) {
    $performance = 'alto'
    $strip = 1024
    $memory = 1GB
} elseif ($ram -ge (12GB) -and $cores -ge 4) {
    $performance = 'equilibrado'
    $strip = 768
    $memory = 768MB
} else {
    $performance = 'conservador'
    $strip = 512
    $memory = 512MB
}

$profile = [ordered]@{
    schema = 1
    generated_at = (Get-Date).ToUniversalTime().ToString('o')
    cpu = [string]$cpu.Name
    physical_cores = $cores
    logical_processors = $logical
    ram_bytes = $ram
    ram_gib = $ramGiB
    performance = $performance
    strip_rows = $strip
    render_memory_bytes = $memory
    disks = $disks
    gpus = $gpus
}

$directory = Split-Path -Parent $OutputPath
New-Item -ItemType Directory -Force -Path $directory | Out-Null
$profile | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $OutputPath -Encoding UTF8
Write-Output ("AutoRIP: perfil {0}, {1} GiB RAM, {2} nucleos, {3} threads" -f $performance, $ramGiB, $cores, $logical)
