import xml.etree.ElementTree as ET


class Verb(object):
    """Represents a single verb in TwilML. """

    def __init__(self, verb, attributes={}, nouns={}):
        self.verb = verb
        self.attributes = attributes
        self.nouns = nouns


class TwiMLParseError(Exception):
    """Raised when trying to parse invalid TwilML"""


class TwiMLParser(object):
    """Parser for TwiML"""

    def parse(self, xml):
        """Parses TwiML and returns a list of :class:`Verb` objects"""
        verbs = []
        root = ET.fromstring(xml)
        if root.tag != "Response":
            raise TwiMLParseError(
                "Invalid root %r. Should be 'Request'." % root.tag)
        for child in root:
            parser = getattr(
                self, '_parse_%s' % child.tag, self._parse_default)
            verbs.append(parser(child))
        return verbs

    def _parse_default(self, element):
        raise TwiMLParseError("Cannot find parser for verb %r" % element.tag)
