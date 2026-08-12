' ============================================================
'  PANEL_APP.vbs  -  Doble clic: abre el Panel FUZION FX como una
'  APLICACION (ventana propia, sin barra ni pestanas del navegador).
'  Usa el Chrome o Edge que ya tenes, en "modo aplicacion". Arranca
'  el servidor local oculto (si ya corre, lo reutiliza).
'
'  Para que arranque con Windows: copia un acceso directo de este
'  archivo en la carpeta que sale al escribir  shell:startup  en Inicio.
' ============================================================
Option Explicit
Dim fso, sh, proj, url, i, cands, browser
Set fso = CreateObject("Scripting.FileSystemObject")
Set sh  = CreateObject("WScript.Shell")
proj = fso.GetParentFolderName(WScript.ScriptFullName)
sh.CurrentDirectory = proj
url = "http://127.0.0.1:8770"

' 1) Servidor del panel OCULTO (pythonw = sin ventana). Si el puerto ya esta
'    ocupado, el servidor se cierra solo y se reutiliza el que ya corre.
sh.Run "pythonw """ & proj & "\fuzion_fx\dashboard\server.py"" --no-open", 0, False
WScript.Sleep 2500                       ' darle tiempo a levantar

' 2) Buscar Chrome o Edge (en ese orden) para abrir en MODO APLICACION.
cands = Array( _
  sh.ExpandEnvironmentStrings("%ProgramFiles%\Google\Chrome\Application\chrome.exe"), _
  sh.ExpandEnvironmentStrings("%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"), _
  sh.ExpandEnvironmentStrings("%LocalAppData%\Google\Chrome\Application\chrome.exe"), _
  sh.ExpandEnvironmentStrings("%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe"), _
  sh.ExpandEnvironmentStrings("%ProgramFiles%\Microsoft\Edge\Application\msedge.exe"))
browser = ""
For i = 0 To UBound(cands)
  If fso.FileExists(cands(i)) Then browser = cands(i) : Exit For
Next

If browser = "" Then
  ' Sin Chrome/Edge: se abre en el navegador por defecto (ventana normal).
  sh.Run url, 1, False
Else
  sh.Run """" & browser & """ --app=" & url & " --window-size=1440,1000", 1, False
End If
