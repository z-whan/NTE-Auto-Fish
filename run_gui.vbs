Set fso = CreateObject("Scripting.FileSystemObject")
Set shell = CreateObject("Shell.Application")

appDir = fso.GetParentFolderName(WScript.ScriptFullName)
pythonw = appDir & "\.venv\Scripts\pythonw.exe"
python = appDir & "\.venv\Scripts\python.exe"
script = appDir & "\main.py"

If fso.FileExists(pythonw) Then
    runner = pythonw
Else
    runner = python
End If

shell.ShellExecute runner, """" & script & """", appDir, "runas", 1
