#!/bin/sh

export PYTHONWARNINGS="ignore:Unverified HTTPS request"
cd /pretty-cool-events/src
python3 /pretty-cool-events/src/pretty-cool-events --config /pretty-cool-events/config.yaml
