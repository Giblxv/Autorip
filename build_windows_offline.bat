@echo off
REM Gera o AutoRIP.exe one-file SEM internet, usando os pacotes de wheelhouse\ (veja preparar_offline.bat).
python -m pip install --no-index --find-links wheelhouse -r requirements.txt || goto :err
python tools\generate_mobile_qrs.py || goto :err
pyinstaller --noconfirm --clean --onefile --name AutoRIP --distpath dist\AutoRIP --workpath build\pyinstaller --noconsole --icon installer_assets\autorip.ico --collect-all scipy --add-data "autorip\ui;autorip\ui" autorip_gui.py || goto :err
if exist "agent\print_agent.py" (
  echo Compilando PrintExpAgent.exe...
  if exist "agent\requirements.txt" python -m pip install --no-index --find-links wheelhouse -r agent\requirements.txt || goto :err
  pyinstaller --noconfirm --clean --onefile --name PrintExpAgent --paths . --distpath dist\PrintExpAgent --workpath build\pyinstaller-agent --noconsole agent\print_agent.py || goto :err
)
if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" (
  "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" installer.iss
  if errorlevel 1 goto :err
) else (
  echo Instale o Inno Setup 6 para gerar o AutoRIP_Setup.exe.
)
echo Pronto: dist\AutoRIP\AutoRIP.exe
exit /b 0
:err
echo Falhou.
exit /b 1
