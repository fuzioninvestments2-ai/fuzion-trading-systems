' ============================================================
'  CREAR_ACCESO_ESCRITORIO.vbs
'  Doble clic UNA vez: pone en tu Escritorio el icono
'  "Fuzion FX" que abre todo (FUZION.vbs) con un clic.
' ============================================================
Option Explicit
Dim fso, sh, proj, target, desktop, lnkPath, lnk

Set fso = CreateObject("Scripting.FileSystemObject")
Set sh  = CreateObject("WScript.Shell")

' Carpeta del proyecto = donde esta este .vbs.
proj   = fso.GetParentFolderName(WScript.ScriptFullName)
target = proj & "\FUZION.vbs"

If Not fso.FileExists(target) Then
    MsgBox "No encontre FUZION.vbs en la carpeta del proyecto." & vbCrLf & _
           "Poné este archivo junto a FUZION.vbs y volvé a intentar.", _
           16, "Fuzion FX"
    WScript.Quit
End If

desktop = sh.SpecialFolders("Desktop")
lnkPath = desktop & "\Fuzion FX.lnk"

Set lnk = sh.CreateShortcut(lnkPath)
' Se lanza con wscript (sin ventana negra) pasando FUZION.vbs como argumento.
lnk.TargetPath       = "wscript.exe"
lnk.Arguments        = """" & target & """"
lnk.WorkingDirectory = proj
lnk.WindowStyle      = 1
lnk.IconLocation     = "shell32.dll,44"       ' icono generico (rayo/energia)
lnk.Description       = "Abrir Fuzion FX (colector + 4 bots + panel)"
lnk.Save

MsgBox "Listo. En tu Escritorio esta el icono 'Fuzion FX'." & vbCrLf & _
       "Doble clic ahi y arranca todo.", 64, "Fuzion FX"
