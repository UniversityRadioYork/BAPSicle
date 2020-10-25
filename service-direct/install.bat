cd /D "%~dp0"
pip install -r requirements.txt
pip install -r requirements-windows.txt
pip install -e ..\
python windows_service.py install

mkdir "C:\Program Files\BAPSicle"
cd "C:\Program Files\BAPSicle\"
mkdir state

copy "C:\Program Files\Python37\Lib\site-packages\pywin32_system32\pywintypes37.dll" "C:\Program Files\Python37\Lib\site-packages\win32\"
TIMEOUT 10