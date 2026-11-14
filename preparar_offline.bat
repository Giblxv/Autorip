@echo off
REM Rode UMA vez num computador COM internet. Baixa os pacotes para a pasta wheelhouse\.
REM Depois copie a pasta do projeto (com wheelhouse\) para o PC sem internet e rode build_windows_offline.bat.
python -m pip download -r requirements.txt -d wheelhouse || (echo Falhou & exit /b 1)
if exist "agent\requirements.txt" python -m pip download -r agent\requirements.txt -d wheelhouse || (echo Falhou & exit /b 1)
echo Pronto: pasta wheelhouse criada.
