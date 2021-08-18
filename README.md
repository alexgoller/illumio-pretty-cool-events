# illumio-pretty-cool-events

# Plugin architecture

Plugins can have a config block in the global config file, the config block
should have the same name as the Plugin class On init the config section under
the plugin class name is handed over to the plugins config method

# How to write your own plugin

* create a new plugin under plugins
* be sure to import outputplugin for the basic functionality
* populate your own methods with code

