[CmdletBinding()]
param(
    [string]$BaseUrl = "https://ark.cn-beijing.volces.com/api/v3",
    [string]$ModelName = "doubao-seed-2-0-lite-260428",
    [string]$DramaRoot,
    [string]$FfmpegBin,
    [string]$Summary = "",
    [int]$Limit = 0,
    [switch]$UseOpenAIDefaultBaseUrl,
    [switch]$Force,
    [switch]$Retranscribe,
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

function Resolve-Executable {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Name,
        [string]$BinDirectory
    )

    if ($BinDirectory) {
        $candidate = Join-Path $BinDirectory "$Name.exe"
        if (Test-Path -LiteralPath $candidate -PathType Leaf) {
            return (Resolve-Path -LiteralPath $candidate).Path
        }
        throw "Cannot find $Name.exe in '$BinDirectory'."
    }

    $configuredPath = if ($Name -eq "ffmpeg") { $env:FFMPEG_PATH } else { $env:FFPROBE_PATH }
    if ($configuredPath -and (Test-Path -LiteralPath $configuredPath -PathType Leaf)) {
        return (Resolve-Path -LiteralPath $configuredPath).Path
    }

    $command = Get-Command $Name -ErrorAction SilentlyContinue
    if ($command) {
        return $command.Source
    }

    throw "$Name.exe was not found. Pass -FfmpegBin 'D:\path\to\ffmpeg\bin' or add FFmpeg bin to PATH."
}

function Read-ApiKey {
    $secret = Read-Host "Enter model API Key (input is hidden)" -AsSecureString
    $pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secret)
    try {
        return [Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer)
    }
    finally {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer)
    }
}

function Get-EpisodeSortIndex {
    param([string]$FileName)

    $match = [regex]::Match($FileName, '\u7b2c\s*(\d+)\s*\u96c6')
    if ($match.Success) {
        return [int]$match.Groups[1].Value
    }

    $fallback = [regex]::Match($FileName, '(\d+)')
    if ($fallback.Success) {
        return [int]$fallback.Groups[1].Value
    }

    return [int]::MaxValue
}

function Get-ContentId {
    param([string]$RelativePath)

    $sha1 = [System.Security.Cryptography.SHA1]::Create()
    try {
        $bytes = [System.Text.Encoding]::UTF8.GetBytes($RelativePath)
        $hash = $sha1.ComputeHash($bytes)
        return -join ($hash[0..7] | ForEach-Object { $_.ToString("x2") })
    }
    finally {
        $sha1.Dispose()
    }
}

