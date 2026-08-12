' ============================================================
'  FUZION.vbs  -  EL BOTON UNICO. Doble clic y listo:
'    1) Actualiza el codigo (git pull).
'    2) Levanta y CUIDA todo: colector + 4 bots + panel (vigilante).
'    3) Abre la APP en su propia ventana (Chrome/Edge en modo app).
'  Todo en segundo plano, sin ventanas negras. Cerra la ventana de la
'  app cuando quieras: el motor sigue corriendo y cuidandose solo.
'
'  Para que arranque con Windows: copia un acceso directo de este
'  archivo en la carpeta que sale al escribir  shell:startup  en Inicio.
' ============================================================
Option Explicit
Dim fso, sh, proj
Set fso = CreateObject("Scripting.FileSystemObject")
Set sh  = CreateObject("WScript.Shell")
proj = fso.GetParentFolderName(WScript.ScriptFullName)
sh.CurrentDirectory = proj
' pythonw = sin ventana (no parpadea). El Centro de Control BUSCA solo el Python
' real que tiene las librerias (Python314) para lanzar los servicios, evitando el
' Python "de la Store" (WindowsApps) que no las tiene.
sh.Run "pythonw """ & proj & "\fuzion_fx\scripts\centro.py""", 0, False
