import re
import xml.etree.ElementTree as ET


class Verb(object):
    """Represents a single verb in TwilML. """
    name = "Verb"

    def __init__(self, attributes={}, nouns=[]):
        self.attributes = attributes
        self.nouns = nouns

class Play(Verb):
    """Represents the Play verb"""
    name = "Play"
    digits_re = re.compile('[0-9w]')

    @classmethod
    def from_xml(cls, xml):
        """Returns a new Play Verb given an ElementTree object"""
        nouns = [xml.text]

        loop = xml.attrib.get('loop', 1)
        try:
            loop = int(loop)
        except ValueError:
            raise TwiMLParseError(
                "Invalid value %r for 'loop' attribute in Play verb. "
                "Must be an integer."  % loop)

        digits = xml.attrib.get('digits')
        if not all(cls.digits_re.match(c) for c in (digits or '')):
            raise TwiMLParseError(
                "Invalid value %r for 'digits' attribute in Play verb. "
                "Must be one of '0123456789w'" % digits)

        attributes = {
            'loop': loop,
            'digits': digits,
        }
        return cls(attributes, nouns)


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
                self, '_parse_%s' % child.tag.lower(), self._parse_default)
            verbs.append(parser(child))
        return verbs

    def _parse_default(self, element):
        raise TwiMLParseError("Cannot find parser for verb %r" % element.tag)
