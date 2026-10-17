@echo off
REM Load the bumpy-web docker image from an archive and run the container (Windows).
REM Usage: docker\load-image.cmd [archive]
setlocal

set ARCHIVE=%1
if "%ARCHIVE%"=="" set ARCHIVE=dist\bumpy-web-image.tar.gz

if not exist "%ARCHIVE%" (
  echo archive not found: %ARCHIVE%
  exit /b 1
)

echo ==^> Loading image from %ARCHIVE%
if not exist dist mkdir dist
tar -xzf "%ARCHIVE%" -C dist
if errorlevel 1 exit /b 1

docker load -i dist\bumpy-web-image.tar
if errorlevel 1 exit /b 1

del dist\bumpy-web-image.tar

echo ==^> Running container on http://localhost:8080
docker rm -f bumpy-web >nul 2>&1
docker run -d --name bumpy-web -p 8080:80 bumpy-web:latest
if errorlevel 1 exit /b 1

echo Done. Open http://localhost:8080
endlocal
