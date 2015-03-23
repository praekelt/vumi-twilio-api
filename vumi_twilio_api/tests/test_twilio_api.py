import json
import treq
from twilio.rest import TwilioRestClient
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
        account = "TestAccount"
        token = "test_account_token"
        self.client = TwilioRestClient(account, token, base=self.url, version='v1') 

    @inlineCallbacks
    def test_create_call(self):
        response = yield treq.get(self.url + '/v1')
        print response

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

