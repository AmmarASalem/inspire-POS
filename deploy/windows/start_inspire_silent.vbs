' Launches start_inspire.bat with no visible console window.
' Used by the Startup-folder shortcut (auto-start on boot/login) and can
' also be used for the desktop icon so double-clicking it stays silent.
Set fso = CreateObject("Scripting.FileSystemObject")
scriptDir = fso.GetParentFolderName(WScript.ScriptFullName)
batPath = scriptDir & "\start_inspire.bat"

Set shell = CreateObject("WScript.Shell")
shell.Run """" & batPath & """", 0, False
