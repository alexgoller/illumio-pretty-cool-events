from outputplugin import OutputPlugin
import pprint
import logging

class PCEStdout(OutputPlugin):
    prepend_str = ''
    append_str = ''
    def config(self,config):
        print("Plugin config handler reached!")
        if 'prepend' in config:
            self.prepend_str = config['prepend']
    
    def output(self, output, extra_data):
        # output function, do output stuff here
        if 'template' in extra_data:
            rtemplate = self.env.get_template(extra_data['template'])
            print(rtemplate)
        else:
            rtemplate = self.env.get_template('default.html')


        print(pprint.pprint(output))
        print("Plugin output handler reached!")
        print(rtemplate.render(output))
