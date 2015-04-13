from twisted.trial.unittest import TestCase
from twilio import twiml
import xml.etree.ElementTree as ET

from vumi_twilio_api.twiml_parser import (
    TwiMLParser, TwiMLParseError, Verb, Play, Hangup, Gather)


class TestVerb(TestCase):
    def test_verb_defaults(self):
        """Defaults are set correctly when no args are given"""
        verb = Verb()
        self.assertEqual(verb.name, "Verb")
        self.assertEqual(verb.attributes, {})
        self.assertEqual(verb.nouns, [])


class TestParser(TestCase):
    def setUp(self):
        self.parser = TwiMLParser('test_url')
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
        """The play verb is correctly parsed and returned"""
        self.response.play('test_url', loop=2, digits='123w')

        [result] = self.parser.parse(str(self.response))

        self.assertEqual(result.name, "Play")
        self.assertEqual(result.nouns, ["test_url"])
        self.assertEqual(result.attributes['loop'], 2)
        self.assertEqual(result.attributes['digits'], '123w')

    def test_parse_hangup(self):
        """The hangup verb is correctly parsed and returned"""
        self.response.hangup()
        [result] = self.parser.parse(str(self.response))

        self.assertEqual(result.name, "Hangup")
        self.assertEqual(result.nouns, [])
        self.assertEqual(result.attributes, {})

    def test_parse_gather(self):
        """The gather verb is correctly parsed and returned"""
        with self.response.gather() as g:
            g.play('play_url')
        [result] = self.parser.parse(str(self.response))

        self.assertEqual(result.name, 'Gather')
        self.assertEqual(result.attributes['finishOnKey'], '#')
        self.assertEqual(result.nouns[0].name, 'Play')


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
            str(e), "Invalid value '123wa123' for 'digits' attribute in Play "
            "verb. Must be one of '0123456789w'")


class TestHangup(TestCase):
    def test_hangup_from_xml(self):
        """There are no attributes or nouns for the hangup verb"""
        root = ET.Element("Hangup")
        hangup = Hangup.from_xml(root)
        self.assertEqual(hangup.name, "Hangup")
        self.assertEqual(hangup.nouns, [])
        self.assertEqual(hangup.attributes, {})


class TestGather(TestCase):
    def test_gather_from_xml_defaults(self):
        """The correct defaults must be set for the Gather verb"""
        root = ET.Element("Gather")
        gather = Gather.from_xml(root, 'test_url')
        self.assertEqual(gather.name, "Gather")
        self.assertEqual(gather.nouns, [])
        self.assertEqual(gather.attributes['action'], 'test_url')
        self.assertEqual(gather.attributes['method'], 'POST')
        self.assertEqual(gather.attributes['timeout'], 5)
        self.assertEqual(gather.attributes['finishOnKey'], '#')
        self.assertEqual(gather.attributes['numDigits'], None)

    def test_gather_from_xml_non_defaults(self):
        """The values must be set according to the supplied values"""
        root = ET.Element("Gather", {
            'action': 'action_url',
            'method': 'GET',
            'timeout': 1,
            'finishOnKey': '*',
            'numDigits': 5})
        gather = Gather.from_xml(root, 'test_url')
        self.assertEqual(gather.name, "Gather")
        self.assertEqual(gather.nouns, [])
        self.assertEqual(gather.attributes['action'], 'action_url')
        self.assertEqual(gather.attributes['method'], 'GET')
        self.assertEqual(gather.attributes['timeout'], 1)
        self.assertEqual(gather.attributes['finishOnKey'], '*')
        self.assertEqual(gather.attributes['numDigits'], 5)

    def test_gather_from_xml_relative_url(self):
        """The url must be relative to the root URL if action is relative"""
        root = ET.Element("Gather", {'action': '/suburl'})
        gather = Gather.from_xml(root, 'http://test_url')
        self.assertEqual(gather.attributes['action'], 'http://test_url/suburl')

    def test_gather_from_xml_invalid_method(self):
        """Should raise an exception if the method parameter is invalid"""
        root = ET.Element("Gather", {'method': 'foobar'})
        e = self.assertRaises(
            TwiMLParseError, Gather.from_xml, root, 'test_url')
        self.assertEqual(
            str(e), "Invalid value 'foobar' for method attribute. "
            "Must be one of ['GET', 'POST']")

    def test_gather_from_xml_nonint_timeout(self):
        """Should raise an exception for non integer values for timeout."""
        root = ET.Element("Gather", {'timeout': 'a'})
        e = self.assertRaises(
            TwiMLParseError, Gather.from_xml, root, 'test_url')
        self.assertEqual(
            str(e), "Invalid value 'a' for timeout parameter. "
            "Must be an integer.")

    def test_gather_from_xml_negative_timeout(self):
        """Should raise an exception for negative values of timeout"""
        root = ET.Element("Gather", {'timeout': -1})
        e = self.assertRaises(
            TwiMLParseError, Gather.from_xml, root, 'test_url')
        self.assertEqual(
            str(e), "Invalid value -1 for timeout parameter. "
            "Must be positive")

    def test_gather_from_xml_finishonkey_multiple_chars(self):
        """Should raise an exception for multiple chars in finishOnKey value"""
        root = ET.Element("Gather", {'finishOnKey': 'foo'})
        e = self.assertRaises(
            TwiMLParseError, Gather.from_xml, root, 'test_url')
        self.assertEqual(
            str(e), "Invalid value 'foo' for finishOnKey parameter. "
            "Must only be one character")

    def test_gather_from_xml_finishonkey_invalid_char(self):
        """Should raise an exception for invalid chars in finishOnKey value"""
        root = ET.Element("Gather", {'finishOnKey': 'a'})
        e = self.assertRaises(
            TwiMLParseError, Gather.from_xml, root, 'test_url')
        self.assertEqual(
            str(e), "Invalid value 'a' for finishOnKey parameter. "
            "Must be one of '0123456789#*'")

    def test_gather_from_xml_numdigits_nonint(self):
        """Should raise an exception for non integer values in numDigits"""
        root = ET.Element("Gather", {'numDigits': 'foo'})
        e = self.assertRaises(
            TwiMLParseError, Gather.from_xml, root, 'test_url')
        self.assertEqual(
            str(e), "Invalid value 'foo' for numDigits parameter. "
            "Must be an integer.")

    def test_gather_from_xml_numdigits_less_than_one(self):
        """Should raise an exception for <1 values in numDigits"""
        root = ET.Element("Gather", {'numDigits': 0})
        e = self.assertRaises(
            TwiMLParseError, Gather.from_xml, root, 'test_url')
        self.assertEqual(
            str(e), "Invalid value 0 for numDigits parameter. "
            "Must be >=1")

    def test_gather_from_xml_valid_sub_verbs(self):
        """Should have valid sub verbs parsed"""
        root = ET.Element("Gather")
        ET.SubElement(root, "Play")
        gather = Gather.from_xml(root, 'test_url')
        self.assertEqual(gather.nouns[0].name, 'Play')

    def test_gather_from_xml_invalid_sub_verbs(self):
        """Shoudl raise an exception for invalid sub verbs"""
        root = ET.Element("Gather")
        ET.SubElement(root, "Hangup")
        e = self.assertRaises(
            TwiMLParseError, Gather.from_xml, root, 'test_url')
        self.assertEqual(
            str(e), "Invalid sub verb 'Hangup' for Gather verb. "
            "Must be one of ['Say', 'Play']")
