from outputplugin import OutputPlugin
import requests
import json

class PCEWebhook(OutputPlugin):

    def config(self,config):
        if 'bearer_token' in config:
            self.bearer_token = config['bearer_token']
        if 'url' in config:
            self.url = config['url']
        if 'data' in config:
            self.data = config['data']

    def output(self,output, extra_data):
        data = output
        r = requests.post(self.url, data=json.dumps(data), 
                          headers={'Content-Type': 'application/json'})
