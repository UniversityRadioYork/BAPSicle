#!/bin/bash
pip3 install autopep8
cd "$(dirname "$0")"
cp "./pre-commit" "../.git/hooks/"

