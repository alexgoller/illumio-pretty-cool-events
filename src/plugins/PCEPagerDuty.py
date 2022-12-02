from outputplugin import OutputPlugin
import pdpyras
import logging
import json
from jinja2 import Template
from pdpyras import APISession

class PCEPagerDuty(OutputPlugin):

    # copied from slack
    def config(self, config):
        self.api_key = config['api_key']
        if 'pd_from' in config:
            self.pager_duty_from = config['pd_from']

        if 'template' in config:
            self.template = config['template']

        if 'pd_from' in config:
            self.pd_from = config['pd_from']
            
        if 'pd_priority' in config:
            self.pd_from = config['pd_priority']

        if 'pd_service' in config:
            self.pd_from = config['pd_service']
    
    def output(self, output, extra_data, template_globals):
        logging.debug("PCEPagerDuty: data: {}".format(output))
        logging.debug("PCEPagerDuty extra data: {}".format(extra_data))
        if 'template' in extra_data:
            template = extra_data['template']
        else:
            template = self.template

        session = APISession(self.api_key, default_from='alex@ryte.de')
        # session.rpost('/incidents', data={ 'incident': { 'type': 'incident', 'title': 'PCE Alert', 'priority': { 'id': 'P7I8BQT', 'type': 'priority_reference' }, 'service': { 'id': 'P1535BG', 'type': 'service_reference' }, 'body': { 'type': 'incident_body', 'details': 'Foo' }}} )


        rtemplate = self.env.get_template(template)
        template_output = rtemplate.render(output)

        session.rpost('/incidents', json={ 'incident': { 'type': 'incident', 'title': 'PCE Alert', 'priority': { 'id': self.pd_priority, 'type': 'priority_reference' }, 'service': { 'id': self.pd_service, 'type': 'service_reference' }, 'body': { 'type': 'incident_body', 'details': template_output }}} )

        logging.debug("PCEPagerDuty: output: {}".format(template_output))
