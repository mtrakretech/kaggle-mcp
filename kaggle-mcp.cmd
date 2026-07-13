@echo off
REM Launch Kaggle MCP Server on Windows
setlocal
cd /d "%~dp0"
if exist "%~dp0.env" (
  for /f "usebackq eol=# tokens=1,* delims==" %%A in ("%~dp0.env") do (
    if not "%%A"=="" set "%%A=%%B"
  )
)
if defined KAGGLE_KEY if not defined KAGGLE_API_TOKEN set "KAGGLE_API_TOKEN=%KAGGLE_KEY%"
python "%~dp0kaggle_mcp.py" %*
