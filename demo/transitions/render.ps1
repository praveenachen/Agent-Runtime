$ErrorActionPreference = "Stop"

$transitionDir = $PSScriptRoot
$manifestPath = Join-Path $transitionDir "manifest.json"
$regularFont = "C:\Windows\Fonts\segoeui.ttf"
$boldFont = "C:\Windows\Fonts\segoeuib.ttf"
$ffmpegImage = "jrottenberg/ffmpeg:7.1-alpine"

if (-not (Test-Path -LiteralPath $regularFont) -or -not (Test-Path -LiteralPath $boldFont)) {
    throw "Required Segoe UI fonts were not found in C:\Windows\Fonts."
}

function Escape-DrawText([string]$value) {
    return $value.Replace("\", "\\").Replace(":", "\:").Replace("'", "\'")
}

function New-TypewriterFilters([string]$title) {
    $filters = [System.Collections.Generic.List[string]]::new()
    $step = 0.052
    $startAt = 0.72

    for ($index = 1; $index -le $title.Length; $index++) {
        $prefix = Escape-DrawText $title.Substring(0, $index)
        $start = $startAt + (($index - 1) * $step)
        $end = $start + $step
        $startText = $start.ToString("0.000", [Globalization.CultureInfo]::InvariantCulture)
        $endText = $end.ToString("0.000", [Globalization.CultureInfo]::InvariantCulture)
        $filters.Add("drawtext=fontfile=/fonts/bold.ttf:text='$prefix':fontcolor=0xf4f7ff:fontsize=82:x=(w-text_w)/2:y=452:enable='between(t\,$startText\,$endText)'" )
    }

    $completeAt = $startAt + ($title.Length * $step)
    $completeText = $completeAt.ToString("0.000", [Globalization.CultureInfo]::InvariantCulture)
    $escapedTitle = Escape-DrawText $title
    $filters.Add("drawtext=fontfile=/fonts/bold.ttf:text='$escapedTitle':fontcolor=0xf4f7ff:fontsize=82:x=(w-text_w)/2:y=452:enable='gte(t\,$completeText)'" )
    return $filters
}

$clips = Get-Content -LiteralPath $manifestPath -Raw -Encoding UTF8 | ConvertFrom-Json
$clipNumber = 0

foreach ($clip in $clips) {
    $clipNumber++
    $eyebrow = Escape-DrawText ([string]$clip.eyebrow)
    $subtitle = Escape-DrawText ([string]$clip.subtitle)
    $number = $clipNumber.ToString("00")

    $filters = [System.Collections.Generic.List[string]]::new()
    $filters.Add("format=yuv420p")
    $filters.Add("drawgrid=w=120:h=120:t=1:c=0x314363@0.16")
    $filters.Add("drawbox=x=150:y=140:w=1620:h=800:color=0x101a2c@0.96:t=fill")
    $filters.Add("drawbox=x=150:y=140:w=1620:h=800:color=0x263858@1.0:t=2")
    $filters.Add("drawbox=x=150:y=140:w=8:h=800:color=0x5967f2@1.0:t=fill")
    $filters.Add("drawbox=x=158:y=140:w=5:h=800:color=0x22d3ee@0.78:t=fill")
    $filters.Add("drawbox=x=212:y=214:w=68:h=68:color=0x1b2d4c@1.0:t=fill")
    $filters.Add("drawbox=x=212:y=214:w=68:h=68:color=0x45669b@1.0:t=2")
    $filters.Add("drawtext=fontfile=/fonts/regular.ttf:text='>_':fontcolor=0x8db9ff:fontsize=32:x=228:y=230")
    $filters.Add("drawtext=fontfile=/fonts/bold.ttf:text='$eyebrow':fontcolor=0x91a8cc:fontsize=25:x=310:y=228")
    $filters.Add("drawbox=x=760:y=392:w=400:h=3:color=0x6172f3@0.95:t=fill")
    $filters.Add("drawbox=x=930:y=392:w=230:h=3:color=0x22d3ee@0.80:t=fill")
    foreach ($typeFilter in (New-TypewriterFilters ([string]$clip.title))) {
        $filters.Add($typeFilter)
    }
    $filters.Add("drawtext=fontfile=/fonts/regular.ttf:text='$subtitle':fontcolor=0xa8b9d3:fontsize=34:x=(w-text_w)/2:y=590:enable='gte(t\,1.75)'" )
    $filters.Add("drawtext=fontfile=/fonts/bold.ttf:text='DEMO $number':fontcolor=0x6fe7d4:fontsize=22:x=1580-text_w:y=838")
    $filters.Add("drawbox=x=1588:y=849:w=12:h=12:color=0x44d8bd@1.0:t=fill")
    $filters.Add("fade=t=in:st=0:d=0.35")
    $filters.Add("fade=t=out:st=3.55:d=0.45")
    $filterGraph = $filters -join ","

    $dockerArgs = @(
        "run", "--rm",
        "-v", "${transitionDir}:/output",
        "-v", "${regularFont}:/fonts/regular.ttf:ro",
        "-v", "${boldFont}:/fonts/bold.ttf:ro",
        $ffmpegImage,
        "-hide_banner", "-loglevel", "error", "-y",
        "-f", "lavfi", "-i", "color=c=0x080f1d:s=1920x1080:r=30:d=4",
        "-vf", $filterGraph,
        "-an", "-c:v", "libx264", "-preset", "medium", "-crf", "18",
        "-pix_fmt", "yuv420p", "-movflags", "+faststart",
        "/output/$($clip.file)"
    )

    Write-Host "Rendering $($clip.file)..."
    & docker @dockerArgs
    if ($LASTEXITCODE -ne 0) {
        throw "FFmpeg failed while rendering $($clip.file)."
    }
}

Write-Host "Rendered $($clips.Count) transition clips to $transitionDir"
