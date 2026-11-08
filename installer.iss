; AutoRIP - instalador (Inno Setup 6). Compile com: ISCC installer.iss  (build_windows.bat ja faz isso)
#define AppName "AutoRIP"
#define AppVersion "0.8.7"
#define AppExe "AutoRIP.exe"

[Setup]
AppId={{6B1F2D7C-4A0E-4C57-9E53-A07A4B1D0C11}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=AutoRIP
DefaultDirName={localappdata}\Programs\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
DisableWelcomePage=no
WizardStyle=modern
WizardImageFile=installer_assets\side.bmp
WizardSmallImageFile=installer_assets\small.bmp
WizardImageBackColor=$1A1A1A
SetupIconFile=installer_assets\autorip.ico
UninstallDisplayIcon={app}\{#AppExe}
UninstallDisplayName={#AppName}
OutputBaseFilename=AutoRIP_Setup
Compression=lzma2/max
SolidCompression=yes
ArchitecturesAllowed=x64
ArchitecturesInstallIn64BitMode=x64
PrivilegesRequired=lowest
CloseApplications=yes

[Languages]
Name: "brazilianportuguese"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"

[Messages]
brazilianportuguese.WelcomeLabel1=Bem-vindo ao [name]!
brazilianportuguese.WelcomeLabel2=O [name] automatiza etapas de pré-impressão para DTF e DTF UV: converte a arte com ICC (se configurado), prepara o branco e gera um arquivo .PRT.%n%nO PRT deve ser validado no PrintExp e na sua impressora antes de produção. O processamento local funciona offline.%n%nClique em Avançar para começar.
brazilianportuguese.FinishedHeadingLabel=É isso aí, pessoal!
brazilianportuguese.FinishedLabel=O [name] foi instalado. Jogue uma arte na pasta de entrada e deixe o resto com ele.

[CustomMessages]
brazilianportuguese.TaskDesktop=Criar um atalho na área de trabalho
brazilianportuguese.TaskAutoStart=Iniciar o AutoRIP junto com o Windows (modo automático sempre ligado)
brazilianportuguese.PgFoldersTitle=Pastas de trabalho
brazilianportuguese.PgFoldersDesc=Onde o AutoRIP vai buscar as artes e guardar os arquivos .PRT?
brazilianportuguese.PgFoldersSub=Você pode mudar isso depois, em Configurações dentro do programa.
brazilianportuguese.PgIn=Pasta de ENTRADA (hot folder com artes PNG, TIFF ou JPEG):
brazilianportuguese.PgOut=Pasta de SAÍDA (arquivos .PRT para o PrintExp):
brazilianportuguese.PgIccTitle=Perfil de cor (ICC)
brazilianportuguese.PgIccDesc=Escolha o perfil ICC CMYK da sua impressora (opcional).
brazilianportuguese.PgIccSub=Selecione o perfil da sua impressora. Se pular, a conversão de cor será genérica; configure o ICC correto antes de produção.
brazilianportuguese.PgIcc=Arquivo .icc:
brazilianportuguese.RunApp=Abrir o AutoRIP agora

[Tasks]
Name: "desktopicon"; Description: "{cm:TaskDesktop}"; GroupDescription: "{cm:AdditionalIcons}"
Name: "autostart"; Description: "{cm:TaskAutoStart}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "dist\AutoRIP\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion createallsubdirs

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{group}\{#AppName} (modo direto, sem navegador)"; Filename: "{app}\{#AppExe}"; Parameters: "--direct"
Name: "{group}\Desinstalar {#AppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon
Name: "{autodesktop}\{#AppName} (modo direto)"; Filename: "{app}\{#AppExe}"; Parameters: "--direct"
Name: "{userstartup}\{#AppName}"; Filename: "{app}\{#AppExe}"; Parameters: "--direct"; Tasks: autostart

[Run]
Filename: "{app}\{#AppExe}"; Description: "{cm:RunApp}"; Flags: postinstall nowait skipifsilent

[Code]
var
  FoldersPage: TInputDirWizardPage;
  IccPage: TInputFileWizardPage;

procedure InitializeWizard;
begin
  { cores e fonte no estilo do programa }
  WizardForm.Color := $E1F8FF;
  WizardForm.MainPanel.Color := $1A1A1A;
  WizardForm.PageNameLabel.Font.Color := $00D8FF;
  WizardForm.PageNameLabel.Font.Style := [fsBold];
  WizardForm.PageDescriptionLabel.Font.Color := clWhite;
  WizardForm.WelcomeLabel1.Font.Name := 'Comic Sans MS';
  WizardForm.WelcomeLabel1.Font.Size := 16;
  WizardForm.FinishedHeadingLabel.Font.Name := 'Comic Sans MS';
  WizardForm.FinishedHeadingLabel.Font.Size := 16;

  FoldersPage := CreateInputDirPage(wpSelectTasks, CustomMessage('PgFoldersTitle'), CustomMessage('PgFoldersDesc'),
    CustomMessage('PgFoldersSub'), False, '');
  FoldersPage.Add(CustomMessage('PgIn'));
  FoldersPage.Add(CustomMessage('PgOut'));
  FoldersPage.Values[0] := ExpandConstant('{userdocs}\AutoRIP\Entrada');
  FoldersPage.Values[1] := ExpandConstant('{userdocs}\AutoRIP\Saida');

  IccPage := CreateInputFilePage(FoldersPage.ID, CustomMessage('PgIccTitle'), CustomMessage('PgIccDesc'), CustomMessage('PgIccSub'));
  IccPage.Add(CustomMessage('PgIcc'), 'Perfis ICC|*.icc;*.icm|Todos os arquivos|*.*', '.icc');
end;

function JsonEscape(const S: String): String;
var R: String;
begin
  R := S;
  StringChangeEx(R, '\', '\\', True);
  Result := R;
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  Dir, Cfg, J: String;
begin
  if CurStep = ssPostInstall then
  begin
    ForceDirectories(FoldersPage.Values[0]);
    ForceDirectories(FoldersPage.Values[1]);
    Dir := ExpandConstant('{userappdata}\AutoRIP');
    ForceDirectories(Dir);
    Cfg := Dir + '\autorip.json';
    if not FileExists(Cfg) then   { nao sobrescreve a configuracao em atualizacoes }
    begin
      J := '{' + #13#10 +
           '  "hot_folder": "' + JsonEscape(FoldersPage.Values[0]) + '",' + #13#10 +
           '  "output_folder": "' + JsonEscape(FoldersPage.Values[1]) + '"';
      if IccPage.Values[0] <> '' then
        J := J + ',' + #13#10 + '  "icc_path": "' + JsonEscape(IccPage.Values[0]) + '"';
      J := J + #13#10 + '}';
      SaveStringToFile(Cfg, J, False);
    end;
  end;
end;
