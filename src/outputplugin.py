from jinja2 import Environment, FileSystemLoader, select_autoescape, Template
import logging

class OutputPlugin:
    # set this to true to get the PCE config credentials from the main pretty-cool-events config
    has_pce = False

    # does this need access to templates
    has_template = True

    def __init__(self):
        # print python module name
        print("{} - init()".format(self.__class__.__name__))
        self.env = Environment(loader=FileSystemLoader('../templates'), autoescape=select_autoescape(['html', 'xml']))

    def output(self, output):
        print("Output something")

    def config(self):
        print("Config something")
