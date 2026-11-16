# QA helper: export every slide of a .pptx to PNG using the locally installed PowerPoint.
# Usage: powershell -File tools/render_slides.ps1 -Deck .tmp/run_demo/deck.pptx [-OutDir .tmp/run_demo/render]
param([Parameter(Mandatory=$true)][string]$Deck, [string]$OutDir)
$deckPath = (Resolve-Path $Deck).Path
if (-not $OutDir) { $OutDir = Join-Path (Split-Path $deckPath) "render" }
New-Item -ItemType Directory -Force $OutDir | Out-Null
$OutDir = (Resolve-Path $OutDir).Path
Get-ChildItem $OutDir -Filter *.png -ErrorAction SilentlyContinue | Remove-Item -Force
$app = New-Object -ComObject PowerPoint.Application
try {
    $pres = $app.Presentations.Open($deckPath, $true, $false, $false)  # read-only, no window
    $i = 0
    foreach ($s in $pres.Slides) {
        $i++
        $s.Export((Join-Path $OutDir ("slide-{0:D2}.png" -f $i)), "PNG", 1600, 900)
    }
    $pres.Close()
    Write-Output "Rendered $i slides to $OutDir"
} finally {
    $app.Quit()
    [System.Runtime.InteropServices.Marshal]::ReleaseComObject($app) | Out-Null
}
