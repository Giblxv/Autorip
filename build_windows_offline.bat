@echo off
REM Gera o AutoRIP.exe SEM internet, usando os pacotes de wheelhouse\ (veja preparar_offline.bat).
python -m pip install --no-index --find-links wheelhouse -r requirements.txt || goto :err
pyinstaller --noconfirm --name AutoRIP --noconsole --icon installer_assets\autorip.ico --collect-all scipy --add-data "autorip\ui;autorip\ui" autorip_gui.py || goto :err
if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" ("%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" installer.iss) else echo Instale o Inno Setup 6 (instalador offline) para gerar o AutoRIP_Setup.exe.
echo Pronto: dist\AutoRIP\AutoRIP.exe
exit /b 0
:err
echo Falhou.
exit /b 1
