#!/usr/bin/env python3

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
import threading
from flask import Flask
from outputplugin import OutputPlugin
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
plugins = load('plugins', subclasses=OutputPlugin)
handlers = plugins.produce()

# print("Handlers:")
# for handler in handlers:
#     print(handler)
#     print(dir(handler))
#     print(handler.__class__.__name__)

# setup configs for handlers/plugins
for handler in handlers:
    handler.config(config['plugin_config'][handler.__class__.__name__])

pce = pce.IllumioPCE()
pce.pce = config['pce']
pce.pce_api_user = config['pce_api_user']
pce.pce_api_secret = config['pce_api_secret']
pce.pce_org = config['pce_org']
pce.client_init()


# def flaskTask():
#     app = Flask('pretty-cool-events')

# @app.route("/")
# def pceMain():
#     return "<p>Hello World!</p>"

# main loop
def main():
    logging.info("Entering main poll loop with interval: %s", config['pce_poll_interval'])
    run = 0
    current_date = 0
    
    current_date = datetime.datetime.now(datetime.timezone.utc).astimezone()
    
    while True:
        payload = {'timestamp[gte]': current_date}
        r3c = pce.client.get('/api/v2/orgs/1/events', params = payload)
    
        for event in r3c:
            if event['event_type'] in watchers:
                print("Matching event type:", event['event_type'])
    
                # check if status matches
                if event['status'] == watchers[event['event_type']]['status']:
                    print("Hooray, even the status matches... Now decide what to do with it!")
                    plugin_name = ''
                    if 'plugin' in watchers[event['event_type']]:
                        print("Found matching plugin:", watchers[event['event_type']]['plugin'])
                        plugin_name = watchers[event['event_type']]['plugin']
                    for handler in handlers:
                        if handler.__class__.__name__ == plugin_name:
                            handler.output(event)
    
        # increment run parameter
        run = run+1
        current_date = datetime.datetime.now(datetime.timezone.utc).astimezone()
        time.sleep(config['pce_poll_interval'])

threading.Thread(target=main).start()
# threading.Thread(target=flaskTask).start()

