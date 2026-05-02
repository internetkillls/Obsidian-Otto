@echo off
setlocal

if defined OTTO_QMD_WSL_DISTRO (
  wsl.exe -d "%OTTO_QMD_WSL_DISTRO%" -- /usr/bin/qmd %*
) else (
  wsl.exe -d Ubuntu -- /usr/bin/qmd %*
)
