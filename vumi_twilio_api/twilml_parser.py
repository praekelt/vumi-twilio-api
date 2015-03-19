import xml.etree.ElementTree as ET


class Verb(object):
    """Represents a single verb in TwilML. """

    def __init__(self, verb, attributes={}, nouns={}):
        self.verb = verb
        self.attributes = attributes
        self.nouns = nouns


class TwilMLParseError(Exception):
    """Raised when trying to parse invalid TwilML"""


class TwilMLParser(object):
    """Parser for TwilML"""

    def parse_xml(self, xml):
        """Parses TwilML and returns a list of :class:`Verb` objects"""
        verbs = []
        root = ET.fromstring(xml)
        if root.tag != "Response":
            raise TwilMLParseError(
                "Invalid root %r. Should be 'Request'." % root.tag)
        for child in root:
            parser = getattr(
                self, '_parse_%s' % child.tag, self._parse_default)
            verbs.append(parser(child))
        return verbs

    def _parse_default(self, element):
        raise TwilMLParseError("Unable to parse verb %r" % element.tag)
