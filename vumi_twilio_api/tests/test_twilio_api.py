import json
from klein import Klein
import treq
from twilio import twiml
from twilio.rest import TwilioRestClient
from twisted.internet.defer import inlineCallbacks
from twisted.internet.threads import deferToThread
from twisted.trial.unittest import TestCase
from vumi.application.tests.helpers import ApplicationHelper
from vumi.tests.helpers import VumiTestCase
import xml.etree.ElementTree as ET

from vumi_twilio_api.twilio_api import TwilioAPIServer, TwilioAPIWorker

class TwiMLServer(object):
    app = Klein()

    def __init__(self, responses={}):
        self._responses = responses.copy()

    def add_response(self, filename, response):
        self._responses[filename] = response

    @app.route('/<string:filename>')
    def get_twiml(self, request, filename):
        return self._responses[filename].toxml()


class TestTwilioAPIServer(VumiTestCase):

    @inlineCallbacks
    def setUp(self):
        self.app_helper = self.add_helper(ApplicationHelper(
            TwilioAPIWorker, transport_type='voice'))
        self.worker = yield self.app_helper.get_application({
            'web_path': '/api',
            'web_port': 8080,
            'api_version': 'v1',
        })
        addr = self.worker.webserver.getHost()
        self.url = 'http://%s:%s%s' % (addr.host, addr.port, '/api')
        self.client = TwilioRestClient('test_account', 'test_token', base=self.url, version='v1')
        self.twiml_server = TwiMLServer()
        self.twiml_connection = self.worker.start_web_resources([
            (self.twiml_server.app.resource(), '/twiml')], 8081)
        self.add_cleanup(self.twiml_connection.loseConnection)

    def _server_request(self, path=''):
        url = '%s/v1/%s' % (self.url, path)
        return treq.get(url, persistent=False)

    def _twilio_client_create_call(self, filename, *args, **kwargs):
        addr = self.twiml_connection.getHost()
        url = 'http://%s:%s%s%s' % (addr.host, addr.port, '/twiml/', filename)
        return deferToThread(self.client.calls.create, *args, url=url, **kwargs)

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
            'Foo': {
                'Bar': {
                    'Baz': 'Qux',
                },
                'FooBar': 'BazQux',
            },
            'BarFoo': 'QuxBaz',
        }
        res = format_json(d)
        root = json.loads(res)
        expected = {
            'foo': {
                'bar': {
                    'baz': 'Qux',
                },
                'foo_bar': 'BazQux',
            },
            'bar_foo': 'QuxBaz',
        }
        self.assertEqual(root, expected)
