#!/bin/bash
set -x
cd "$(dirname "$0")"

# Get the git commit / branch and write it into build.py.
build_commit="$(git rev-parse --short HEAD)"
build_branch="$(git branch --show-current)"
echo "BUILD: str = \"$build_commit\"" > ../build.py
echo "BRANCH: str = \"$build_branch\"" >> ../build.py

poetry install

poetry run python3 ./generate-build-exe-config.py

poetry run python3 ./build-exe.py

bash ./build-exe-pyinstaller-command.sh

rm ./*.spec

cd ../
poetry run python3 build/generate-platypus-config.py
cd build

brew install platypus

platypus --load-profile ./BAPSicle.platypus --overwrite ./output/BAPSicle.app
chmod +x output/BAPSicle.app/Contents/Resources/BAPSicle

rm ../build.py