function Get-RelativeVideoPath {
    param(
        [string]$Root,
        [string]$VideoPath
    )

    $relativePath = $VideoPath.Substring($Root.Length).TrimStart('\', '/')
    return $relativePath.Replace('\', '/')
}

$serverRoot = Split-Path -Parent $PSScriptRoot
$projectRoot = Split-Path -Parent $serverRoot
$projectsRoot = Split-Path -Parent $projectRoot
$python = Join-Path $serverRoot ".venv\Scripts\python.exe"
$manifestRoot = Join-Path $serverRoot "data\manifests"
$transcriptRoot = Join-Path $serverRoot "data\transcripts"

if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
    throw "Python virtual environment not found at '$python'. Create server\.venv and install requirements first."
}

if (-not $DramaRoot) {
    $DramaRoot = Join-Path $projectsRoot "drama"
}
$DramaRoot = (Resolve-Path -LiteralPath $DramaRoot).Path

$env:LOCAL_DRAMA_ROOT = $DramaRoot

$videoExtensions = @(".mp4", ".mov", ".mkv", ".avi")
$dramaDirectories = @(Get-ChildItem -LiteralPath $DramaRoot -Directory | Sort-Object Name)
$episodes = @()

for ($dramaOffset = 0; $dramaOffset -lt $dramaDirectories.Count; $dramaOffset++) {
    $drama = $dramaDirectories[$dramaOffset]
    $videos = @(
        Get-ChildItem -LiteralPath $drama.FullName -File |
            Where-Object { $videoExtensions -contains $_.Extension.ToLowerInvariant() } |
            ForEach-Object {
                [PSCustomObject]@{
                    File = $_
                    SortIndex = Get-EpisodeSortIndex -FileName $_.Name
                }
            } |
            Sort-Object SortIndex, @{ Expression = { $_.File.Name } }
    )

    for ($episodeOffset = 0; $episodeOffset -lt $videos.Count; $episodeOffset++) {
        $video = $videos[$episodeOffset].File
        $relativePath = Get-RelativeVideoPath -Root $DramaRoot -VideoPath $video.FullName
        $contentId = Get-ContentId -RelativePath $relativePath
        $episodes += [PSCustomObject]@{
            Drama = $drama.Name
            ContentId = $contentId
            RelativePath = $relativePath
            Video = $video.FullName
            Manifest = Join-Path $manifestRoot "$contentId.json"
            Transcript = Join-Path $transcriptRoot "$contentId.json"
        }
    }
}

if ($Limit -gt 0) {
    $episodes = @($episodes | Select-Object -First $Limit)
}

if ($episodes.Count -eq 0) {
    throw "No video files found under '$DramaRoot'."
}

Write-Host ""
Write-Host "Drama root: $DramaRoot"
Write-Host "Episodes selected: $($episodes.Count)"
Write-Host ""

if ($DryRun) {
    $episodes | Select-Object Drama, ContentId, RelativePath, Manifest | Format-Table -AutoSize
    Write-Host "Dry run completed. No API calls were made."
    exit 0
}

$ffmpeg = Resolve-Executable -Name "ffmpeg" -BinDirectory $FfmpegBin
$ffprobe = Resolve-Executable -Name "ffprobe" -BinDirectory $FfmpegBin
$env:FFMPEG_PATH = $ffmpeg
$env:FFPROBE_PATH = $ffprobe

if (-not $ModelName) {
    throw "Provide -ModelName."
}

if ($UseOpenAIDefaultBaseUrl) {
    Remove-Item Env:MODEL_BASE_URL -ErrorAction SilentlyContinue
}
elseif ($BaseUrl) {
    $env:MODEL_BASE_URL = $BaseUrl
}
else {
    Remove-Item Env:MODEL_BASE_URL -ErrorAction SilentlyContinue
}
$env:MODEL_NAME = $ModelName
$env:MODEL_AUDIO_NAME = $ModelName
$env:MODEL_API_KEY = Read-ApiKey

Remove-Item Env:ASR_BASE_URL -ErrorAction SilentlyContinue
Remove-Item Env:ASR_API_KEY -ErrorAction SilentlyContinue
Remove-Item Env:ASR_MODEL -ErrorAction SilentlyContinue

Write-Host "FFmpeg: $ffmpeg"
Write-Host "FFprobe: $ffprobe"
$modelBaseUrlLabel = if ($UseOpenAIDefaultBaseUrl) { "<OpenAI default>" } elseif ($BaseUrl) { $BaseUrl } else { "<OpenAI default>" }
Write-Host "Model base URL: $modelBaseUrlLabel"
Write-Host "Model: $ModelName"
Write-Host ""

$successCount = 0
$skipCount = 0
$failureCount = 0

try {
    for ($index = 0; $index -lt $episodes.Count; $index++) {
        $episode = $episodes[$index]
        $number = $index + 1
        Write-Host "[$number/$($episodes.Count)] Content $($episode.ContentId): $($episode.Video)"

        if (-not $Force -and (Test-Path -LiteralPath $episode.Manifest -PathType Leaf)) {
            Write-Host "  Skipped: manifest already exists. Use -Force to regenerate."
            $skipCount++
            continue
        }

        $arguments = @(
            "-m",
            "app.scripts.generate_episode_manifest",
            $episode.Video,
            "--local-drama-root",
            $DramaRoot
        )
        if ($Summary) {
            $arguments += @("--summary", $Summary)
        }
        if (-not $Retranscribe -and (Test-Path -LiteralPath $episode.Transcript -PathType Leaf)) {
            Write-Host "  Reusing transcript: $($episode.Transcript)"
            $arguments += @("--transcript-json", $episode.Transcript)
        }

        & $python @arguments
        if ($LASTEXITCODE -eq 0) {
            $successCount++
        }
        else {
            Write-Warning "Generation failed for content $($episode.ContentId). Continuing with the next episode."
            $failureCount++
        }
    }
}
finally {
    Remove-Item Env:MODEL_API_KEY -ErrorAction SilentlyContinue
}

Write-Host ""
Write-Host "Batch generation completed."
Write-Host "Generated: $successCount"
Write-Host "Skipped:   $skipCount"
Write-Host "Failed:    $failureCount"

if ($failureCount -gt 0) {
    exit 1
}
