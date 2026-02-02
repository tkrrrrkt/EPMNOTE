@echo off
chcp 65001 >nul
echo デスクトップにショートカットを作成しています...

:: PowerShellでショートカット作成
powershell -Command "$WshShell = New-Object -ComObject WScript.Shell; $Shortcut = $WshShell.CreateShortcut('%USERPROFILE%\Desktop\EPMNote.lnk'); $Shortcut.TargetPath = 'C:\10_dev\EPMNote\run.bat'; $Shortcut.WorkingDirectory = 'C:\10_dev\EPMNote'; $Shortcut.Description = 'Note.com記事作成支援ツール'; $Shortcut.Save()"

if %ERRORLEVEL% EQU 0 (
    echo.
    echo ショートカットを作成しました: %USERPROFILE%\Desktop\EPMNote.lnk
    echo デスクトップの「EPMNote」をダブルクリックで起動できます。
) else (
    echo エラー: ショートカットの作成に失敗しました
)

echo.
pause
