#!/bin/bash
cd "$(dirname "$0")"

build_commit="$(git rev-parse --short HEAD)"
echo "BUILD: str = \"$build_commit\"" > ../build.py

apt install libportaudio2

python3 -m venv ../venv
source ../venv/bin/activate

pip3 install -r requirements.txt
pip3 install -r requirements-linux.txt
pip3 install -e ../

python3 ./generate-build-exe-config.py

python3 ./build-exe.py

bash ./build-exe-pyinstaller-command.sh

rm ./*.spec

