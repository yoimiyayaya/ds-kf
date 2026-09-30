' ============================================================
'  Balance Pet V3 - fully silent launcher (no console window).
'  ASCII only: Windows Script Host reads .vbs in the ANSI page.
'  The desktop shortcut points at wscript.exe + this file.
' ============================================================
Option Explicit

Dim fso, sh, here, py, pyw, script
Set fso = CreateObject("Scripting.FileSystemObject")
Set sh = CreateObject("WScript.Shell")

here = fso.GetParentFolderName(WScript.ScriptFullName)
script = fso.BuildPath(here, "balance_pet.py")

If Not fso.FileExists(script) Then
    MsgBox "balance_pet.py not found next to this launcher:" & vbCrLf & script, 16, "Balance Pet"
    WScript.Quit 1
End If

py = FindPython()
If py = "" Then
    MsgBox "No Python interpreter with tkinter was found." & vbCrLf & vbCrLf & _
           "Install Python 3.9+ (tick ""Add python.exe to PATH"") and try again." & vbCrLf & _
           "See README.md for details.", 16, "Balance Pet"
    WScript.Quit 1
End If

' prefer pythonw.exe so nothing flashes on screen
pyw = py
If LCase(Right(py, 10)) = "python.exe" Then
    If fso.FileExists(Left(py, Len(py) - 10) & "pythonw.exe") Then
        pyw = Left(py, Len(py) - 10) & "pythonw.exe"
    End If
End If

sh.CurrentDirectory = here
sh.Run """" & pyw & """ """ & script & """", 0, False
WScript.Quit 0

' ------------------------------------------------------------

Function FindPython()
    Dim out, lines, i, cand

    FindPython = ""

    ' 1) the py launcher registered on this machine
    out = Capture("cmd /c py -3 -c ""import tkinter,sys;print(sys.executable)""")
    cand = FirstPythonLine(out)
    If cand <> "" Then FindPython = cand : Exit Function

    ' 2) every python.exe on PATH, take the first one that has tkinter
    out = Capture("cmd /c where python")
    lines = Split(out, vbCrLf)
    For i = 0 To UBound(lines)
        cand = Trim(lines(i))
        If cand <> "" Then
            If InStr(LCase(cand), "python.exe") > 0 Then
                If fso.FileExists(cand) Then
                    If Capture("cmd /c """ & cand & """ -c ""import tkinter""") <> "__FAIL__" Then
                        FindPython = cand
                        Exit Function
                    End If
                End If
            End If
        End If
    Next

    ' 3) the python shipped with the DeepSeek Harness runtime
    cand = sh.ExpandEnvironmentStrings("%USERPROFILE%") & _
           "\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe"
    If fso.FileExists(cand) Then
        FindPython = cand
        Exit Function
    End If
End Function

Function FirstPythonLine(text)
    Dim lines, i, line
    FirstPythonLine = ""
    If text = "" Then Exit Function
    lines = Split(text, vbCrLf)
    For i = 0 To UBound(lines)
        line = Trim(lines(i))
        If InStr(LCase(line), "python") > 0 And InStr(line, ":") > 0 Then
            FirstPythonLine = line
            Exit Function
        End If
    Next
End Function

' Runs a command hidden and returns its stdout.
' Returns "__FAIL__" when the command exits non-zero.
Function Capture(cmdline)
    Dim ex, out, waited
    Capture = ""
    On Error Resume Next
    Set ex = sh.Exec(cmdline)
    If Err.Number <> 0 Then
        Err.Clear
        Capture = "__FAIL__"
        Exit Function
    End If
    On Error GoTo 0

    waited = 0
    Do While ex.Status = 0
        WScript.Sleep 25
        waited = waited + 1
        If waited > 400 Then            ' 10s is plenty for "print a path"
            ex.Terminate
            Capture = "__FAIL__"
            Exit Function
        End If
    Loop
    out = ""
    On Error Resume Next
    If Not ex.StdOut.AtEndOfStream Then out = ex.StdOut.ReadAll
    On Error GoTo 0

    If ex.ExitCode <> 0 Then
        Capture = "__FAIL__"
    Else
        Capture = out
    End If
End Function
