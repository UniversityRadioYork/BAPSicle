cd /D "%~dp0"
pip install -r requirements.txt
pip install -r requirements-windows.txt
pip install -e ..\

python generate-build-exe-config.py

auto-py-to-exe -c build-exe-config.json -o ../install 

TIMEOUT 5