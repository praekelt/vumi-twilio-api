class Verb(object):
    """Represents a single verb in TwilML. """

    def __init__(self, verb, attributes={}, nouns={}):
        self.verb = verb
        self.attributes = attributes
        self.nouns = nouns
