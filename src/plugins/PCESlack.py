from outputplugin import OutputPlugin
import slack_sdk
import json
from jinja2 import Template

class PCESlack(OutputPlugin):
    slack_bot_token = ''

    def config(self, config):
        self.slack_bot_token = config['slack_bot_token']
        if 'template' in config:
            self.template = config['template']
    
    def output(self, output, extra_data):
        print("Extra data: {}".format(extra_data))
        if 'template' in extra_data:
            template = extra_data['template']
        else:
            template = 'default.html'

        if 'channel' in extra_data:
            channel = extra_data['channel']
        else:
            channel = '#pce'

        print("PCESlack: output: {}".format(output))
        client = slack_sdk.WebClient(token=self.slack_bot_token)

        rtemplate = self.env.get_template(template)
        template_output = rtemplate.render(output)

        try:
            response = client.chat_postMessage(
                    channel=channel,
                    blocks = template_output,
                    text = 'Foo'
            )
            print("Posted slack message: {}".format(template_output))
        except slack_sdk.errors.SlackApiError as e:
            print("Exception caught: {}".format(e))
            assert e.response["error"]
