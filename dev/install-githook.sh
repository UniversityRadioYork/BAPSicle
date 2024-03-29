#!/bin/bash
poetry install
cd "$(dirname "$0")"
cp "./pre-commit" "../.git/hooks/"

