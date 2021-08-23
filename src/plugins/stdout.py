from outputplugin import OutputPlugin
import pprint

class PCEStdout(OutputPlugin):
    prepend_str = ''
    append_str = ''
    def config(self,config):
        print("Plugin config handler reached!")
        if config['prepend']:
            self.prepend_str = config['prepend']
    
    def output(self, output, template='default.html'):
        # output function, do output stuff here
        template = self.env.get_template(template)
        print(template)

        print(pprint.pprint(output))
        print("Plugin output handler reached!")
        print(template.render(output))
