from jinja2 import Environment, FileSystemLoader, select_autoescape, Template
import logging
import json

class OutputPlugin:
    # set this to true to get the PCE config credentials from the main pretty-cool-events config
    has_pce = False

    # does this need access to templates
    has_template = True

    def __init__(self):
        # print python module name
        logging.info("{} - init()".format(self.__class__.__name__))
        self.env = Environment(loader=FileSystemLoader('../templates'), autoescape=select_autoescape(['html', 'xml']))
        self.env.filters['json_filter'] = json_filter


    def output(self, output):
        logging.info("Output something")

    def config(self):
        logging.info("Config something")

def json_filter(value):
                return json.dumps(value, indent=4, sort_keys=True, ensure_ascii=True)
