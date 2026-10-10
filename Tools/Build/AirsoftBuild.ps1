<#
Andrew's Airsoft - first-build helper (Windows PowerShell 5.1 or later).

Run it through Airsoft.bat in the project root (double-click), or directly:

    powershell -ExecutionPolicy Bypass -File Tools\Build\AirsoftBuild.ps1 <action>

Actions:
    menu      interactive menu (default)
    check     check this PC: Unreal 5.8, Visual Studio C++, Windows SDK, disk, GPU, art, Tailscale
    files     generate Visual Studio project files (AndrewsAirsoft.sln)
    build     compile the game code (AndrewsAirsoftEditor, Win64 Development)
    setup     open the editor and run Content/Python/airsoft_setup.py (imports art and audio, builds the maps)
    editor    open the project in the Unreal editor
    package   package a Shipping build for friends into Packaged\ (and zip it)
    all       check, build, then setup

Every action writes a report to Saved\BuildReport\latest.txt. When something fails the report is opened in
Notepad and copied to the clipboard: paste it to Claude and the fix comes back. Paths in the report are
shortened to <project>, <engine> and <user> so it doesn't carry your Windows user name.

Override the engine location with the environment variable AIRSOFT_UE_ROOT (the folder that contains Engine\).
#>

param(
    [string]$Action = "menu",
    [string]$SetupArgs = ""
)

# Continue, not Stop: Windows PowerShell 5.1 turns any stderr line of a native tool (Build.bat, git, tailscale)
# into a terminating error under Stop.
$ErrorActionPreference = "Continue"
Set-StrictMode -Version 2

$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$ProjectFile = Join-Path $ProjectRoot "AndrewsAirsoft.uproject"
$ReportDir = Join-Path $ProjectRoot "Saved\BuildReport"
$script:Stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$script:Report = New-Object System.Collections.Generic.List[string]
$script:Failed = $false
$script:EngineRoot = $null

# ------------------------------------------------------------------------------------------ output

function Say([string]$Text, [string]$Color = "Gray") {
    Write-Host $Text -ForegroundColor $Color
    $script:Report.Add($Text)
}
function Ok([string]$Text) { Say ("  [ OK ] " + $Text) "Green" }
function Warn([string]$Text) { Say ("  [WARN] " + $Text) "Yellow" }
function Bad([string]$Text) { Say ("  [FAIL] " + $Text) "Red"; $script:Failed = $true }
function Head([string]$Text) { Say ""; Say ("== " + $Text + " ==") "Cyan" }

