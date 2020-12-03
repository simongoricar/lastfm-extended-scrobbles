class AnalysisException(Exception):
    """
    Base exception for all other custom exceptions.
    """
    pass


class ConfigException(AnalysisException):
    """
    Raised when an error occurs in the configuration file.
    """
    pass
