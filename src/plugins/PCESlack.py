import slack_sdk
import json
from jinja2 import Template
from outputplugin import OutputPlugin

class PCESlack(OutputPlugin):
    slack_bot_token = ''
    template = Template('{{ event["event_type"] }}, {{ event["created_by"]["user"]["username"] }} from {{ event["action"]["src_ip"] }}. ')

    def config(self, config):
        self.slack_bot_token = config['slack_bot_token']
        if 'template' in config:
            self.template = config['template']
    
    def output(self, output):
        client = slack_sdk.WebClient(token=self.slack_bot_token)
        template_output = self.template.render(event=output)

        try:
            response = client.chat_postMessage(
                    channel="#pce",
                    text=template_output
                )
        except SlackApiError as e:
            assert e.response["error"]
