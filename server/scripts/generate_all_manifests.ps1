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
    [switch]$Reenrich,
    [switch]$SeparateSpeakers,
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

function Test-ReusableEnrichedTranscript {
    param([string]$Path)

    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        return $false
    }

    try {
        $json = Get-Content -LiteralPath $Path -Raw -Encoding UTF8 | ConvertFrom-Json
        return $json._meta -and $json._meta.reusable -eq $true
    }
    catch {
        return $false
    }
}

function Get-JsonProperty {
    param(
        [object]$Object,
        [string]$Name
    )

    if ($null -eq $Object) {
        return $null
    }

    $property = $Object.PSObject.Properties[$Name]
    if ($property) {
        return $property.Value
    }
    return $null
}

function Get-EnrichedEpisodeContext {
    param(
        [string]$Path,
        [int]$EpisodeIndex
    )

    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        return ""
    }

    try {
        $json = Get-Content -LiteralPath $Path -Raw -Encoding UTF8 | ConvertFrom-Json
        $meta = Get-JsonProperty -Object $json -Name "_meta"
        $reusable = Get-JsonProperty -Object $meta -Name "reusable"
        if ($reusable -ne $true) {
            return ""
        }

        $speakerLabels = @()
        $characters = Get-JsonProperty -Object $json -Name "characters"
        if ($characters) {
            foreach ($character in @($characters | Select-Object -First 6)) {
                $id = [string](Get-JsonProperty -Object $character -Name "id")
                $name = [string](Get-JsonProperty -Object $character -Name "name")
                $id = $id.Trim()
                $name = $name.Trim()
                if ($id -and $name) {
                    $speakerLabels += "$id=$name"
                }
                elseif ($id) {
                    $speakerLabels += $id
                }
            }
        }

        if ($speakerLabels.Count -eq 0) {
            $segments = Get-JsonProperty -Object $json -Name "segments"
            foreach ($segment in @($segments | Select-Object -First 80)) {
                $speaker = [string](Get-JsonProperty -Object $segment -Name "speaker")
                $speakerName = [string](Get-JsonProperty -Object $segment -Name "speaker_name")
                $speaker = $speaker.Trim()
                $speakerName = $speakerName.Trim()
                if ($speaker -and $speakerName) {
                    $label = "$speaker=$speakerName"
                }
                else {
                    $label = $speaker
                }
                if ($label -and -not ($speakerLabels -contains $label)) {
                    $speakerLabels += $label
                }
                if ($speakerLabels.Count -ge 6) {
                    break
                }
            }
        }

        if ($speakerLabels.Count -eq 0) {
            return ""
        }
        return "episode ${EpisodeIndex} speakers: " + ($speakerLabels -join "; ")
    }
    catch {
        return ""
    }
}

function Add-SeriesContext {
    param(
        [string]$ExistingContext,
        [string]$EpisodeContext,
        [int]$MaxChars = 1600
    )

    if (-not $EpisodeContext) {
        return $ExistingContext
    }

    $lines = @()
    if ($ExistingContext) {
        $lines += @($ExistingContext -split "\r?\n" | Where-Object { $_ })
    }
    $lines += $EpisodeContext

    while (($lines -join [Environment]::NewLine).Length -gt $MaxChars -and $lines.Count -gt 1) {
        $lines = @($lines | Select-Object -Skip 1)
    }
    return $lines -join [Environment]::NewLine
}

