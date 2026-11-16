# Run from PowerShell after installing requirements and PyInstaller in .venv.
$ErrorActionPreference = 'Stop'
Push-Location $PSScriptRoot
try {
    & .\.venv\Scripts\python.exe -m PyInstaller --noconfirm --onefile --noupx `
        --name CommentCut --specpath build `
        --add-data "${PSScriptRoot}\static:static" --add-data "${PSScriptRoot}\capture_media.js:." `
        --add-data "${PSScriptRoot}\post_dom.js:." --add-data "${PSScriptRoot}\threads_dom.js:." `
        "$PSScriptRoot\launcher.py"
    if ($LASTEXITCODE) { exit $LASTEXITCODE }
} finally {
    Pop-Location
}
