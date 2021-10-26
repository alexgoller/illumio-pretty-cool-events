from outputplugin import OutputPlugin
import logging
import json
from rest3client import RESTclient
from jinja2 import Template

class PCEServiceNow(OutputPlugin):

    def config(self, config):
        if 'instance' in config:
            self.instance = config['instance']

        if 'username' in config:
            self.username = config['username']

        if 'password' in config:
            self.password = config['password']
    
    def output(self, output, extra_data):
        logging.debug("PCEServiceNow: data: {}".format(output))
        logging.debug("Extra data: {}".format(extra_data))

        if 'template' in extra_data:
            template = extra_data['template']
        else:
            template = 'default.html'


        rtemplate = self.env.get_template(template)
        template_output = rtemplate.render(event = output)
        logging.debug("PCEServiceNow: output: {}".format(template_output))

        client = RESTclient(self.instance, username=self.username, password=self.password)
        payload = {
            'sysparm_action': 'insert',
            'category': 'network',
            'impact': '1',
            'urgency': '1',
            'short_description': output['event_type'],
            'comments': template_output
        }

        try:
            client.post('/incident.do?JSONv2', json=payload)
            logging.debug("Posted ServiceNow incident: {}".format(template_output))
        except e:
            logging.debug("Exception caught: {}".format(e))