function Scrub([string]$Text) {
    if (-not $Text) { return $Text }
    $t = $Text.Replace($ProjectRoot, "<project>")
    if ($script:EngineRoot) { $t = $t.Replace($script:EngineRoot, "<engine>") }
    if ($env:USERPROFILE) { $t = $t.Replace($env:USERPROFILE, "<user>") }
    if ($env:USERNAME) { $t = $t -replace ([regex]::Escape("\" + $env:USERNAME + "\")), "\<user>\" }
    return $t
}

function Save-Report([string]$Name) {
    New-Item -ItemType Directory -Force -Path $ReportDir | Out-Null
    $header = @(
        "Andrew's Airsoft build report",
        ("Action: " + $Name + "   Result: " + $(if ($script:Failed) { "FAILED" } else { "OK" })),
        ("Time: " + (Get-Date -Format "yyyy-MM-dd HH:mm:ss")),
        ("Git: " + (Get-GitDescription)),
        ""
    )
    $text = ($header + $script:Report.ToArray()) | ForEach-Object { Scrub $_ }
    $file = Join-Path $ReportDir ($Name + "-" + $script:Stamp + ".txt")
    $latest = Join-Path $ReportDir "latest.txt"
    Set-Content -Path $file -Value $text -Encoding UTF8
    Set-Content -Path $latest -Value $text -Encoding UTF8
    Write-Host ""
    Write-Host ("Report: " + $latest) -ForegroundColor Cyan
    if ($script:Failed) {
        try {
            Set-Clipboard -Value ($text -join "`r`n")
            Write-Host "The report is on your clipboard. Paste it to Claude to get the fix." -ForegroundColor Yellow
        } catch {
            Write-Host "Open the report above and paste its contents to Claude to get the fix." -ForegroundColor Yellow
        }
        try { Start-Process notepad.exe $latest | Out-Null } catch { }
    }
}

function Get-GitDescription {
    try {
        $git = Get-Command git -ErrorAction SilentlyContinue
        if (-not $git) { return "git not installed" }
        Push-Location $ProjectRoot
        try {
            $branch = (& git rev-parse --abbrev-ref HEAD 2>$null)
            $sha = (& git rev-parse --short HEAD 2>$null)
            $dirty = (& git status --porcelain 2>$null | Measure-Object).Count
            return ("{0} @ {1}{2}" -f $branch, $sha, $(if ($dirty -gt 0) { " (+$dirty local changes)" } else { "" }))
        } finally { Pop-Location }
    } catch { return "unknown" }
}

# Runs a native tool, shows its output live and keeps a copy in $Log. Returns the exit code.
function Invoke-Logged([string]$Exe, [string[]]$Arguments, [string]$Log) {
    New-Item -ItemType Directory -Force -Path (Split-Path $Log) | Out-Null
    & $Exe @Arguments 2>&1 | ForEach-Object { "$_" } | Tee-Object -FilePath $Log | Out-Host
    return $LASTEXITCODE
}

# ------------------------------------------------------------------------------------------ discovery

function Get-EngineVersion {
    $json = Get-Content -Raw -Path $ProjectFile | ConvertFrom-Json
    return [string]$json.EngineAssociation
}

function Find-Engine {
    $version = Get-EngineVersion
    $candidates = New-Object System.Collections.Generic.List[string]
    if ($env:AIRSOFT_UE_ROOT) { $candidates.Add($env:AIRSOFT_UE_ROOT) }
    foreach ($key in @("HKLM:\SOFTWARE\EpicGames\Unreal Engine\$version", "HKLM:\SOFTWARE\WOW6432Node\EpicGames\Unreal Engine\$version")) {
        try {
            $dir = (Get-ItemProperty -Path $key -ErrorAction Stop).InstalledDirectory
            if ($dir) { $candidates.Add($dir) }
        } catch { }
    }
    $launcherDat = Join-Path $env:ProgramData "Epic\UnrealEngineLauncher\LauncherInstalled.dat"
    if (Test-Path $launcherDat) {
        try {
            $list = (Get-Content -Raw $launcherDat | ConvertFrom-Json).InstallationList
            foreach ($entry in $list) {
                if ($entry.AppName -eq ("UE_" + $version)) { $candidates.Add($entry.InstallLocation) }
            }
        } catch { }
    }
    foreach ($drive in @($env:ProgramFiles, "C:\Program Files", "D:\Program Files", "D:\Epic Games", "E:\Epic Games")) {
        if ($drive) { $candidates.Add((Join-Path $drive ("Epic Games\UE_" + $version))); $candidates.Add((Join-Path $drive ("UE_" + $version))) }
    }
    foreach ($c in $candidates) {
        if ($c -and (Test-Path (Join-Path $c "Engine\Binaries\Win64\UnrealEditor.exe"))) {
            return (Resolve-Path $c).Path.TrimEnd("\")
        }
    }
    return $null
}

function Require-Engine {
    if (-not $script:EngineRoot) { $script:EngineRoot = Find-Engine }
    if (-not $script:EngineRoot) {
        Bad ("Unreal Engine " + (Get-EngineVersion) + " was not found. Install it from the Epic Games Launcher, or set AIRSOFT_UE_ROOT to the folder that contains Engine\.")
        return $false
    }
    return $true
}

function Find-VisualStudio {
    $vswhere = Join-Path ${env:ProgramFiles(x86)} "Microsoft Visual Studio\Installer\vswhere.exe"
    if (-not (Test-Path $vswhere)) { return $null }
    $path = & $vswhere -latest -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath 2>$null
    if (-not $path) { return $null }
    $ver = & $vswhere -latest -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property catalog_productDisplayVersion 2>$null
    $name = & $vswhere -latest -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property displayName 2>$null
    $game = & $vswhere -latest -products * -requires Microsoft.VisualStudio.Workload.NativeGame -property installationPath 2>$null
    return [pscustomobject]@{ Path = $path; Version = $ver; Name = $name; GameWorkload = [bool]$game }
}

# ------------------------------------------------------------------------------------------ actions

function Invoke-Check {
    Head "Checking this PC"
    $version = Get-EngineVersion
    if (Require-Engine) {
        $build = Join-Path $script:EngineRoot "Engine\Build\Build.version"
        $patch = ""
        if (Test-Path $build) {
            $b = Get-Content -Raw $build | ConvertFrom-Json
            $patch = "{0}.{1}.{2}" -f $b.MajorVersion, $b.MinorVersion, $b.PatchVersion
        }
        Ok ("Unreal Engine " + $(if ($patch) { $patch } else { $version }) + " at " + $script:EngineRoot)
    }

    $vs = Find-VisualStudio
    if ($vs) {
        Ok ($vs.Name + " " + $vs.Version + " with the C++ compiler")
        if (-not $vs.GameWorkload) { Warn "The 'Game development with C++' workload isn't installed. Add it in the Visual Studio Installer (include the Unreal Engine installer component)." }
    } else {
        Bad "Visual Studio 2022 with C++ wasn't found. Install Visual Studio 2022 Community with 'Game development with C++' and 'Desktop development with C++'."
    }

    $kits = Join-Path ${env:ProgramFiles(x86)} "Windows Kits\10\Include"
    $sdks = @()
    if (Test-Path $kits) { $sdks = @(Get-ChildItem $kits -Directory | Where-Object { $_.Name -match '^10\.0\.\d+\.\d+$' } | Sort-Object Name) }
    if ($sdks.Count -gt 0) { Ok ("Windows SDK " + $sdks[-1].Name) } else { Bad "No Windows 10/11 SDK found. Add the latest Windows 11 SDK in the Visual Studio Installer." }

    try {
        $drive = (Get-Item $ProjectRoot).PSDrive
        $freeGB = [math]::Round($drive.Free / 1GB)
        if ($freeGB -lt 40) { Bad ("Only $freeGB GB free on drive " + $drive.Name + ": the build, imported 4K art and shader cache need about 60 GB.") }
        elseif ($freeGB -lt 80) { Warn ("$freeGB GB free on drive " + $drive.Name + ". Packaging needs more; 80 GB+ is comfortable.") }
        else { Ok ("$freeGB GB free on drive " + $drive.Name) }
    } catch { Warn "Couldn't read free disk space." }

    try {
        $gpus = @(Get-CimInstance Win32_VideoController | ForEach-Object { $_.Name + " (driver " + $_.DriverVersion + ")" })
        foreach ($g in $gpus) { Ok ("GPU: " + $g) }
        $ramGB = [math]::Round((Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory / 1GB)
        if ($ramGB -lt 16) { Warn "$ramGB GB RAM. Unreal works best with 32 GB; close other programs while building." } else { Ok "$ramGB GB RAM" }
    } catch { Warn "Couldn't read GPU / RAM info." }

    $art = @("Weapons", "Props", "Architecture", "Materials") | Where-Object { -not (Test-Path (Join-Path $ProjectRoot "SourceAssets\$_")) }
    if ($art.Count -eq 0) { Ok "4K art is in SourceAssets\" }
    else {
        Warn ("4K art is missing (" + ($art -join ", ") + "). The game still runs with stand-in shapes. To get it, run in the project folder:")
        Say  "         git fetch origin art"
        Say  "         git checkout FETCH_HEAD -- SourceAssets"
        Say  "         git reset -q SourceAssets"
    }
    $audio = @(Get-ChildItem (Join-Path $ProjectRoot "Tools\Audio\Generated") -Filter *.wav -ErrorAction SilentlyContinue).Count
    if ($audio -gt 0) { Ok "$audio sound files in Tools\Audio\Generated" } else { Warn "No sounds in Tools\Audio\Generated (run: python Tools\Audio\make_sounds.py)." }

    if (Test-Path (Join-Path $ProjectRoot "Content\Characters\Mannequins")) { Ok "Third Person content pack is installed (player bodies)" }
    else { Warn "Third Person content pack not added yet: other players will be grey stand-ins. In the editor: Content Drawer > Add > Add Feature or Content Pack > Third Person." }

    $ts = Get-Command tailscale.exe -ErrorAction SilentlyContinue
    if (-not $ts -and (Test-Path "$env:ProgramFiles\Tailscale\tailscale.exe")) { $ts = Get-Item "$env:ProgramFiles\Tailscale\tailscale.exe" }
    if ($ts) {
        $exe = if ($ts -is [System.Management.Automation.CommandInfo]) { $ts.Source } else { $ts.FullName }
        $ip = (& $exe ip -4 2>$null | Select-Object -First 1)
        if ($ip) { Ok ("Tailscale is connected: this PC is " + $ip + " (friends type this to join when you host)") }
        else { Warn "Tailscale is installed but not connected. Open Tailscale and sign in." }
    } else { Warn "Tailscale isn't installed. Only needed for playing over the internet (tailscale.com)." }

    $binaries = Join-Path $ProjectRoot "Binaries\Win64\UnrealEditor-AndrewsAirsoft.dll"
    if (Test-Path $binaries) { Ok ("Game code was last built " + (Get-Item $binaries).LastWriteTime.ToString("yyyy-MM-dd HH:mm")) }
    else { Say "  [INFO] The game code hasn't been built yet (choose Build)." }
    if (Test-Path (Join-Path $ProjectRoot "Content\Maps\L_Staging.umap")) { Ok "Maps have been built" }
    else { Say "  [INFO] The maps haven't been built yet (choose Setup after Build)." }
}

function Invoke-ProjectFiles {
    Head "Generating Visual Studio project files"
    if (-not (Require-Engine)) { return }
    $ubt = Join-Path $script:EngineRoot "Engine\Binaries\DotNET\UnrealBuildTool\UnrealBuildTool.exe"
    if (-not (Test-Path $ubt)) { Bad "UnrealBuildTool.exe wasn't found in the engine folder."; return }
    $log = Join-Path $ReportDir ("files-" + $script:Stamp + ".log")
    $code = Invoke-Logged $ubt @("-projectfiles", ("-project=" + $ProjectFile), "-game", "-rocket", "-progress") $log
    if ($code -ne 0) { Bad "Generating project files failed (exit $code)."; Add-ErrorLines $log }
    else { Ok "AndrewsAirsoft.sln is ready (open it in Visual Studio if you want to read or debug the code)." }
}

function Add-ErrorLines([string]$LogPath, [int]$Max = 120) {
    if (-not (Test-Path $LogPath)) { return }
    $lines = Get-Content $LogPath
    $pattern = '(\berror\b\s*[A-Z]{1,4}\d{3,5}|fatal error|: error\b|\bError:|error LNK|ERROR:|UnrealHeaderTool failed|Unable to build while Live Coding)'
    $picked = New-Object System.Collections.Generic.List[string]
    $seen = @{}
    for ($i = 0; $i -lt $lines.Count; $i++) {
        $l = $lines[$i]
        if ($l -match $pattern -and -not $seen.ContainsKey($l)) {
            $seen[$l] = $true
            $picked.Add($l.Trim())
            # keep the compiler's follow-up notes (template instantiation context, "see declaration of")
            for ($j = $i + 1; $j -lt [math]::Min($i + 4, $lines.Count); $j++) {
                if ($lines[$j] -match '(: note:|see declaration|see reference|while compiling|with \[)') { $picked.Add("      " + $lines[$j].Trim()) } else { break }
            }
        }
        if ($picked.Count -ge $Max) { break }
    }
    if ($picked.Count -eq 0) {
        Say "  No compiler error lines were found. Last 60 lines of the log:"
        $lines | Select-Object -Last 60 | ForEach-Object { Say ("    " + $_) }
    } else {
        Say ("  Errors (" + $picked.Count + " lines" + $(if ($picked.Count -ge $Max) { ", first $Max" } else { "" }) + "):")
        foreach ($p in $picked) { Say ("    " + $p) }
    }
    Say ("  Full log: " + $LogPath)
}

function Invoke-Build {
    Head "Building the game code (AndrewsAirsoftEditor, Win64 Development)"
    if (-not (Require-Engine)) { return }
    if (Get-Process -Name UnrealEditor -ErrorAction SilentlyContinue) {
        Warn "The Unreal editor is open. Close it first, or the build can't replace the game code (Live Coding blocks it)."
    }
    $bat = Join-Path $script:EngineRoot "Engine\Build\BatchFiles\Build.bat"
    $log = Join-Path $ReportDir ("build-" + $script:Stamp + ".log")
    $start = Get-Date
    $code = Invoke-Logged $bat @("AndrewsAirsoftEditor", "Win64", "Development", ("-Project=" + $ProjectFile), "-WaitMutex") $log
    $mins = [math]::Round(((Get-Date) - $start).TotalMinutes, 1)
    if ($code -ne 0) {
        Bad ("The build failed after $mins min (exit $code).")
        Add-ErrorLines $log
    } else {
        $warnings = @(Select-String -Path $log -Pattern 'warning [A-Z]+\d+' -ErrorAction SilentlyContinue).Count
        Ok ("Built in $mins min" + $(if ($warnings -gt 0) { " ($warnings compiler warnings, harmless unless something misbehaves)" } else { "" }))
    }
}

function Invoke-Setup {
    Head "Building the game content (airsoft_setup.py)"
    if (-not (Require-Engine)) { return }
    if (-not (Test-Path (Join-Path $ProjectRoot "Binaries\Win64\UnrealEditor-AndrewsAirsoft.dll"))) {
        Bad "Build the game code first (the setup script needs the game's classes)."
        return
    }
    $editor = Join-Path $script:EngineRoot "Engine\Binaries\Win64\UnrealEditor.exe"
    # Content\Python is on the editor's Python path, so the script is run by name (no path that could hold spaces).
    $pyCommand = ("airsoft_setup.py --quit " + $SetupArgs).Trim()
    $logFile = Join-Path $ProjectRoot "Saved\Logs\AndrewsAirsoft.log"
    Say "  The editor opens, imports the art and sound, builds all maps, then closes by itself."
    Say "  The first run takes a long time (often 30-90 minutes: shaders compile and 4K textures import)."
    $start = Get-Date
    $proc = Start-Process -FilePath $editor -ArgumentList @(('"' + $ProjectFile + '"'), ('-ExecutePythonScript="' + $pyCommand + '"'), "-log") -PassThru
    $proc.WaitForExit()   # only the editor itself; Start-Process -Wait would also wait for shader workers it leaves behind
    $mins = [math]::Round(((Get-Date) - $start).TotalMinutes, 1)
    if (-not (Test-Path $logFile)) { Bad "The editor log wasn't found (Saved\Logs\AndrewsAirsoft.log)."; return }
    $log = Get-Content $logFile
    $summaryStart = -1
    for ($i = 0; $i -lt $log.Count; $i++) { if ($log[$i] -match '\[AirsoftSetup\] Andrew.s Airsoft setup - ') { $summaryStart = $i } }
    if ($summaryStart -lt 0) {
        Bad ("The setup script didn't start (editor exit code " + $proc.ExitCode + ", $mins min). Is the Python Editor Script Plugin enabled?")
        $log | Where-Object { $_ -match '(Error|Fatal|Python)' } | Select-Object -Last 60 | ForEach-Object { Say ("    " + $_) }
        return
    }
    $run = $log[$summaryStart..($log.Count - 1)]
    $errors = @($run | Where-Object { $_ -match '(LogPython: Error|Traceback \(most recent|setup aborted)' })
    $warns = @($run | Where-Object { $_ -match 'LogPython: Warning: \[AirsoftSetup\]' })
    $summary = @($run | Where-Object { $_ -match '\[AirsoftSetup\] ' } | Select-Object -Last 60)
    $finished = @($run | Where-Object { $_ -match 'setup summary' }).Count -gt 0
    if ($errors.Count -gt 0 -or -not $finished) {
        Bad ("The setup script " + $(if ($finished) { "reported " + $errors.Count + " error line(s)" } else { "stopped before finishing (editor exit code " + $proc.ExitCode + ")" }) + " after $mins min.")
        $errors | Select-Object -First 120 | ForEach-Object { Say ("    " + $_) }
        Say "  Script output (last 60 lines):"
        $summary | ForEach-Object { Say ("    " + $_) }
    } else {
        Ok ("Content built in $mins min" + $(if ($warns.Count -gt 0) { " (" + $warns.Count + " warnings, listed below; usually harmless)" } else { "" }))
        $warns | Select-Object -First 60 | ForEach-Object { Say ("    " + $_) }
        Say "  Summary:"
        $summary | Where-Object { $_ -notmatch 'LogPython: Warning' } | ForEach-Object { Say ("    " + $_) }
    }
}

function Invoke-Editor {
    Head "Opening the editor"
    if (-not (Require-Engine)) { return }
    $editor = Join-Path $script:EngineRoot "Engine\Binaries\Win64\UnrealEditor.exe"
    Start-Process -FilePath $editor -ArgumentList @(('"' + $ProjectFile + '"')) | Out-Null
    Ok "The editor is starting."
}

function Invoke-Package {
    Head "Packaging a Shipping build for friends"
    if (-not (Require-Engine)) { return }
    $uat = Join-Path $script:EngineRoot "Engine\Build\BatchFiles\RunUAT.bat"
    $out = Join-Path $ProjectRoot "Packaged"
    $log = Join-Path $ReportDir ("package-" + $script:Stamp + ".log")
    New-Item -ItemType Directory -Force -Path $out | Out-Null
    $maps = "L_MainMenu+L_Transition+L_Staging+L_IronwoodYard+L_VelvetClub"
    Say "  This cooks every map and texture; expect 30-120 minutes the first time."
    $start = Get-Date
    $code = Invoke-Logged $uat @("BuildCookRun", ("-project=" + $ProjectFile), "-noP4", "-platform=Win64", "-clientconfig=Shipping",
        "-build", "-cook", ("-map=" + $maps), "-stage", "-pak", "-compressed", "-prereqs", "-archive", ("-archivedirectory=" + $out), "-utf8output") $log
    $mins = [math]::Round(((Get-Date) - $start).TotalMinutes, 1)
    if ($code -ne 0) { Bad ("Packaging failed after $mins min (exit $code)."); Add-ErrorLines $log; return }
    $gameDir = Join-Path $out "Windows"
    if (-not (Test-Path $gameDir)) { $gameDir = $out }
    $sizeGB = [math]::Round(((Get-ChildItem $gameDir -Recurse -File | Measure-Object Length -Sum).Sum) / 1GB, 1)
    Ok ("Packaged in $mins min: " + $gameDir + " ($sizeGB GB)")
    $zip = Join-Path $out ("AndrewsAirsoft-" + (Get-Date -Format "yyyy-MM-dd") + ".zip")
    $tar = Join-Path $env:SystemRoot "System32\tar.exe"
    if (Test-Path $tar) {
        Say "  Zipping it for sharing..."
        if (Test-Path $zip) { Remove-Item $zip -Force }
        $items = @(Get-ChildItem $gameDir | ForEach-Object { $_.Name })
        Push-Location $gameDir
        try { & $tar -a -c -f $zip @items 2>&1 | Out-Null } finally { Pop-Location }
        if ($LASTEXITCODE -eq 0 -and (Test-Path $zip)) { Ok ("Zip for friends: " + $zip + " (" + [math]::Round((Get-Item $zip).Length / 1GB, 1) + " GB). Upload it to Google Drive and share the link; everyone must run the same build.") }
        else { Warn "Zipping failed. Right-click the Windows folder > Send to > Compressed (zipped) folder instead." }
    } else { Warn "Right-click the Windows folder > Send to > Compressed (zipped) folder to share it." }
}

function Show-Menu {
    while ($true) {
        Write-Host ""
        Write-Host "  ANDREW'S AIRSOFT - build helper" -ForegroundColor Cyan
        Write-Host "  1  Check my PC"
        Write-Host "  2  Build the game code"
        Write-Host "  3  Build the game content (art, sound, maps)"
        Write-Host "  4  Open the editor"
        Write-Host "  5  Package the game for friends"
        Write-Host "  6  Do 1, 2 and 3 in order (first time)"
        Write-Host "  7  Make Visual Studio project files"
        Write-Host "  Q  Quit"
        $choice = Read-Host "  Choose"
        $script:Report.Clear(); $script:Failed = $false
        $script:Stamp = Get-Date -Format "yyyyMMdd-HHmmss"
        switch ($choice.Trim().ToUpper()) {
            "1" { Invoke-Check; Save-Report "check" }
            "2" { Invoke-Build; Save-Report "build" }
            "3" { Invoke-Setup; Save-Report "setup" }
            "4" { Invoke-Editor }
            "5" { Invoke-Package; Save-Report "package" }
            "6" { Invoke-All; Save-Report "all" }
            "7" { Invoke-ProjectFiles; Save-Report "files" }
            "Q" { return }
            default { Write-Host "  Type a number from the list." -ForegroundColor Yellow }
        }
    }
}

function Invoke-All {
    Invoke-Check
    if ($script:Failed) { Say ""; Say "Fix the FAIL items above first, then run this again." "Yellow"; return }
    Invoke-Build
    if ($script:Failed) { return }
    Invoke-Setup
    if (-not $script:Failed) { Say ""; Say "Done. Choose 'Open the editor', press Play, or package the game for friends." "Green" }
}

try {
    switch ($Action.ToLower()) {
        "menu" { Show-Menu }
        "check" { Invoke-Check; Save-Report "check" }
        "files" { Invoke-ProjectFiles; Save-Report "files" }
        "build" { Invoke-Build; Save-Report "build" }
        "setup" { Invoke-Setup; Save-Report "setup" }
        "editor" { Invoke-Editor }
        "package" { Invoke-Package; Save-Report "package" }
        "all" { Invoke-All; Save-Report "all" }
        default { Write-Host "Unknown action '$Action'. Use: menu, check, files, build, setup, editor, package, all." -ForegroundColor Yellow; exit 2 }
    }
} catch {
    Bad ("The helper itself hit an error: " + $_.Exception.Message + " (line " + $_.InvocationInfo.ScriptLineNumber + ")")
    Save-Report "helper-error"
    exit 1
}
if ($script:Failed) { exit 1 }
