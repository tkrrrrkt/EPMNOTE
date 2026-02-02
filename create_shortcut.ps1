$WshShell = New-Object -ComObject WScript.Shell
$Desktop = [Environment]::GetFolderPath('Desktop')
$Shortcut = $WshShell.CreateShortcut("$Desktop\EPMNote.lnk")
$Shortcut.TargetPath = "C:\10_dev\EPMNote\run.bat"
$Shortcut.WorkingDirectory = "C:\10_dev\EPMNote"
$Shortcut.Save()
Write-Host "Desktop shortcut created: $Desktop\EPMNote.lnk"
