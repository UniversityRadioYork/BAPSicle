#!/bin/bash
brew install tcl

pip3 install -r requirements.txt
pip3 install -r requirements-macos.txt
pip3 install -e ..\

python3 ./generate-build-exe-config.py

python3 ./build-exe.py

bash ./build-exe-pyinstaller-command.sh
