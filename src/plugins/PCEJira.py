from outputplugin import OutputPlugin
from jira import JIRA
import logging
import json
from jinja2 import Template

class PCEJira(OutputPlugin):

    def config(self, config):
        if 'jira_server' in config:
            self.jira_server = config['jira_server']

        if 'username' in config:
            self.username = config['username']

        if 'api_token' in config:
            self.api_token = config['api_token']

        if 'project' in config:
            self.project = config['project']

        if 'template' in config:
            self.template = config['template']
    
    def output(self, output, extra_data):
        logging.debug("PCEJira: data: {}".format(output))
        logging.debug("Extra data: {}".format(extra_data))

        if 'template' in extra_data:
            template = extra_data['template']
        else:
            template = 'default.html'


        rtemplate = self.env.get_template(template)
        template_output = rtemplate.render(event = output)
        logging.debug("PCEJira: output: {}".format(template_output))

        jira = JIRA(server = self.jira_server, basic_auth=(self.username, self.api_token))
        issue_params = { 'project': {'key': self.project }, 'description': template_output, 'summary': output['event_type'], 'issuetype': {'name': 'Task'} }


        try:
            jira.create_issue(fields=issue_params)
            logging.debug("Posted slack message: {}".format(template_output))
        except e:
            logging.debug("Exception caught: {}".format(e))
