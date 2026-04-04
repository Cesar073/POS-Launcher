[Setup]
AppName=NexoPOS
AppVersion=0.4.1
; DefaultDirName es la carpeta de destino en la PC del cliente.
; pf -> Program Files
;DefaultDirName={pf}\NexoPOS
; userappdata -> AppData de cada usuario en Windows.
DefaultDirName={localappdata}\NexoPOS\Launcher
DefaultGroupName=NexoPOS
OutputDir=output
OutputBaseFilename=NexoPOS_Installer
Compression=lzma
SolidCompression=yes
; Indicamos que no se necesitan privilegios de Admin para su instalación.
PrivilegesRequired=lowest

[Files]
; Tu app completa (standalone)
Source: "D:\Proyectos\Python\POS-Launcher\dist\main.dist\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs

; Redistribuible (mismo nombre en [Run])
Source: "D:\Proyectos\Python\POS-Launcher\installer\VC_redist.x64.exe"; DestDir: "{tmp}"; Flags: deleteafterinstall

[Icons]
; Escritorio del usuario (adecuado con PrivilegesRequired=lowest)
Name: "{userdesktop}\NexoPOS"; Filename: "{app}\Launcher_Windows.exe"; WorkingDir: "{app}"
; Menú Inicio (carpeta del grupo)
Name: "{group}\NexoPOS"; Filename: "{app}\Launcher_Windows.exe"; WorkingDir: "{app}"

[Run]
; Instalar Visual C++ si hace falta
Filename: "{tmp}\VC_redist.x64.exe"; \
  Parameters: "/install /quiet /norestart"; \
  StatusMsg: "Instalando dependencias necesarias..."; \
  Check: NeedVCRedist

; Ejecutar app al finalizar (opcional)
Filename: "{app}\Launcher_Windows.exe"; Description: "Ejecutar POS"; Flags: nowait postinstall skipifsilent

[Code]
function NeedVCRedist(): Boolean;
var
  Installed: Cardinal;
begin
  Result := not RegQueryDWordValue(
    HKLM,
    'SOFTWARE\Microsoft\VisualStudio\14.0\VC\Runtimes\x64',
    'Installed',
    Installed
  ) or (Installed = 0);
end;
