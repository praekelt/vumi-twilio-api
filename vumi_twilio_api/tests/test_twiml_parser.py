from twisted.trial.unittest import TestCase
from twilio import twiml
import xml.etree.ElementTree as ET

from vumi_twilio_api.twiml_parser import (
    TwiMLParser, TwiMLParseError, Verb, Play)


class TestVerb(TestCase):
    def test_verb_defaults(self):
        """Defaults are set correctly when no args are given"""
        verb = Verb()
        self.assertEqual(verb.name, "Verb")
        self.assertEqual(verb.attributes, {})
        self.assertEqual(verb.nouns, [])


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
        self.response.sms("Foobar")
        e = self.assertRaises(
            TwiMLParseError, self.parser.parse, str(self.response))
        self.assertEqual(e.args[0], "Cannot find parser for verb 'Sms'")

    def test_verb_parse(self):
        """The correct parse function is called when parsing"""
        def dummy_parser(element):
            return "dummy_parser"
        self.parser._parse_say = dummy_parser
        self.response.say("Foobar")
        [result] = self.parser.parse(str(self.response))
        self.assertEqual(result, "dummy_parser")

    def test_parse_play(self):
        self.response.play('test_url', loop=2, digits='123w')

        [result] = self.parser.parse(str(self.response))

        self.assertEqual(result.name, "Play")
        self.assertEqual(result.nouns, ["test_url"])
        self.assertEqual(result.attributes['loop'], 2)
        self.assertEqual(result.attributes['digits'], '123w')


class TestPlay(TestCase):
    def test_play_from_xml_defaults(self):
        """Defaults set according to API documentation"""
        root = ET.Element("Play")
        root.text = ''
        play = Play.from_xml(root)

        self.assertEqual(play.name, "Play")
        self.assertEqual(play.attributes['loop'], 1)
        self.assertEqual(play.attributes['digits'], None)
        self.assertEqual(play.nouns, [''])

    def test_play_from_xml_non_defaults(self):
        """Values are set according to what is specified in the XML"""
        root = ET.Element("Play", {'loop': '2', 'digits': '1234567890w'})
        root.text = 'url'
        play = Play.from_xml(root)

        self.assertEqual(play.name, "Play")
        self.assertEqual(play.attributes['loop'], 2)
        self.assertEqual(play.attributes['digits'], '1234567890w')
        self.assertEqual(play.nouns, ['url'])

    def test_play_from_xml_loop_non_int(self):
        """Error should be raised when loop attribute is not an integer"""
        root = ET.Element("Play", {'loop': 'a'})

        e = self.assertRaises(TwiMLParseError, Play.from_xml, root)
        self.assertEqual(
            str(e), "Invalid value 'a' for 'loop' attribute in Play verb. "
            "Must be an integer.")

    def test_play_from_xml_invalid_digits(self):
        """Error should be raised for digits attribute values not 0-9 and w"""
        root = ET.Element("Play", {'digits': '123wa123'})

        e = self.assertRaises(TwiMLParseError, Play.from_xml, root)
        self.assertEqual(
            str(e), "Invalid value '123wa123' for 'digits' attribute in Play"
            "verb. Must be one of '0123456789w'")
