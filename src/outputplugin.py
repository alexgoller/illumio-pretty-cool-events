from jinja2 import Environment, FileSystemLoader, select_autoescape, Template

class OutputPlugin:
    def __init__(self):
        print("Do the init thing")
        self.env = Environment(loader=FileSystemLoader('../templates'), autoescape=select_autoescape(['html', 'xml']))

    def output(self, output):
        print("Output something")

    def config(self):
        print("Config something")
