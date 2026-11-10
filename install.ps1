# oxDesktop Windows Native Installer
# Usage:
#   irm https://raw.githubusercontent.com/nanodevmc/oxDesktop/main/install.ps1 | iex

param(
    [switch]$Portable,
    [string]$Prefix = "",
    [switch]$Quiet
)

$ErrorActionPreference = 'Stop'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12 -bor [Net.SecurityProtocolType]::Tls13

$isRu = [System.Globalization.CultureInfo]::CurrentUICulture.Name.StartsWith("ru")

function Write-Step($ruText, $enText) {
    if (-not $Quiet) {
        $msg = if ($isRu) { $ruText } else { $enText }
        Write-Host "  `e[32m✔`e[0m $msg"
    }
}

function Write-Title($ruText, $enText) {
    if (-not $Quiet) {
        $msg = if ($isRu) { $ruText } else { $enText }
        Write-Host "`e[38;2;224;58;27m✦`e[0m `e[1m$msg`e[0m"
    }
}

Write-Title "Установщик oxDesktop" "oxDesktop Installer"
Write-Step "Определено: Windows x64" "Detected: Windows x64"

$repo = "nanodevmc/oxDesktop"
$apiUrl = "https://api.github.com/repos/$repo/releases/latest"

Write-Step "Поиск последнего релиза на GitHub..." "Checking latest release on GitHub..."
$headers = @{ "User-Agent" = "oxDesktop-Installer" }
$release = Invoke-RestMethod -Uri $apiUrl -Headers $headers

$pattern = if ($Portable) { "oxDesktop-portable-x64\..*\.zip" } else { "oxDesktop-setup-x64\..*\.exe" }
$asset = $release.assets | Where-Object { $_.name -match $pattern } | Select-Object -First 1

if (-not $asset) {
    # Fallback to any installer or zip
    $asset = $release.assets | Where-Object { $_.name -match "(installer|setup|windows)" } | Select-Object -First 1
}

if (-not $asset) {
    Write-Error "Файл релиза не найден на GitHub / Release asset not found on GitHub."
    exit 1
}

$tempDir = [System.IO.Path]::Combine([System.IO.Path]::GetTempPath(), [System.Guid]::NewGuid().ToString())
New-Item -ItemType Directory -Path $tempDir -Force | Out-Null

try {
    $outPath = Join-Path $tempDir $asset.name
    Write-Step "Загрузка $($asset.name)..." "Downloading $($asset.name)..."
    Invoke-WebRequest -Uri $asset.browser_download_url -OutFile $outPath -UseBasicParsing

    if ($Portable) {
        $targetDir = if ($Prefix) { $Prefix } else { Join-Path $env:LOCALAPPDATA "oxDesktop" }
        Write-Step "Распаковка в $targetDir..." "Extracting to $targetDir..."
        if (Test-Path $targetDir) { Remove-Item -Recurse -Force $targetDir }
        Expand-Archive -Path $outPath -DestinationPath $targetDir -Force
        Write-Step "Готово! Запуск: $targetDir\oxDesktop.exe" "Ready! Launch: $targetDir\oxDesktop.exe"
    } else {
        Write-Step "Запуск тихого установщика Windows..." "Launching Windows silent installer..."
        $proc = Start-Process -FilePath $outPath -ArgumentList "/SILENT", "/NORESTART", "/SP-" -Wait -PassThru
        if ($proc.ExitCode -eq 0) {
            Write-Step "Установка oxDesktop успешно завершена!" "oxDesktop installation successfully completed!"
        } else {
            Write-Host "  `e[33m⚠`e[0m Код завершения установщика: $($proc.ExitCode)"
        }
    }
} finally {
    if (Test-Path $tempDir) {
        Remove-Item -Recurse -Force $tempDir -ErrorAction SilentlyContinue
    }
}
