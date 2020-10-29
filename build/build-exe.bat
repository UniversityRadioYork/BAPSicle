cd /D "%~dp0"
pip install -r requirements.txt
pip install -r requirements-windows.txt
pip install -e ..\

: Generate the json config in case you wanted to use the gui to regenerate the command below manually.
python generate-build-exe-config.py

: auto-py-to-exe -c build-exe-config.json -o ../install

python build-exe.py

build-exe-pyinstaller-command.bat

del *.spec /q

echo "Output file should be located in 'output/' folder."
TIMEOUT 5