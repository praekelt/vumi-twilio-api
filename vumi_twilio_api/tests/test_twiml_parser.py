from twisted.trial.unittest import TestCase
from twilio import twiml
import xml.etree.ElementTree as ET

from vumi_twilio_api.twiml_parser import TwiMLParser, TwiMLParseError, Verb


class TestVerb(TestCase):
    def test_verb_defaults(self):
        """Defaults are set correctly when no args are given"""
        verb = Verb("Say")
        self.assertEqual(verb.verb, "Say")
        self.assertEqual(verb.attributes, {})
        self.assertEqual(verb.nouns, {})


class TestParser(TestCase):
    def setUp(self):
        self.parser = TwiMLParser()
        self.response = twiml.Response()

    def test_invalid_root(self):
        """An invalid root raises an exception"""
        root = ET.Element('foobar')
        xml = ET.tostring(root)
        e = self.assertRaises(TwiMLParseError, self.parser.parse, xml)
        self.assertEqual(
            e.args[0], "Invalid root 'foobar'. Should be 'Request'.")

    def test_default_parse(self):
        """The default parse function is called when a verb parser cannot be
        found"""
        if getattr(self.parser, '_parse_Say', None):
            self.parser._parse_Say = None
        self.response.say("Foobar")
        e = self.assertRaises(
            TwiMLParseError, self.parser.parse, str(self.response))
        self.assertEqual(e.args[0], "Cannot find parser for verb 'Say'")

    def test_verb_parse(self):
        """The correct parse function is called when parsing"""
        def dummy_parser(element):
            return "dummy_parser"
        self.parser._parse_Say = dummy_parser
        self.response.say("Foobar")
        [result] = self.parser.parse(str(self.response))
        self.assertEqual(result, "dummy_parser")
