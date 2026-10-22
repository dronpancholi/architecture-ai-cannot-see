"""Plugin registry: delegates all dynamic loading to PluginLoader."""

from host.loader import PluginLoader


class Registry:
    def __init__(self, loader: PluginLoader):
        self.loader = loader
        self.plugins = []

    def install(self, name: str) -> None:
        plugin = self.loader.load_plugin(name)
        self.plugins.append(plugin)
