from datetime import datetime
import json
from klein import Klein
from mock import Mock
import re
import treq
from twilio.rest import TwilioRestClient
from twilio.rest.exceptions import TwilioRestException
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
        request.setHeader('Content-Type', 'application/xml')
        return ET.tostring(self._responses[filename])


class TestTwiMLServer(VumiTestCase):

    @inlineCallbacks
    def setUp(self):
        self.app_helper = self.add_helper(ApplicationHelper(
            TwilioAPIWorker, transport_type='voice'))
        self.worker = yield self.app_helper.get_application({
            'web_path': '/api',
            'web_port': 8080,
            'api_version': 'v1',
        })

        self.twiml_server = TwiMLServer()
        self.twiml_connection = self.worker.start_web_resources([
            (self.twiml_server.app.resource(), '/twiml')], 8081)
        self.add_cleanup(self.twiml_connection.loseConnection)
        addr = self.twiml_connection.getHost()
        self.url = 'http://%s:%s' % (addr.host, addr.port)

    def _server_request(self, path='', method='GET', data={}):
        url = '%s/twiml/%s' % (self.url, path)
        return treq.request(method, url, persistent=False, data=data)

    @inlineCallbacks
    def test_getting_response(self):
        response = ET.Element('Foo')
        bar = ET.SubElement(response, 'Bar')
        self.twiml_server.add_response('example.xml', response)

        request = yield self._server_request('example.xml')
        request = yield request.content()
        root = ET.fromstring(request)
        self.assertEqual(root.tag, response.tag)
        [child] = list(root)
        self.assertEqual(child.tag, bar.tag)


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
        self.client = TwilioRestClient(
            'test_account', 'test_token', base=self.url, version='v1')
        self.twiml_server = TwiMLServer()
        self.twiml_connection = self.worker.start_web_resources([
            (self.twiml_server.app.resource(), '/twiml')], 8081)
        self.add_cleanup(self.twiml_connection.loseConnection)

    def _server_request(self, path='', method='GET', data={}):
        url = '%s/v1/%s' % (self.url, path)
        return treq.request(method, url, persistent=False, data=data)

    def _twilio_client_create_call(self, filename, *args, **kwargs):
        addr = self.twiml_connection.getHost()
        url = 'http://%s:%s%s%s' % (addr.host, addr.port, '/twiml/', filename)
        return deferToThread(
            self.client.calls.create, *args, url=url, **kwargs)

    def assertRegexpMatches(self, text, regexp, msg=None):
        self.assertTrue(re.search(regexp, text), msg=msg)

    @inlineCallbacks
    def assert_parameter_missing(self, url, method='GET', error={}, data={}):
        response = yield self._server_request(
            url, method=method, data=data)
        self.assertEqual(response.code, 400)
        response = yield response.json()
        self.assertEqual(response, error)

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
        [version] = list(root)
        self.assertEqual(version.tag, 'Version')
        [name, subresourceuris, uri] = sorted(
            list(version), key=lambda i: i.tag)
        self.assertEqual(name.tag, 'Name')
        self.assertEqual(name.text, 'v1')
        self.assertEqual(uri.tag, 'Uri')
        self.assertEqual(uri.text, '/v1')
        self.assertEqual(subresourceuris.tag, 'SubresourceUris')
        [accounts] = sorted(list(subresourceuris), key=lambda i: i.tag)
        self.assertEqual(accounts.tag, 'Accounts')
        self.assertEqual(accounts.text, '/v1/Accounts')

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
        [version] = list(root)
        self.assertEqual(version.tag, 'Version')
        [name, subresourceuris, uri] = sorted(
            list(version), key=lambda i: i.tag)
        self.assertEqual(name.tag, 'Name')
        self.assertEqual(name.text, 'v1')
        self.assertEqual(uri.tag, 'Uri')
        self.assertEqual(uri.text, '/v1.xml')
        self.assertEqual(subresourceuris.tag, 'SubresourceUris')
        [accounts] = sorted(list(subresourceuris), key=lambda i: i.tag)
        self.assertEqual(accounts.tag, 'Accounts')
        self.assertEqual(accounts.text, '/v1/Accounts.xml')

    @inlineCallbacks
    def test_root_json(self):
        response = yield self._server_request('.json')
        self.assertEqual(
            response.headers.getRawHeaders('content-type'),
            ['application/json'])
        self.assertEqual(response.code, 200)
        content = yield response.json()
        self.assertEqual(content, {
            'name': 'v1',
            'uri': '/v1.json',
            'subresource_uris': {
                'accounts': '/v1/Accounts.json'
            }
        })

    @inlineCallbacks
    def test_root_invalid_format(self):
        response = yield self._server_request('.foo')
        self.assertEqual(
            response.headers.getRawHeaders('content-type'),
            ['application/xml'])
        self.assertEqual(response.code, 400)
        content = yield response.content()
        root = ET.fromstring(content)
        [error] = list(root)
        [error_message, error_type] = sorted(error, key=lambda c: c.tag)
        self.assertEqual(error_message.tag, 'error_message')
        self.assertEqual(
            error_message.text, "'foo' is not a valid request format")
        self.assertEqual(error_type.tag, 'error_type')
        self.assertEqual(error_type.text, 'UsageError')

    @inlineCallbacks
    def test_make_call_sid(self):
        res = self.worker.server._get_sid()
        self.assertTrue(isinstance(res, basestring))
        self.assertTrue('-' not in res)

        self.worker.server._get_sid = Mock(return_value='ab12cd34')
        call = yield self._twilio_client_create_call(
            'default.xml', from_='+12345', to='+54321')
        self.assertEqual(call.sid, 'ab12cd34')
        self.assertEqual(
            call.subresource_uris['notifications'],
            '/v1/Accounts/test_account/Calls/ab12cd34/Notifications.json')
        self.assertEqual(
            call.subresource_uris['recordings'],
            '/v1/Accounts/test_account/Calls/ab12cd34/Recordings.json')
        self.assertEqual(call.name, 'ab12cd34')

    @inlineCallbacks
    def test_make_call_timestamp(self):
        res = self.worker.server._get_timestamp()
        self.assertTrue(isinstance(res, basestring))
        self.assertRegexpMatches(
            res, '\w+, \d{2} \w+ \d{4} \d{2}:\d{2}:\d{2} (\+|-)\d{4}')

        self.worker.server._get_timestamp = Mock(
            return_value='Thu, 01 January 1970 00:00:00 +0000')
        call = yield self._twilio_client_create_call(
            'default.xml', from_='+12345', to='+54321')
        self.assertEqual(call.date_created, datetime.utcfromtimestamp(0))
        self.assertEqual(call.date_updated, datetime.utcfromtimestamp(0))

    @inlineCallbacks
    def test_make_call_response_defaults(self):
        call = yield self._twilio_client_create_call(
            'default.xml', from_='+12345', to='+54321')

        self.assertEqual(call.to, '+54321')
        self.assertEqual(call.formatted_to, '+54321')
        self.assertEqual(call.from_, '+12345')
        self.assertEqual(call.formatted_from, '+12345')
        self.assertEqual(call.parent_call_sid, None)
        self.assertEqual(call.phone_number_sid, None)
        self.assertEqual(call.status, 'queued')
        self.assertEqual(call.start_time, None)
        self.assertEqual(call.end_time, None)
        self.assertEqual(call.duration, None)
        self.assertEqual(call.price, None)
        self.assertEqual(call.direction, 'outbound-api')
        self.assertEqual(call.answered_by, None)
        self.assertEqual(call.api_version, 'v1')
        self.assertEqual(call.forwarded_from, None)
        self.assertEqual(call.caller_name, None)
        self.assertEqual(call.account_sid, 'test_account')

    @inlineCallbacks
    def test_make_call_required_parameters_to(self):
        addr = self.twiml_connection.getHost()
        url = 'http://%s:%s%s%s' % (
            addr.host, addr.port, '/twiml/', 'example.xml')

        # Can't use the client here because it requires the required parameters
        yield self.assert_parameter_missing(
            '/Accounts/test-account/Calls.json', 'POST', data={
                'From': '+12345', 'Url': url},
            error={
                'error_type': 'UsageError',
                'error_message': 
                    "Required field 'To' not supplied",
            })

    @inlineCallbacks
    def test_make_call_required_parameters_from(self):
        addr = self.twiml_connection.getHost()
        url = 'http://%s:%s%s%s' % (
            addr.host, addr.port, '/twiml/', 'example.xml')

        # Can't use the client here because it requires the required parameters
        yield self.assert_parameter_missing(
            '/Accounts/test-account/Calls.json', 'POST', data={
                'To': '+12345', 'Url': url},
            error={
                'error_type': 'UsageError',
                'error_message': 
                    "Required field 'From' not supplied",
            })

    @inlineCallbacks
    def test_make_call_required_parameters_url(self):
        addr = self.twiml_connection.getHost()
        url = 'http://%s:%s%s%s' % (
            addr.host, addr.port, '/twiml/', 'example.xml')

        # Can't use the client here because it requires the required parameters
        yield self.assert_parameter_missing(
            '/Accounts/test-account/Calls.json', 'POST', data={
                'To': '+12345', 'From': '+54321'},
            error={
                'error_type': 'UsageError',
                'error_message': 
                    "Request must have an 'Url' or an 'ApplicationSid' field",
            })

        response = yield self._server_request(
            '/Accounts/test-account/Calls.json', method='POST',
            data={'To': '+12345', 'From': '+54321', 'Url': url})
        self.assertEqual(response.code, 200)
        response = yield response.json()
        self.assertEqual(response['to'], '+12345')

        response = yield self._server_request(
            '/Accounts/test-account/Calls.json', method='POST',
            data={
                'To': '+12345',
                'From': '+54321',
                'ApplicationSid': 'foobar'})
        self.assertEqual(response.code, 200)
        response = yield response.json()
        self.assertEqual(response['to'], '+12345')

    @inlineCallbacks
    def test_make_call_optional_parameters_senddigits(self):
        call = yield self._twilio_client_create_call(
            'default.xml', from_='+12345', to='+54321',
            send_digits='0123456789#*w')
        self.assertEqual(call.to, '+54321')

        e = yield self.assertFailure(
            self._twilio_client_create_call(
                'default.xml', from_='+12345', to='+54321',
                send_digits='0a*'),
            TwilioRestException)
        self.assertEqual(e.status, 400)
        message = json.loads(e.msg)
        self.assertEqual(message['error_type'], 'UsageError')
        self.assertEqual(
            message['error_message'],
            "SendDigits value '0a*' is not valid. May only contain the "
            "characters (0-9), '#', '*' and 'w'")

    @inlineCallbacks
    def test_make_call_optional_parameters_ifmachine(self):
        call = yield self._twilio_client_create_call(
            'default.xml', from_='+12345', to='+54321',
            if_machine='Continue')
        self.assertEqual(call.to, '+54321')

        call = yield self._twilio_client_create_call(
            'default.xml', from_='+12345', to='+54321',
            if_machine='Hangup')
        self.assertEqual(call.to, '+54321')

        e = yield self.assertFailure(
            self._twilio_client_create_call(
                'default.xml', from_='+12345', to='+54321',
                if_machine='foobar'),
            TwilioRestException)
        self.assertEqual(e.status, 400)
        message = json.loads(e.msg)
        self.assertEqual(message['error_type'], 'UsageError')
        self.assertEqual(
            message['error_message'],
            "IfMachine value must be one of [None, 'Continue', 'Hangup']")


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
            'Root': {
                'Foo': {
                    'Bar': {
                        'Baz': 'Qux',
                    },
                    'FooBar': 'BazQux',
                },
                'BarFoo': 'QuxBaz',
            }
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
