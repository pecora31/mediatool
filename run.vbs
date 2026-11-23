Set WshShell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
currentDir = fso.GetParentFolderName(WScript.ScriptFullName)
localAppData = WshShell.ExpandEnvironmentStrings("%LOCALAPPDATA%")
pythonwPath = localAppData & "\Programs\Python\Python310\pythonw.exe"

WshShell.CurrentDirectory = currentDir
WshShell.Run """" & pythonwPath & """ """ & currentDir & "\main.py""", 0, False
WScript.Sleep 1000
WshShell.Run "http://127.0.0.1:5000"
