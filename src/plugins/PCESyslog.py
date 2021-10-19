from outputplugin import OutputPlugin
import logging.config
import ssl
import logging
import tlssyslog
from jinja2 import Template

class PCESyslog(OutputPlugin):
    template = Template('{{ event["event_type"] }}, {{ event["created_by"]["user"]["username"] }} from {{ event["action"]["src_ip"] }}. ')

    def config(self, config):
        if 'syslog_host' in config:
            self.syslog_host   = config['syslog_host']
        if 'syslog_port' in config:
            self.syslog_port   = config['syslog_port']
        if 'syslog_cert_file' in config:
            self.syslog_cert_file   = config['syslog_cert_file']

        if 'template' in config:
            self.template = config['template']

        mylogger = logging.Logger("PCESyslog")
        mylogger.setLevel(logging.INFO)
        
        th = tlssyslog.TLSSysLogHandler(address =(self.syslog_host, self.syslog_port))
        th.setLevel(logging.INFO)

        formatter = logging.Formatter("%(asctime)s django %(name)s: %(levelname)s %(message)s")
        th.setFormatter(formatter)
        mylogger.addHandler(th)
        self.logger = mylogger
        
    
    def output(self, output, extra_data):
        mylogger = self.logger
        mylogger.info(output)
        

