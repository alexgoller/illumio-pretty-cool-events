from outputplugin import OutputPlugin

class PCEStdout(OutputPlugin):
    prepend_str = ''
    append_str = ''
    def config(self,config):
        print("Plugin config handler reached!")
        if config['prepend']:
            self.prepend_str = config['prepend']
    
    def output(self, output):
        # output function, do output stuff here
        print("Plugin output handler reached!")
        print(self.prepend_str, output)
