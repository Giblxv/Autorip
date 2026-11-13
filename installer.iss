; AutoRIP - instalador (Inno Setup 6). Compile com: ISCC installer.iss  (build_windows.bat ja faz isso)
#define AppName "AutoRIP"
#define AppVersion "0.8.26"
#define AppExe "AutoRIP.exe"

[Setup]
AppId={{6B1F2D7C-4A0E-4C57-9E53-A07A4B1D0C11}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=AutoRIP
DefaultDirName={localappdata}\Programs\{#AppName}
DisableDirPage=no
DirExistsWarning=yes
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
brazilianportuguese.TaskAgentAutoStart=Iniciar o agente de automação do PrintExp junto com o Windows
brazilianportuguese.SelectDirLabel3=Escolha onde os arquivos do programa serão instalados. As pastas de entrada, saída, concluídos, erros e impressos são configuradas separadamente abaixo.
brazilianportuguese.PgFoldersTitle=Pastas de trabalho
brazilianportuguese.PgFoldersDesc=Onde o AutoRIP vai buscar as artes e guardar os arquivos .PRT?
brazilianportuguese.PgFoldersSub=Você pode mudar isso depois, em Configurações dentro do programa.
brazilianportuguese.PgIn=Pasta de ENTRADA (hot folder com artes PNG, TIFF ou JPEG):
brazilianportuguese.PgOut=Pasta de SAÍDA (arquivos .PRT para o PrintExp):
brazilianportuguese.PgIccTitle=Perfil de cor (ICC)
brazilianportuguese.PgIccDesc=Escolha o perfil ICC CMYK da sua impressora (opcional).
brazilianportuguese.PgIccSub=Selecione o perfil da sua impressora. Se pular, a conversão de cor será genérica; configure o ICC correto antes de produção.
brazilianportuguese.PgIcc=Arquivo .icc:
brazilianportuguese.PgPrintExpTitle=Automação do PrintExp
brazilianportuguese.PgPrintExpDesc=Informe o executável do PrintExp usado pelo agente de automação.
brazilianportuguese.PgPrintExpSub=Essa configuração é opcional. O instalador do PrintExp pode ser colocado em vendor\PrintExpSetup.exe para ser executado ao final.
brazilianportuguese.PgPrintExp=Executável do PrintExp:
brazilianportuguese.RunApp=Abrir o AutoRIP agora

[Tasks]
Name: "desktopicon"; Description: "{cm:TaskDesktop}"; GroupDescription: "{cm:AdditionalIcons}"
Name: "autostart"; Description: "{cm:TaskAutoStart}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked
Name: "agentautostart"; Description: "{cm:TaskAgentAutoStart}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "installer_assets\mobile-android.bmp"; DestName: "mobile-android.bmp"; Flags: dontcopy noencryption
Source: "installer_assets\mobile-ios-guide.bmp"; DestName: "mobile-ios-guide.bmp"; Flags: dontcopy noencryption
Source: "dist\AutoRIP\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion createallsubdirs
Source: "dist\PrintExpAgent\PrintExpAgent.exe"; DestDir: "{app}"; Flags: ignoreversion skipifsourcedoesntexist
Source: "vendor\PrintExpSetup.exe"; DestDir: "{app}\vendor"; Flags: ignoreversion skipifsourcedoesntexist

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{group}\{#AppName} (modo direto, sem navegador)"; Filename: "{app}\{#AppExe}"; Parameters: "--direct"
Name: "{group}\Desinstalar {#AppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon
Name: "{autodesktop}\{#AppName} (modo direto)"; Filename: "{app}\{#AppExe}"; Parameters: "--direct"
Name: "{userstartup}\{#AppName}"; Filename: "{app}\{#AppExe}"; Parameters: "--direct"; Tasks: autostart

[Run]
Filename: "{sys}\schtasks.exe"; Parameters: "/Create /TN ""AutoRIP PrintExp Agent"" /TR """"{app}\PrintExpAgent.exe"""" /SC ONLOGON /RL LIMITED /F"; Tasks: agentautostart; Check: AgentExecutableExists; Flags: runhidden waituntilterminated
Filename: "{app}\vendor\PrintExpSetup.exe"; Description: "Instalar o PrintExp"; Check: PrintExpSetupExists; Flags: postinstall waituntilterminated
Filename: "{app}\{#AppExe}"; Description: "{cm:RunApp}"; Flags: postinstall nowait skipifsilent

[Code]
var
  FoldersPage: TInputDirWizardPage;
  IccPage: TInputFileWizardPage;
  PrintExpPage: TInputFileWizardPage;
  MobileAppsPage: TWizardPage;
  AndroidQrImage, IosQrImage: TBitmapImage;
  AndroidQrLabel, IosQrLabel, MobileAppsNote: TNewStaticText;

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

  PrintExpPage := CreateInputFilePage(IccPage.ID, CustomMessage('PgPrintExpTitle'), CustomMessage('PgPrintExpDesc'), CustomMessage('PgPrintExpSub'));
  PrintExpPage.Add(CustomMessage('PgPrintExp'), 'Executavel|*.exe|Todos os arquivos|*.*', '.exe');

  ExtractTemporaryFile('mobile-android.bmp');
  ExtractTemporaryFile('mobile-ios-guide.bmp');
  MobileAppsPage := CreateCustomPage(PrintExpPage.ID, 'Aplicativos móveis', 'Escaneie um QR para baixar o APK Android ou consultar as instruções para iPhone/iPad.');

  AndroidQrLabel := TNewStaticText.Create(WizardForm);
  AndroidQrLabel.Parent := MobileAppsPage.Surface;
  AndroidQrLabel.SetBounds(10, 6, (MobileAppsPage.SurfaceWidth div 2) - 20, 28);
  AndroidQrLabel.Caption := 'Android - baixar APK';
  AndroidQrLabel.Alignment := taCenter;
  AndroidQrLabel.Font.Style := [fsBold];
  AndroidQrLabel.Font.Color := $1A1A1A;

  IosQrLabel := TNewStaticText.Create(WizardForm);
  IosQrLabel.Parent := MobileAppsPage.Surface;
  IosQrLabel.SetBounds((MobileAppsPage.SurfaceWidth div 2) + 10, 6, (MobileAppsPage.SurfaceWidth div 2) - 20, 28);
  IosQrLabel.Caption := 'iPhone/iPad - instruções';
  IosQrLabel.Alignment := taCenter;
  IosQrLabel.Font.Style := [fsBold];
  IosQrLabel.Font.Color := $1A1A1A;

  AndroidQrImage := TBitmapImage.Create(WizardForm);
  AndroidQrImage.Parent := MobileAppsPage.Surface;
  AndroidQrImage.SetBounds((MobileAppsPage.SurfaceWidth div 4) - 90, 38, 180, 180);
  AndroidQrImage.Stretch := True;
  AndroidQrImage.Center := True;
  AndroidQrImage.Bitmap.LoadFromFile(ExpandConstant('{tmp}\mobile-android.bmp'));

  IosQrImage := TBitmapImage.Create(WizardForm);
  IosQrImage.Parent := MobileAppsPage.Surface;
  IosQrImage.SetBounds((MobileAppsPage.SurfaceWidth * 3 div 4) - 90, 38, 180, 180);
  IosQrImage.Stretch := True;
  IosQrImage.Center := True;
  IosQrImage.Bitmap.LoadFromFile(ExpandConstant('{tmp}\mobile-ios-guide.bmp'));

  MobileAppsNote := TNewStaticText.Create(WizardForm);
  MobileAppsNote.Parent := MobileAppsPage.Surface;
  MobileAppsNote.SetBounds(10, 226, MobileAppsPage.SurfaceWidth - 20, 54);
  MobileAppsNote.Caption := 'Android 0.2.0: prévia assinada com chave de teste; APK otimizado instala separado. iPhone/iPad: o QR abre o guia; ainda não há IPA assinado para distribuição.';
  MobileAppsNote.Alignment := taCenter;
  MobileAppsNote.WordWrap := True;
  MobileAppsNote.Font.Color := $1A1A1A;
end;

function JsonEscape(const S: String): String;
var R: String;
begin
  R := S;
  StringChangeEx(R, '\', '\\', True);
  StringChangeEx(R, '"', '\"', True);
  StringChangeEx(R, #13#10, '\n', True);
  StringChangeEx(R, #13, '\n', True);
  StringChangeEx(R, #10, '\n', True);
  Result := R;
end;

function AgentExecutableExists: Boolean;
begin
  Result := FileExists(ExpandConstant('{app}\PrintExpAgent.exe'));
end;

function PrintExpSetupExists: Boolean;
begin
  Result := FileExists(ExpandConstant('{app}\vendor\PrintExpSetup.exe'));
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  Dir, Cfg, AgentCfg, J: String;
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

    AgentCfg := Dir + '\print-agent.json';
    if not FileExists(AgentCfg) then
    begin
      J := '{' + #13#10 +
           '  "program_dir": "' + JsonEscape(ExpandConstant('{app}')) + '",' + #13#10 +
           '  "agent_exe": "' + JsonEscape(ExpandConstant('{app}\PrintExpAgent.exe')) + '",' + #13#10 +
           '  "printexp_exe": "' + JsonEscape(PrintExpPage.Values[0]) + '",' + #13#10 +
           '  "auto_print": false,' + #13#10 +
           '  "dry_run": false,' + #13#10 +
           '  "hot_folder": "' + JsonEscape(FoldersPage.Values[0]) + '",' + #13#10 +
           '  "output_folder": "' + JsonEscape(FoldersPage.Values[1]) + '",' + #13#10 +
           '  "printed_folder": "' + JsonEscape(ExpandConstant('{userdocs}\AutoRIP\Impressos')) + '",' + #13#10 +
           '  "done_folder": "' + JsonEscape(ExpandConstant('{userdocs}\AutoRIP\Feito')) + '",' + #13#10 +
           '  "error_folder": "' + JsonEscape(ExpandConstant('{userdocs}\AutoRIP\Erro')) + '"' + #13#10 +
           '}';
      SaveStringToFile(AgentCfg, J, False);
    end;
  end;
end;
