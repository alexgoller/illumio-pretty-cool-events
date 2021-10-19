
from execplugin import ExecPlugin

# stub, not functional

class PCEPolicyGit(ExecPlugin):
    def pce_config_handler(self, config):
        # TODO
        # handle a pce ocnfig
        return

    def config(self, config):
        if 'repo' in config:
            self.repo = config['repo']
        if 'policy_file' in config:
            self.policy_file = config['policy_file']
        else:
            policy_file = 'illumio_core_policy'

    def output(self,output, extra):
        return
