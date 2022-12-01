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
        if 'template' in config:
            self.template = config['template']
    
    def output(self, output, extra_data, template_globals):
        logging.debug("PCEPagerDuty: data: {}".format(output))
        logging.debug("PCEPagerDuty extra data: {}".format(extra_data))
        if 'template' in extra_data:
            template = extra_data['template']
        else:
            template = 'default.html'

        session = APISession(self.api_key)
        # create incident with pagerduty api
        # https://v2.developer.pagerduty.com/docs/send-an-event-events-api-v2
        # https://v2.developer.pagerduty.com/docs/send-an-event-events-api-v2#section-example-requests
        # https://v2.developer.pagerduty.com/docs/send-an-event-events-api-v2#section-example-responses
        # https://v2.developer.pagerduty.com/docs/send-an-event-events-api-v2#section-incident-creation
        session.rput('/incidents', data={ 'incident': { 'type': 'incident', 'title': 'PCE Alert', 'service': { 'id': 'P9ZQZ6C', 'type': 'service_reference' }, 'body': { 'type': 'incident_body', 'details': 'PCE Alert' } } })


        rtemplate = self.env.get_template(template)
        template_output = rtemplate.render(output)

        logging.debug("PCEPagerDuty: output: {}".format(template_output))
