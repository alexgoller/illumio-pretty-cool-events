from outputplugin import OutputPlugin
import slack_sdk
import logging
import json
from jinja2 import Template

class PCESlack(OutputPlugin):
    slack_bot_token = ''

    def config(self, config):
        self.slack_bot_token = config['slack_bot_token']
        if 'template' in config:
            self.template = config['template']
    
    def output(self, output, extra_data, template_globals):
        logging.debug("PCESlack: data: {}".format(output))
        logging.debug("Extra data: {}".format(extra_data))
        if 'template' in extra_data:
            template = extra_data['template']
        else:
            template = 'default.html'

        if 'channel' in extra_data:
            channel = extra_data['channel']
        else:
            channel = '#pce'

        client = slack_sdk.WebClient(token=self.slack_bot_token)

        rtemplate = self.env.get_template(template)
        template_output = rtemplate.render(output)

        logging.debug("PCESlack: output: {}".format(template_output))

        try:
            response = client.chat_postMessage(
                    channel=channel,
                    blocks = template_output,
                    text = 'Foo'
            )
            logging.debug("Posted slack message: {}".format(template_output))
        except slack_sdk.errors.SlackApiError as e:
            logging.debug("Exception caught: {}".format(e))
            assert e.response["error"]
