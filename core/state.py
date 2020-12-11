from typing import Dict


class SingletonByName(type):
    _by_name: Dict[str, "State"] = {}

    def __call__(cls, name: str, *args, **kwargs):
        if name in cls._by_name:
            # Return existing instance
            return cls._by_name[name]
        else:
            # Make new instance
            instance = super(SingletonByName, cls).__call__(name, *args, **kwargs)
            cls._by_name[name] = instance
            return instance


class State(dict, metaclass=SingletonByName):
    """
    A singleton-by-name dict-like state. First argument is the state name.

    If a State with a specific name was already instantiated, its instance will
    be returned (instead of making a new instance).

    Supports "instance.key = value" assignments.
    """
    def __init__(self, _name: str, *args, **kwargs):
        super(State, self).__init__(*args, **kwargs)

    def __setattr__(self, key, value):
        self[key] = value

    def __delattr__(self, item):
        del self[item]

    def __getattr__(self, item):
        return self[item]
