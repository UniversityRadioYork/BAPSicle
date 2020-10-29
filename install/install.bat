set install_path="C:\Program Files\BAPSicle"
set exe_name="BAPSicle.exe"
set exe_path=%install_path%\\%exe_name%
set service_name="BAPSicle"

mkdir %install_path%
mkdir %install_path%\state


cd %~dp0\nssm
nssm stop %service_name%
nssm remove %service_name% confirm
sc.exe delete %service_name%

cd %install_path%


copy /Y "%~dp0\uninstall.bat" .
copy /Y "%~dp0\..\build\output\%exe_name%" %exe_name%

mkdir nssm
cd nssm
copy /Y "%~dp0\nssm\nssm.exe" .
nssm install %service_name% %exe_path%
nssm set %service_name% AppDirectory %install_path%
nssm set %service_name% AppExit Default Restart
nssm set %service_name% AppStopMethodConsole 5000
nssm set %service_name% AppStopMethodWindow 5000
nssm set %service_name% AppStopMethodThreads 5000
nssm set %service_name% DisplayName "BAPSicle Server"
nssm set %service_name% Description "The next gen Broadcast and Presenting Suite server! Access settings on port 5000."
nssm set %service_name% ObjectName LocalSystem
nssm set %service_name% Start SERVICE_AUTO_START
nssm set %service_name% Type SERVICE_INTERACTIVE_PROCESS

: usefull tools are edit and dump:

: nssm edit %service_name%
: nssm dump %service_name%
nssm start %service_name%

timeout 4 /nobreak

explorer "http://localhost:5000/"
