#!/bin/bash
cd "$(dirname "$0")"

apt install libportaudio2

pip3 install -r requirements.txt
pip3 install -r requirements-linux.txt
pip3 install -e ..\

python3 ./generate-build-exe-config.py

python3 ./build-exe.py

bash ./build-exe-pyinstaller-command.sh

rm ./*.spec

