
import requests
import argparse
import yaml
from yaml.loader import SafeLoader
import os
import time
import logging
import sys

logging.basicConfig(stream=sys.stdout, level=logging.INFO)

# just --config being used right now
parser = argparse.ArgumentParser(description='Run the event loop!')
parser.add_argument('--config', help='Location of the config file', default = 'config.yml')
args = parser.parse_args()

if 'config' not in args:
    logging.warn("No config file given. Quitting")
    exit()


if os.path.exists(args.config):
    with open(args.config, 'r') as stream:
        try:
            logging.info("Reading config file: %s", args.config)
            data = yaml.load(stream, Loader=SafeLoader)
        except yaml.YAMLError as exc:
            logging.warn("Config file read error: %s", exc)
else:
    print("Can't open config file: ", args.config)
    exit()

config = data['config']

# main loop
logging.info("Entering main poll loop with interval: %s", config['pce_poll_interval'])
while True:
    time.sleep(config['pce_poll_interval'])
