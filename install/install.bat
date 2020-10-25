mkdir "C:\Program Files\BAPSicle"
cd "C:\Program Files\BAPSicle\"
mkdir state

copy /Y "%~dp0\BAPSicle.exe" "BAPSicle.exe"

%~dp0nssm\nssm.exe remove BAPSicle confirm
%~dp0nssm\nssm.exe install BAPSicle .\BAPSicle.exe
TIMEOUT 5