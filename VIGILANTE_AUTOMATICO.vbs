' ============================================================
'  VIGILANTE_AUTOMATICO.vbs  -  Doble clic: arranca el vigilante
'  de Fuzion FX INVISIBLE (sin ventana). Levanta y cuida el
'  colector + 4 bots y los reinicia si se caen. No deja ninguna
'  ventana abierta: corre en segundo plano, como una app.
'
'  Para que arranque SOLO con Windows: copia un acceso directo de
'  este archivo en la carpeta que sale al escribir  shell:startup
'  en el menu Inicio.
'
'  Para VER que esta haciendo: abri logs\vigilante.log
'  Para DETENERLO: doble clic en DETENER_FUZION_FX.bat (apaga los
'  bots) y termina "pythonw.exe" desde el Administrador de tareas.
' ============================================================
Option Explicit
Dim fso, shell, proj, cmd
Set fso = CreateObject("Scripting.FileSystemObject")
Set shell = CreateObject("WScript.Shell")

' Carpeta donde esta este .vbs (raiz del proyecto).
proj = fso.GetParentFolderName(WScript.ScriptFullName)
shell.CurrentDirectory = proj

' pythonw = Python SIN ventana de consola. 0 = ventana oculta; False = no esperar.
cmd = "pythonw """ & proj & "\fuzion_fx\scripts\vigilante.py"""
shell.Run cmd, 0, False
