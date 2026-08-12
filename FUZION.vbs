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
' pythonw = sin ventana. El Centro de Control hace el resto (update + arranque + app).
sh.Run "pythonw """ & proj & "\fuzion_fx\scripts\centro.py""", 0, False
