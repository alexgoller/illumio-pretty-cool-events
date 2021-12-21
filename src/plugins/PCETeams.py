from outputplugin import OutputPlugin
import pymsteams
import logging
import json
from jinja2 import Template

class PCETeams(OutputPlugin):

    def config(self, config):
        if 'webhook' in config:
            self.webhook = config['webhook']
        if 'template' in config:
            self.template = config['template']
    
    def output(self, output, extra_data, template_globals):
        logging.debug("PCETeams: data: {}".format(output))
        logging.debug("Extra data: {}".format(extra_data))
        if 'template' in extra_data:
            template = extra_data['template']
        elif self.template:
            template = self.template
        else:
            template = 'default-teams.tmpl'

        rtemplate = self.env.get_template(template)
        template_output = rtemplate.render(event = output)

        teamsMessage = pymsteams.connectorcard(self.webhook)
        teamsMessage.color("ffffff")
        teamsMessage.text(template_output)
        teamsMessage.title("Pretty Cool Events Notification")

        logging.debug("PCETeams: output: {}".format(template_output))

        try:
            teamsMessage.send()
            logging.debug("Posted slack message: {}".format(template_output))
        except e:
            logging.debug("Exception caught: {}".format(e))
