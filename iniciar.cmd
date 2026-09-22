@echo off
setlocal
cd /d "%~dp0"
where python >nul 2>nul
if errorlevel 1 (
  echo Instale Python 3.10 ou superior e habilite Add Python to PATH.
  pause
  exit /b 1
)
if not exist ".venv\Scripts\python.exe" python -m venv .venv
if errorlevel 1 goto erro
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto erro
".venv\Scripts\python.exe" manage.py migrate
if errorlevel 1 goto erro
".venv\Scripts\python.exe" manage.py check
if errorlevel 1 goto erro
".venv\Scripts\python.exe" manage.py shell -c "from chamados.models import Usuario; raise SystemExit(0 if Usuario.objects.filter(perfil='ADMIN', is_active=True).exists() else 1)"
if errorlevel 1 (
  echo Vamos criar seu primeiro administrador.
  ".venv\Scripts\python.exe" manage.py criar_admin
  if errorlevel 1 goto erro
)
echo.
echo HelpDesk: http://127.0.0.1:8000
echo Para encerrar, pressione Ctrl+C nesta janela.
".venv\Scripts\python.exe" manage.py runserver 127.0.0.1:8000
exit /b %errorlevel%
:erro
echo Nao foi possivel iniciar. Confira o erro acima.
pause
exit /b 1
