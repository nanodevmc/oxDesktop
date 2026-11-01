@echo off
setlocal enabledelayedexpansion

echo ========================================================
echo  exDesktop Windows Native Builder with Compiler Cache
echo ========================================================

:: Cache directory & size limits for .obj compiler caching
if "%SCCACHE_DIR%"=="" set "SCCACHE_DIR=%USERPROFILE%\.cache\sccache"
if "%SCCACHE_CACHE_SIZE%"=="" set "SCCACHE_CACHE_SIZE=15G"
if "%CCACHE_DIR%"=="" set "CCACHE_DIR=%USERPROFILE%\.cache\ccache"
if "%CCACHE_MAXSIZE%"=="" set "CCACHE_MAXSIZE=15G"

set "ACTION=configure"
set "BUILD_DIR=out"
set "CONFIG=Release"

if /i "%~1"=="build" (
    set "ACTION=build"
    if not "%~2"=="" set "BUILD_DIR=%~2"
    if not "%~3"=="" set "CONFIG=%~3"
) else if /i "%~1"=="configure" (
    set "ACTION=configure"
    if not "%~2"=="" set "BUILD_DIR=%~2"
    if not "%~3"=="" set "CONFIG=%~3"
) else (
    if not "%~1"=="" set "BUILD_DIR=%~1"
    if not "%~2"=="" set "CONFIG=%~2"
)

if "%ACTION%"=="build" (
    if not exist "%BUILD_DIR%" (
        echo [ERROR] Build directory %BUILD_DIR% does not exist. Run configure first.
        exit /b 1
    )
    echo [INFO] Compiling exDesktop in %BUILD_DIR% (%CONFIG%)...
    cmake --build "%BUILD_DIR%" --config "%CONFIG%" --target Telegram
    exit /b %errorlevel%
)

:: Check for sccache / ccache
where sccache >nul 2>&1
if %errorlevel% equ 0 (
    echo [INFO] Detected sccache in PATH. Enabling object file caching in %SCCACHE_DIR%
    set "CACHE_FLAG=-DDESKTOP_APP_USE_COMPILER_CACHE=ON"
) else (
    where ccache >nul 2>&1
    if %errorlevel% equ 0 (
        echo [INFO] Detected ccache in PATH. Enabling object file caching in %CCACHE_DIR%
        set "CACHE_FLAG=-DDESKTOP_APP_USE_COMPILER_CACHE=ON"
    ) else (
        echo [INFO] Neither sccache nor ccache found in PATH.
        echo [TIP]  Install sccache (cargo install sccache or scoop install sccache) for 2x-5x faster rebuilds.
        set "CACHE_FLAG=-DDESKTOP_APP_USE_COMPILER_CACHE=OFF"
    )
)

if not "%TDESKTOP_API_ID%"=="" (
    set "API_ARGS=-DTDESKTOP_API_ID=%TDESKTOP_API_ID% -DTDESKTOP_API_HASH=%TDESKTOP_API_HASH%"
) else (
    set "API_ARGS=-DTDESKTOP_API_TEST=ON"
)

echo [INFO] Configuring CMake in %BUILD_DIR% (%CONFIG%)...
cmake -B "%BUILD_DIR%" ^
    -DCMAKE_BUILD_TYPE="%CONFIG%" ^
    %API_ARGS% ^
    %CACHE_FLAG%

if %errorlevel% neq 0 (
    echo [ERROR] CMake configuration failed.
    exit /b %errorlevel%
)

echo [INFO] Build directory configured.
echo [INFO] To compile, run: build_win.bat build %BUILD_DIR% %CONFIG%
echo [INFO] Or: cmake --build %BUILD_DIR% --config %CONFIG% --target Telegram
exit /b 0
