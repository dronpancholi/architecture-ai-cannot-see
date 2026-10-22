"""Plugin loader: the only place allowed to perform dynamic imports."""

import importlib


class PluginLoader:
    def load_plugin(self, name: str):
        module = importlib.import_module(f"plugins.{name}")
        return module.register()
