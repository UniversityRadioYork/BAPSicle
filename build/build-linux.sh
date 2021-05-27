#!/bin/bash
cd "$(dirname "$0")"

# Get the git commit / branch and write it into build.py.
build_commit="$(git rev-parse --short HEAD)"
build_branch="$(git branch --show-current)"
echo "BUILD: str = \"$build_commit\"" > ../build.py
echo "BRANCH: str = \"$build_branch\"" >> ../build.py

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

rm ../build.py

