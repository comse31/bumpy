@echo off
REM Export the bumpy-web docker image to a transferable archive (Windows).
REM Usage: docker\export-image.cmd [image] [archive]
setlocal

set IMAGE=%1
if "%IMAGE%"=="" set IMAGE=bumpy-web:latest

set ARCHIVE=%2
if "%ARCHIVE%"=="" set ARCHIVE=dist\bumpy-web-image.tar.gz

if not exist dist mkdir dist

echo ==^> Saving image %IMAGE% -^> %ARCHIVE%
docker save %IMAGE% -o dist\bumpy-web-image.tar
if errorlevel 1 exit /b 1

tar -czf %ARCHIVE% -C dist bumpy-web-image.tar
if errorlevel 1 exit /b 1

del dist\bumpy-web-image.tar

echo ==^> Done: %ARCHIVE%
endlocal
