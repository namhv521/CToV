param(
    [string]$FfmpegDirectory = '',
    [switch]$SkipZip
)

$ErrorActionPreference = 'Stop'
Push-Location $PSScriptRoot
$previousBrowsers = $env:PLAYWRIGHT_BROWSERS_PATH
try {
    $python = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
    if (-not (Test-Path -LiteralPath $python)) {
        & python -m venv .venv
        if ($LASTEXITCODE) { throw 'Python 3.11+ is required on the build machine only.' }
    }
    & $python -m pip install -r requirements-build.txt
    if ($LASTEXITCODE) { throw 'Could not install build requirements.' }

    $buildDirectory = Join-Path $PSScriptRoot 'build'
    $browsers = Join-Path $buildDirectory 'browsers'
    New-Item -ItemType Directory -Force -Path $buildDirectory | Out-Null
    $env:PLAYWRIGHT_BROWSERS_PATH = $browsers
    & $python -m playwright install chromium --no-shell
    if ($LASTEXITCODE) { throw 'Could not download the bundled browser.' }

    if (-not $FfmpegDirectory) {
        $ffmpegCommand = Get-Command ffmpeg.exe -ErrorAction SilentlyContinue
        if ($ffmpegCommand) { $FfmpegDirectory = Split-Path $ffmpegCommand.Source }
    }
    if (-not $FfmpegDirectory) {
        $ffmpegArchive = Join-Path $buildDirectory 'ffmpeg-release-essentials.zip'
        $ffmpegUrl = 'https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip'
        Invoke-WebRequest -UseBasicParsing -Uri $ffmpegUrl -OutFile $ffmpegArchive
        $checksum = (Invoke-WebRequest -UseBasicParsing -Uri "$ffmpegUrl.sha256").Content
        $expected = [regex]::Match([string]$checksum, '[a-fA-F0-9]{64}').Value
        if (-not $expected -or (Get-FileHash -LiteralPath $ffmpegArchive -Algorithm SHA256).Hash -ne $expected) {
            throw 'FFmpeg download checksum mismatch.'
        }
        $ffmpegExtract = Join-Path $buildDirectory 'ffmpeg-download'
        Expand-Archive -LiteralPath $ffmpegArchive -DestinationPath $ffmpegExtract -Force
        $FfmpegDirectory = (Get-ChildItem -LiteralPath $ffmpegExtract -Recurse -Filter ffmpeg.exe | Select-Object -First 1).DirectoryName
    }
    foreach ($name in @('ffmpeg.exe', 'ffprobe.exe')) {
        if (-not (Test-Path -LiteralPath (Join-Path $FfmpegDirectory $name))) {
            throw "Missing $name in $FfmpegDirectory"
        }
    }
    $ffmpegHome = Split-Path $FfmpegDirectory
    $ffmpegLicense = Join-Path $ffmpegHome 'LICENSE'
    if (-not (Test-Path -LiteralPath $ffmpegLicense)) {
        throw 'Use the complete FFmpeg essentials distribution, including its LICENSE file.'
    }

    & $python -m PyInstaller --noconfirm --clean --onedir --windowed --noupx `
        --name CommentCut --specpath build `
        --add-data "${PSScriptRoot}\static:static" --add-data "${PSScriptRoot}\capture_media.js:." `
        --add-data "${PSScriptRoot}\post_dom.js:." --add-data "${PSScriptRoot}\threads_dom.js:." `
        --add-data "${browsers}:browsers" `
        --add-binary "${FfmpegDirectory}\ffmpeg.exe:." --add-binary "${FfmpegDirectory}\ffprobe.exe:." `
        --collect-submodules uvicorn `
        "$PSScriptRoot\launcher.py"
    if ($LASTEXITCODE) { throw 'PyInstaller failed.' }

    $release = Join-Path $PSScriptRoot 'dist\CommentCut'
    foreach ($folder in @('Vid_nen', 'vid_meme', 'img_meme', 'mp3_meme')) {
        New-Item -ItemType Directory -Force -Path (Join-Path $release "data\$folder") | Out-Null
    }
    $notices = Join-Path $release 'licenses\FFmpeg'
    New-Item -ItemType Directory -Force -Path $notices | Out-Null
    Copy-Item -LiteralPath $ffmpegLicense -Destination $notices
    foreach ($name in @('README.txt', 'doc')) {
        $noticeSource = Join-Path $ffmpegHome $name
        if (Test-Path -LiteralPath $noticeSource) { Copy-Item -LiteralPath $noticeSource -Destination $notices -Recurse -Force }
    }
    & (Join-Path $FfmpegDirectory 'ffmpeg.exe') -version | Set-Content -Encoding UTF8 (Join-Path $notices 'build-version.txt')
    @(
        'FFmpeg binaries and corresponding source/build information: https://www.gyan.dev/ffmpeg/builds/',
        'Playwright and Chromium notices are included in _internal/playwright and _internal/browsers.',
        'Font license: _internal/static/OFL.txt'
    ) | Set-Content -Encoding UTF8 (Join-Path $release 'licenses\THIRD-PARTY.txt')

    if (-not $SkipZip) {
        $archive = Join-Path $PSScriptRoot 'dist\CommentCut-Windows-x64.zip'
        Compress-Archive -LiteralPath $release -DestinationPath $archive -Force
        $hash = (Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash.ToLowerInvariant()
        "$hash  CommentCut-Windows-x64.zip" | Set-Content -Encoding ASCII "$archive.sha256"
        Write-Host "Portable ZIP: $archive"
    }
    Write-Host "Application: $release\CommentCut.exe"
} finally {
    $env:PLAYWRIGHT_BROWSERS_PATH = $previousBrowsers
    Pop-Location
}
