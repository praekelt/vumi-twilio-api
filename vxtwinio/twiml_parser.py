import re
from urlparse import urljoin
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
        loop = check_integer('loop', loop, 0)

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


class Hangup(Verb):
    """Represents the Hangup verb"""
    name = "Hangup"

    @classmethod
    def from_xml(cls, xml):
        """Returns a new Hangup verb from the given ElementTree object"""
        return cls()


def check_integer(name, integer, minimum=None):
    """Raises the appropriate error if the value cannot be cast to an int.
    If minimum is present, raises the appropriate error if the value is less
    than minimum.

    Returns the processed integer"""
    try:
        integer = int(integer)
    except ValueError:
        raise TwiMLParseError(
            "Invalid value %r for %s parameter. Must be an integer."
            % (integer, name))
    if minimum is not None and integer < minimum:
        raise TwiMLParseError(
            "Invalid value %r for %s parameter. Must be >= %s"
            % (integer, name, minimum))
    return integer


class Gather(Verb):
    """Represents the Gather verb"""
    name = "Gather"

    @classmethod
    def from_xml(cls, xml, url):
        """Returns a new Gather verb from the given ElementTree object.
        The URL is the document url, used as the default action URL."""
        action = xml.attrib.get('action', None)
        action = urljoin(url, action)

        valid_methods = ['GET', 'POST']
        method = xml.attrib.get('method', 'POST')
        if method not in valid_methods:
            raise TwiMLParseError(
                "Invalid value %r for method attribute. Must be one of %r" % (
                    method, valid_methods))

        timeout = xml.attrib.get('timeout', 5)
        timeout = check_integer('timeout', timeout, 0)

        finishOnKey = xml.attrib.get('finishOnKey', '#')
        if len(finishOnKey) > 1:
            raise TwiMLParseError(
                "Invalid value %r for finishOnKey parameter. "
                "Must only be one character" % finishOnKey)
        valid_chars = "0123456789#*"
        if finishOnKey not in valid_chars:
            raise TwiMLParseError(
                "Invalid value %r for finishOnKey parameter. "
                "Must be one of %r" % (finishOnKey, valid_chars))

        numDigits = xml.attrib.get('numDigits', None)
        if numDigits is not None:
            numDigits = check_integer('numDigits', numDigits, 1)

        data = TwiMLParser.from_list(xml, url)
        valid_verbs = ['Say', 'Play']
        for verb in data:
            if verb.name not in valid_verbs:
                raise TwiMLParseError(
                    "Invalid sub verb %r for Gather verb. Must be one of %r"
                    % (verb.name, valid_verbs))

        return cls({
            'action': action,
            'method': method,
            'timeout': timeout,
            'finishOnKey': finishOnKey,
            'numDigits': numDigits,
            }, data)


class TwiMLParseError(Exception):
    """Raised when trying to parse invalid TwilML"""


class TwiMLParser(object):
    """Parser for TwiML"""
    def __init__(self, url):
        self.url = url

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

    @classmethod
    def from_list(cls, lst, url):
        self = cls(url)
        verbs = []
        for child in lst:
            parser = getattr(
                self, '_parse_%s' % child.tag.lower(), self._parse_default)
            verbs.append(parser(child))
        return verbs

    def _parse_default(self, element):
        raise TwiMLParseError("Cannot find parser for verb %r" % element.tag)

    def _parse_play(self, element):
        return Play.from_xml(element)

    def _parse_hangup(self, element):
        return Hangup.from_xml(element)

    def _parse_gather(self, element):
        return Gather.from_xml(element, self.url)
