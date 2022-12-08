from outputplugin import OutputPlugin
import pprint
import logging

class PCEFile(OutputPlugin):
    prepend_str = ''
    append_str = ''
    def config(self,config):
        logging.info("Plugin config handler reached!")
        if 'prepend' in config:
            self.prepend_str = config['prepend']
        if 'logfile' in config:
            self.logfile = config['logfile']
    
    def output(self, output, extra_data, template_globals):
        # output function, do output stuff here
        if 'template' in extra_data:
            rtemplate = self.env.get_template(extra_data['template'])
            print(rtemplate)
        else:
            rtemplate = self.env.get_template('default.html')


        try:
            with open(self.logfile, "a+") as logfile:
                print(pprint.pprint(output))
                print("Plugin output handler reached!")
                logfile.write(rtemplate.render(output))
        except Exception:
                logging.info("Error writing to file: {}".format(self.logfile))
        finally:
            logfile.close()
