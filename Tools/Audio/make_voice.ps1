# Andrew's Airsoft - story voice-over from Content/Airsoft/Data/Campaign.json.
#
# Uses the Windows text-to-speech voices (no downloads, nothing copyrighted): a slow, low
# narrator for the mission cards and outros, and a voice per boss for their taunt.
# Writes Tools/Audio/Generated/Voice/VO_M<n>_I<k>.wav, VO_M<n>_Boss.wav, VO_M<n>_Outro.wav;
# Content/Python/airsoft_setup.py imports them as /Game/Airsoft/Audio/<name>.
#
#   powershell -ExecutionPolicy Bypass -File Tools\Audio\make_voice.ps1
param([string]$Root = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path)

$ErrorActionPreference = "Stop"
Add-Type -AssemblyName System.Speech

$data = Get-Content (Join-Path $Root "Content\Airsoft\Data\Campaign.json") -Raw | ConvertFrom-Json
$outDir = Join-Path $Root "Tools\Audio\Generated\Voice"
New-Item -ItemType Directory -Force $outDir | Out-Null

$synth = New-Object System.Speech.Synthesis.SpeechSynthesizer
$installed = @($synth.GetInstalledVoices() | Where-Object Enabled | ForEach-Object { $_.VoiceInfo.Name })
$format = New-Object System.Speech.AudioFormat.SpeechAudioFormatInfo 48000, ([System.Speech.AudioFormat.AudioBitsPerSample]::Sixteen), ([System.Speech.AudioFormat.AudioChannel]::Mono)

function Pick-Voice([string]$Wanted, [string]$Gender) {
    if ($Wanted -and $installed -contains $Wanted) { return $Wanted }
    foreach ($v in $synth.GetInstalledVoices()) {
        if ($v.Enabled -and $v.VoiceInfo.Gender.ToString() -eq $Gender) { return $v.VoiceInfo.Name }
    }
    return $installed[0]
}

function Say([string]$Text, [string]$Voice, [string]$Rate, [string]$Pitch, [string]$File) {
    $escaped = [System.Security.SecurityElement]::Escape($Text)
    $ssml = "<speak version='1.0' xmlns='http://www.w3.org/2001/10/synthesis' xml:lang='en-US'>" +
            "<voice name='$Voice'><prosody rate='$Rate' pitch='$Pitch'>$escaped</prosody></voice></speak>"
    $synth.SetOutputToWaveFile($File, $format)
    $synth.SpeakSsml($ssml)
    $synth.SetOutputToNull()
    "  {0,-22} {1}" -f (Split-Path $File -Leaf), $Text
}

$narrator = Pick-Voice $data.Narrator "Male"
"Narrator: $narrator"
$n = 0
foreach ($m in $data.Missions) {
    $n++
    for ($k = 0; $k -lt $m.Intro.Count; $k++) {
        Say $m.Intro[$k] $narrator "-15%" "low" (Join-Path $outDir ("VO_M{0}_I{1}.wav" -f $n, $k))
    }
    if ($m.Outro) {
        Say $m.Outro $narrator "-15%" "low" (Join-Path $outDir ("VO_M{0}_Outro.wav" -f $n))
    }
    if ($m.Boss -and $m.Boss.Taunt) {
        # Bosses: a different delivery from the narrator (and a female voice for Mara Voss).
        $female = $m.Boss.Name -match "Mara"
        $voice = if ($female) { Pick-Voice "" "Female" } else { $narrator }
        $pitch = if ($female) { "medium" } else { "x-low" }
        Say $m.Boss.Taunt $voice "-5%" $pitch (Join-Path $outDir ("VO_M{0}_Boss.wav" -f $n))
    }
}
$synth.Dispose()
"Done: $outDir"
