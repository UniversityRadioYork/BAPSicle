#!/bin/bash
cd "$(dirname "$0")"

pip3 install -r requirements.txt
pip3 install -r requirements-macos.txt
pip3 install -e ..\

python3 ./generate-build-exe-config.py

python3 ./build-exe.py

bash ./build-exe-pyinstaller-command.sh

rm ./*.spec

brew install platypus

platypus --load-profile ./BAPSicle.platypus --overwrite ./output/BAPSicle.app
mkdir ./output/state
mkdir ./output/logs
mkdir ./output/music-tmp