$serverRoot = Split-Path -Parent $PSScriptRoot
$projectRoot = Split-Path -Parent $serverRoot
$projectsRoot = Split-Path -Parent $projectRoot
$python = Join-Path $serverRoot ".venv\Scripts\python.exe"
$manifestRoot = Join-Path $serverRoot "data\manifests"
$transcriptRoot = Join-Path $serverRoot "data\transcripts"
$enrichedTranscriptRoot = Join-Path $serverRoot "data\enriched_transcripts"

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
        $sortIndex = $videos[$episodeOffset].SortIndex
        $episodeIndex = if ($sortIndex -ne [int]::MaxValue) { $sortIndex } else { $episodeOffset + 1 }
        $relativePath = Get-RelativeVideoPath -Root $DramaRoot -VideoPath $video.FullName
        $contentId = Get-ContentId -RelativePath $relativePath
        $episodes += [PSCustomObject]@{
            Drama = $drama.Name
            EpisodeIndex = $episodeIndex
            ContentId = $contentId
            RelativePath = $relativePath
            Video = $video.FullName
            Manifest = Join-Path $manifestRoot "$contentId.json"
            Transcript = Join-Path $transcriptRoot "$contentId.json"
            EnrichedTranscript = Join-Path $enrichedTranscriptRoot "$contentId.json"
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
    $episodes | Select-Object Drama, EpisodeIndex, ContentId, RelativePath, Manifest, Transcript, EnrichedTranscript | Format-Table -AutoSize
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
$env:ENRICHED_TRANSCRIPT_ROOT = $enrichedTranscriptRoot

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
$seriesContextByDrama = @{}

try {
    for ($index = 0; $index -lt $episodes.Count; $index++) {
        $episode = $episodes[$index]
        $number = $index + 1
        Write-Host "[$number/$($episodes.Count)] Content $($episode.ContentId): $($episode.Video)"

        if (-not $Force -and (Test-Path -LiteralPath $episode.Manifest -PathType Leaf)) {
            $episodeContext = if ($SeparateSpeakers) { Get-EnrichedEpisodeContext -Path $episode.EnrichedTranscript -EpisodeIndex $episode.EpisodeIndex } else { "" }
            if ($episodeContext) {
                $existingContext = if ($seriesContextByDrama.ContainsKey($episode.Drama)) { $seriesContextByDrama[$episode.Drama] } else { "" }
                $seriesContextByDrama[$episode.Drama] = Add-SeriesContext -ExistingContext $existingContext -EpisodeContext $episodeContext
                Write-Host "  Loaded speaker context from enriched transcript."
            }
            Write-Host "  Skipped: manifest already exists. Use -Force to regenerate."
            $skipCount++
            continue
        }

        $seriesContext = if ($seriesContextByDrama.ContainsKey($episode.Drama)) { $seriesContextByDrama[$episode.Drama] } else { "" }
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
        if ($SeparateSpeakers -and $seriesContext) {
            Write-Host "  Using previous speaker context for drama '$($episode.Drama)'."
            $arguments += @("--series-context", $seriesContext)
        }
        if (-not $Retranscribe -and (Test-Path -LiteralPath $episode.Transcript -PathType Leaf)) {
            Write-Host "  Reusing transcript: $($episode.Transcript)"
            $arguments += @("--transcript-json", $episode.Transcript)
        }
        if ($SeparateSpeakers) {
            $arguments += @("--separate-speakers")
        }
        if ($SeparateSpeakers -and -not $Retranscribe -and -not $Reenrich -and (Test-ReusableEnrichedTranscript -Path $episode.EnrichedTranscript)) {
            Write-Host "  Reusing enriched transcript: $($episode.EnrichedTranscript)"
            $arguments += @("--enriched-transcript-json", $episode.EnrichedTranscript)
        }
        elseif ($SeparateSpeakers -and -not $Retranscribe -and -not $Reenrich -and (Test-Path -LiteralPath $episode.EnrichedTranscript -PathType Leaf)) {
            Write-Host "  Ignoring enriched transcript without reusable model metadata: $($episode.EnrichedTranscript)"
        }

        & $python @arguments
        if ($LASTEXITCODE -eq 0) {
            $episodeContext = if ($SeparateSpeakers) { Get-EnrichedEpisodeContext -Path $episode.EnrichedTranscript -EpisodeIndex $episode.EpisodeIndex } else { "" }
            if ($episodeContext) {
                $existingContext = if ($seriesContextByDrama.ContainsKey($episode.Drama)) { $seriesContextByDrama[$episode.Drama] } else { "" }
                $seriesContextByDrama[$episode.Drama] = Add-SeriesContext -ExistingContext $existingContext -EpisodeContext $episodeContext
                Write-Host "  Updated speaker context from enriched transcript."
            }
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
