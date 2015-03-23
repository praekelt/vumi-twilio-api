import json
import treq
from twisted.internet.defer import inlineCallbacks
from twisted.trial.unittest import TestCase
from vumi.application.tests.helpers import ApplicationHelper
from vumi.tests.helpers import VumiTestCase
import xml.etree.ElementTree as ET

from vumi_twilio_api.twilio_api import TwilioAPIServer, TwilioAPIWorker


class TestTwilioAPIServer(VumiTestCase):

    @inlineCallbacks
    def setUp(self):
        self.app_helper = self.add_helper(ApplicationHelper(
            TwilioAPIWorker, transport_type='voice'))
        self.worker = yield self.app_helper.get_application({
            'web_path': '/api/v1',
            'web_port': 8080
        })
        addr = self.worker.webserver.getHost()
        self.url = 'http://%s:%s%s' % (addr.host, addr.port, '/api')

    def _server_request(self, path=''):
        url = '%s/v1/%s' % (self.url, path)
        return treq.get(url, persistent=False)

    @inlineCallbacks
    def test_root_default(self):
        response = yield self._server_request()
        self.assertEqual(
            response.headers.getRawHeaders('content-type'),
            ['application/xml'])
        self.assertEqual(response.code, 200)
        content = yield response.content()
        root = ET.fromstring(content)
        self.assertEqual(root.tag, "TwilioResponse")
        self.assertEqual(list(root), [])

    @inlineCallbacks
    def test_root_xml(self):
        response = yield self._server_request('.xml')
        self.assertEqual(
            response.headers.getRawHeaders('content-type'),
            ['application/xml'])
        self.assertEqual(response.code, 200)
        content = yield response.content()
        root = ET.fromstring(content)
        self.assertEqual(root.tag, "TwilioResponse")
        self.assertEqual(list(root), [])

    @inlineCallbacks
    def test_root_json(self):
        response = yield self._server_request('.json')
        self.assertEqual(
            response.headers.getRawHeaders('content-type'),
            ['application/json'])
        self.assertEqual(response.code, 200)
        content = yield response.json()
        self.assertEqual(content, {})

    @inlineCallbacks
    def test_root_invalid_format(self):
        response = yield self._server_request('.foo')
        self.assertEqual(
            response.headers.getRawHeaders('content-type'),
            ['application/xml'])
        self.assertEqual(response.code, 400)
        content = yield response.content()
        root = ET.fromstring(content)
        [error_message, error_type] = sorted(root, key=lambda c: c.tag)
        self.assertEqual(error_message.tag, 'error_message')
        self.assertEqual(
            error_message.text, "'foo' is not a valid request format")
        self.assertEqual(error_type.tag, 'error_type')
        self.assertEqual(error_type.text, 'UsageError')


class TestServerFormatting(TestCase):

    def test_format_xml(self):
        format_xml = TwilioAPIServer.format_xml
        res = format_xml({
            'foo': {
                'bar': {
                    'baz': 'qux',
                },
                'foobar': 'bazqux',
            },
            'barfoo': 'quxbaz',
        })
        root = ET.fromstring(res)
        self.assertEqual(root.tag, 'TwilioResponse')
        [barfoo, foo] = sorted(root, key=lambda c: c.tag)
        self.assertEqual(foo.tag, 'foo')
        self.assertEqual(barfoo.tag, 'barfoo')
        self.assertEqual(barfoo.text, 'quxbaz')
        [bar, foobar] = sorted(foo, key=lambda c: c.tag)
        self.assertEqual(bar.tag, 'bar')
        self.assertEqual(foobar.tag, 'foobar')
        self.assertEqual(foobar.text, 'bazqux')
        [baz] = list(bar)
        self.assertEqual(baz.tag, 'baz')
        self.assertEqual(baz.text, 'qux')

    def test_format_json(self):
        format_json = TwilioAPIServer.format_json
        d = {
            'foo': {
                'bar': {
                    'baz': 'qux',
                },
                'foobar': 'bazqux',
            },
            'barfoo': 'quxbaz',
        }
        res = format_json(d)
        root = json.loads(res)
        self.assertEqual(root, d)
