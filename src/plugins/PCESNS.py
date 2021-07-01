
from outputplugin import OutputPlugin
from jinja2 import Template
import boto3

class PCESNS(OutputPlugin):
    template = Template('{{ event["event_type"] }}, {{ event["created_by"]["user"]["username"] }} from {{ event["action"]["src_ip"] }}. ')
    access_key = ''
    access_key_secret = ''

    def config(self, config):
        self.access_key = config['access_key'] 
        self.access_key_secret = config['access_key_secret'] 
        self.aws_region_name = config['aws_region_name']

        self.client = boto3.client(
            "sns",
            aws_access_key_id = self.access_key,
            aws_secret_access_key = self.access_key_secret,
            region_name = self.aws_region_name
        )

    def output(self, output):
        template_output = self.template.render(event=output)
        self.client.publish(PhoneNumber='004916092481632', Message=template_output)
