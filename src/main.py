
import requests
import argparse
import yaml
from yaml.loader import SafeLoader
import os
import time
import logging
import sys
import pce
import json
import datetime
from straight.plugin import load

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

### watcher stuff
watchers = data['watchers']
print(type(watchers))

for watcher in watchers:
    print(watcher)

### check plugins
plugins = load('plugins')
print(plugins)

for plugin in plugins:
    try:
        plugin.output("Test")
    except:
        pass

pce = pce.IllumioPCE()
pce.pce = config['pce']
pce.pce_api_user = config['pce_api_user']
pce.pce_api_secret = config['pce_api_secret']
pce.pce_org = config['pce_org']
pce.client_init()



# main loop
logging.info("Entering main poll loop with interval: %s", config['pce_poll_interval'])
run = 0
current_date = 0

while True:
    payload = {'timestamp[gte]': current_date}
    if run == 0:
        r3c = pce.client.get('/api/v2/orgs/1/events')
    else:
        r3c = pce.client.get('/api/v2/orgs/1/events', params = payload)

    print(json.dumps(r3c, indent=2))
    # increment run parameter
    run = run+1
    current_date = datetime.datetime.now(datetime.timezone.utc).astimezone()
    time.sleep(config['pce_poll_interval'])
