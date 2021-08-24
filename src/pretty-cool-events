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
import regex
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


app = Flask('pretty-cool-events')

def flaskTask():
    if 'httpd_listener_address' in config:
        address = config['httpd_listener_address']
    else:
        address = '0.0.0.0'

    if 'httpd_listener_port' in config:
        flask_port = config['httpd_listener_port']
    else:
        flask_port = 8443

    app.run(host=address, port=flask_port)

@app.route("/")
def pceMain():
    return "<p>Pretty cool events</p>"

@app.route("/watchers")
def pceWatchers():
    return str(watchers)

# @app.route("/config")
# def pceConfig():
#     return str(config)

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
            template = config['default_template']
            if event['event_type'] in watchers:
                print("Matching event type:", event['event_type'])

                for w in watchers[event['event_type']]:
                    if event['status'] == w['status']:
                        print("Hooray, even the status matches... Now decide what to do with it!")
                        plugin_name = ''
                        if 'plugin' in w:
                            print("Found matching plugin:", w['plugin'])
                            plugin_name = w['plugin']
                        if 'template' in w:
                            template = w['template']

                        for handler in handlers:
                            if handler.__class__.__name__ == plugin_name:
                                handler.output(event, template=template)
            else:
                evt = event['event_type']
                for key, watcher in watchers.items():
                    if evt.startswith(key):
                        for w in watchers[key]:
                            if event['status'] == w['status']:
                                plugin_name = ''
                                if 'template' in w:
                                    template = w['template']
                                if 'plugin' in w:
                                    print("Found matching plugin:", w['plugin'])
                                    plugin_name = w['plugin']
                                    for handler in handlers:
                                        if handler.__class__.__name__ == plugin_name:
                                            handler.output(event, template=template)

    
        # increment run parameter
        run = run+1
        current_date = datetime.datetime.now(datetime.timezone.utc).astimezone()
        time.sleep(config['pce_poll_interval'])

logging.info("Starting main task.")
threading.Thread(target=main).start()

if config['httpd']:
    logging.info("Starting httpd task.")
    threading.Thread(target=flaskTask).start()

