#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"

# Get the git commit / branch and write it into build.py.
build_commit="$(git rev-parse --short HEAD)"
build_branch="$(git branch --show-current)"
echo "BUILD: str = \"$build_commit\"" >../build.py
echo "BRANCH: str = \"$build_branch\"" >>../build.py

python3 -m venv ../venv
source ../venv/bin/activate

pip3 install wheel
pip3 install -r requirements.txt
pip3 install -r requirements-macos.txt
pip3 install -e ..
python3 ./generate-build-exe-config.py

python3 ./build-exe.py

bash ./build-exe-pyinstaller-command.sh

rm ./*.spec

cd ../
python3 build/generate-platypus-config.py
cd build

brew install platypus

platypus --load-profile ./BAPSicle.platypus --overwrite ./output/BAPSicle.app
chmod +x output/BAPSicle.app/Contents/Resources/BAPSicle

rm ../build.py
