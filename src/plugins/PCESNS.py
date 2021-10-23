
from outputplugin import OutputPlugin
from jinja2 import Template
import boto3
import logging

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

    def output(self, output, extra_data):
        template = 'default.html'
        if 'template' in extra_data:
            template = extra_data['template']

        if 'phone_number' in extra_data:
            phone_number = extra_data['phone_number']
        else:
            logging.info("No phone number given. Not sending message")

        rtemplate = self.env.get_template(template)
        template_output = rtemplate.render(output)

        self.client.publish(PhoneNumber=phone_number, Message=template_output)
