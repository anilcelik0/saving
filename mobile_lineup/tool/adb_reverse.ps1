# Every connected Android device (phone over USB / wireless adb, emulator) reaches the dev backend:
# device localhost:8000 -> this PC's nginx on port 80. Rules are lost when a device reconnects: run before each launch
# (VS Code "Line Up (dev backend)" does it as its preLaunchTask). Usage: powershell -File tool\adb_reverse.ps1
$adb = Join-Path $env:USERPROFILE "Android\sdk\platform-tools\adb.exe"
$ids = & $adb devices | Select-String "`tdevice$" | ForEach-Object { ($_ -split "`t")[0] }
if (-not $ids) {
    Write-Error "No Android device connected (adb devices). Connect the phone or start the emulator."
    exit 1
}
foreach ($id in $ids) {
    & $adb -s $id reverse tcp:8000 tcp:80 | Out-Null
    Write-Host "adb reverse tcp:8000 -> tcp:80 on $id"
}
