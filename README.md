# illumio-pretty-cool-events

Illumio Pretty Cool Events aims to be a general notification mechanism that polls
the Illumio Core Events API to get the latest audit events from the Illumio Core PCE.

It will then call plugin actions based on a user configuration (config.yaml).

# Configuration

Configuration is done via a YAML config file, find a sample file in the
config.yaml.sample in the base directory.

# Available plugins (Work in progress)

* PCEStdout  - directly output events to stdout
* PCEMail    - email specific events
* PCESlack   - send to a slack channel or person
* PCESNS     - send SMS/text messages via Amazon SNS
* PCESyslog  - useful for SaaS instances or PoCs, poll the event API and send to syslog
* PCEWebhook - send custom webhooks (needs more work)
* PCETeams   - stub plugin, not functional - send to MS Teams



# Plugin architecture

Plugins can have a config block in the global config file, the config block
should have the same name as the Plugin class On init the config section under
the plugin class name is handed over to the plugins config method

# Template support

Every plugin inherits from OutputPlugin, which creates a jinja2 environment
that has a filesystem loader based on the templates directory.
That means any plugin can rely to load templates from the templates directory.

    template = self.env.get_template('filename')

You can then render the template with the event being handed over by the main
loop

    template.render(output)

# How to write your own plugin

* create a new plugin under plugins
* be sure to import outputplugin for the basic functionality
* populate your own methods with code

# TODO

Dockerfile for easy deployment.

# Ideas

* Plugin to execute local actions - e.g. git commit policy after each PCE provision
* Notify people on slack for problems in the PCE or process
* Get policy and check for constraints
* Do something useful with tampering events
* etc.
