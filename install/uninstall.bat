
set service_name="BAPSicle"

cd %~dp0\nssm
nssm stop %service_name%
nssm remove %service_name% confirm
sc.exe delete %service_name%

del "C:\Program Files\BAPSicle\" /q /s /f

PAUSE