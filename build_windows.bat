@echo off
REM Gera dist\AutoRIP\AutoRIP.exe (one-file) e, se o Inno Setup 6 estiver instalado, Output\AutoRIP_Setup.exe
python -m pip install -r requirements.txt || goto :err
pyinstaller --noconfirm --clean --onefile --name AutoRIP --distpath dist\AutoRIP --workpath build\pyinstaller --noconsole --icon installer_assets\autorip.ico --collect-all scipy --add-data "autorip\ui;autorip\ui" autorip_gui.py || goto :err
if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" (
  "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" installer.iss
  if errorlevel 1 goto :err
) else (
  echo Instale o Inno Setup 6 para gerar o AutoRIP_Setup.exe.
)
echo Pronto. Teste: dist\AutoRIP\AutoRIP.exe
exit /b 0
:err
echo Falhou.
exit /b 1
