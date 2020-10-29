
set service_name="BAPSicle"

: We can't 'nssm stop because' we're about to delete it.
: The file will remain open, so you'll get access denied.
net stop %service_name%
sc delete %service_name%

: We cd out of the folder, just in case we're about to delete
: out PWD.
cd \
rmdir "C:\Program Files\BAPSicle\" /q /s


PAUSE