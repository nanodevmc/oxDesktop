__version__ = "1.4.6.5"
version = (1, 4, 6, 5)
version_str = __version__
__beta__ = False
beta = __beta__


class SafeModeImporter:
    IS_OLD_VERSION = False
    I = True
    E = False

    @classmethod
    def c(cls):
        return None


Z = SafeModeImporter.INSTANCE = SafeModeImporter()
