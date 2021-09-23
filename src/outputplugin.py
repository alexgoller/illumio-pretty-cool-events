import jinja2

class OutputPlugin:
    # set this to true to get the PCE config credentials from the main pretty-cool-events config
    has_pce = False

    # does this need access to templates
    has_template = True

    def __init__(self):
        print("Do the init thing")

    def output(self, output):
        print("Output something")

    def config(self):
        print("Config something")
