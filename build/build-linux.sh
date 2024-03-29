#!/bin/bash
set -x
cd "$(dirname "$0")"

# Get the git commit / branch and write it into build.py.
build_commit="$(git rev-parse --short HEAD)"
build_branch="$(git branch --show-current)"
echo "BUILD: str = \"$build_commit\"" > ../build.py
echo "BRANCH: str = \"$build_branch\"" >> ../build.py

sudo apt install libportaudio2
sudo apt install python3-pip python3-venv ffmpeg

poetry install

poetry run python3 ./generate-build-exe-config.py

chmod +x output/BAPSicle

poetry run python3 ./build-exe.py

bash ./build-exe-pyinstaller-command.sh

rm ./*.spec

rm ../build.py

