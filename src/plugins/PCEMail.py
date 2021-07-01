from outputplugin import OutputPlugin
import smtplib
from jinja2 import Template
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

class PCEMail(OutputPlugin):
    smtp_user = ''
    smtp_host = ''
    smtp_password = ''
    smtp_port = 25

    template = Template('{{ event["event_type"] }}, {{ event["created_by"]["user"]["username"] }} from {{ event["action"]["src_ip"] }}. ')

    def config(self, config):
        if 'smtp_user' in config:
            self.smtp_user     = config['smtp_user']
        if 'smtp_password' in config:
            self.smtp_password = config['smtp_password']
        if 'smtp_host' in config:
            self.smtp_host     = config['smtp_host']
        if 'smtp_port' in config:
            self.smtp_port     = config['smtp_host']

        if 'template' in config:
            self.template = config['template']
    
    def output(self, output):
        template_output = self.template.render(event=output)
        msg = MIMEMultipart()
        message = template_output
        smtphost = self.smtp_host
        try:
            msg['From'] = "alex@ryte.de"
            msg['To'] = "alex@ryte.de"
            msg['Subject'] = "Pretty-Cool-Events Notification"
            msg.attach(MIMEText(message, 'plain'))
            server = smtplib.SMTP(self.smtp_host)
            server.starttls()
            server.login(self.smtp_user, self.smtp_password)
            server.sendmail(msg['From'], msg['To'], msg.as_string())
            server.quit()
            print("Successfully sent email message to %s:" % (msg['To']))
        except smtplib.SMTPException as e:
            print("Exception:", e)
