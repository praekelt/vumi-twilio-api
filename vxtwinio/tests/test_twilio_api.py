from datetime import datetime
import json
from mock import Mock
import re
import treq
from twilio import twiml
from twilio.rest import TwilioRestClient
from twilio.rest.exceptions import TwilioRestException
from twisted.internet.defer import inlineCallbacks
from twisted.internet.threads import deferToThread
from twisted.trial.unittest import TestCase
from vumi.application.tests.helpers import ApplicationHelper
from vumi.message import TransportUserMessage
from vumi.tests.helpers import VumiTestCase
import xml.etree.ElementTree as ET

from .helpers import TwiMLServer
from vumi_twilio_api.twilio_api import TwilioAPIWorker, Response


class TestTwiMLServer(VumiTestCase):

    @inlineCallbacks
    def setUp(self):
        self.twiml_server = yield self.add_helper(TwiMLServer())
        self.url = self.twiml_server.url

    def _server_request(self, path='', method='GET', data={}):
        url = '%s/%s' % (self.url, path)
        return treq.request(method, url, persistent=False, data=data)

    @inlineCallbacks
    def test_getting_response(self):
        response = twiml.Response()
        response.say("Hello")
        self.twiml_server.add_response('example.xml', response)

        request = yield self._server_request('example.xml')
        request = yield request.content()
        root = ET.fromstring(request)
        self.assertEqual(root.tag, 'Response')
        [child] = list(root)
        self.assertEqual(child.tag, 'Say')
        self.assertEqual(child.text, 'Hello')


class TestTwilioAPIServer(VumiTestCase):

    @inlineCallbacks
    def setUp(self):
        self.twiml_server = yield self.add_helper(TwiMLServer())

        self.app_helper = self.add_helper(ApplicationHelper(
            TwilioAPIWorker, use_riak=True, transport_type='voice'))
        self.worker = yield self.app_helper.get_application({
            'web_path': '/api',
            'web_port': 0,
            'api_version': 'v1',
            'client_path': '%s' % self.twiml_server.url,
            'status_callback_path': '%s/callback.xml' % self.twiml_server.url,
        })
        addr = self.worker.webserver.getHost()
        self.url = 'http://%s:%s%s' % (addr.host, addr.port, '/api')
        self.client = TwilioRestClient(
            'test_account', 'test_token', base=self.url, version='v1')
        self.patch_resource_request(self.client.calls)

    def patch_resource_request(self, resource):
        """
        Patch a TwilioRestClient resource object's request method to force the
        connection to be closed at the end of the request.
        """
        old_request = resource.request

        def request(method, uri, **kwargs):
            kwargs["headers"] = kwargs.get("headers", {}).copy()
            kwargs["headers"].setdefault("Connection", "close")
            return old_request(method, uri, **kwargs)

        self.patch(resource, "request", request)

    def _server_request(self, path='', method='GET', data={}):
        url = '%s/v1/%s' % (self.url, path)
        return treq.request(method, url, persistent=False, data=data)

    def _twilio_client_create_call(self, filename, *args, **kwargs):
        url = '%s/%s' % (self.twiml_server.url, filename)
        if kwargs.get('fallback_url'):
            kwargs['fallback_url'] = '%s/%s' % (
                self.twiml_server.url, kwargs['fallback_url'])
        if kwargs.get('status_callback'):
            kwargs['status_callback'] = '%s/%s' % (
                self.twiml_server.url, kwargs['status_callback'])
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
        self.assertEqual(error_type.text, 'TwilioAPIUsageException')

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
        # Can't use the client here because it requires the required parameters
        yield self.assert_parameter_missing(
            '/Accounts/test-account/Calls.json', 'POST', data={
                'From': '+12345', 'Url': self.twiml_server.url},
            error={
                'error_type': 'TwilioAPIUsageException',
                'error_message':
                    "Required field 'To' not supplied",
            })

    @inlineCallbacks
    def test_make_call_required_parameters_from(self):
        # Can't use the client here because it requires the required parameters
        yield self.assert_parameter_missing(
            '/Accounts/test-account/Calls.json', 'POST', data={
                'To': '+12345', 'Url': self.twiml_server.url},
            error={
                'error_type': 'TwilioAPIUsageException',
                'error_message':
                    "Required field 'From' not supplied",
            })

    @inlineCallbacks
    def test_make_call_required_parameters_url(self):
        # Can't use the client here because it requires the required parameters
        yield self.assert_parameter_missing(
            '/Accounts/test-account/Calls.json', 'POST', data={
                'To': '+12345', 'From': '+54321'},
            error={
                'error_type': 'TwilioAPIUsageException',
                'error_message':
                    "Request must have an 'Url' or an 'ApplicationSid' field",
            })

        response = yield self._server_request(
            '/Accounts/test-account/Calls.json', method='POST',
            data={
                'To': '+12345',
                'From': '+54321',
                'Url': self.twiml_server.url})
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
        self.assertEqual(message['error_type'], 'TwilioAPIUsageException')
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
        self.assertEqual(message['error_type'], 'TwilioAPIUsageException')
        self.assertEqual(
            message['error_message'],
            "IfMachine value must be one of [None, 'Continue', 'Hangup']")

    @inlineCallbacks
    def test_make_call_ack_fallback_url(self):
        self.twiml_server.add_err('err.xml', 'Error response')
        response = twiml.Response()
        self.twiml_server.add_response('default.xml', response)
        yield self._twilio_client_create_call(
            'err.xml', from_='+12345', to='+54321',
            fallback_url='default.xml')
        [msg] = yield self.app_helper.wait_for_dispatched_outbound(1)
        yield self.app_helper.dispatch_event(self.app_helper.make_ack(msg))
        [bad, req] = self.twiml_server.requests
        self.assertEqual(req['filename'], 'default.xml')
        self.assertEqual(bad['filename'], 'err.xml')

    @inlineCallbacks
    def test_make_call_ack_response(self):
        response = twiml.Response()
        self.twiml_server.add_response('default.xml', response)
        yield self._twilio_client_create_call(
            'default.xml', from_='+12345', to='+54321')
        [msg] = yield self.app_helper.wait_for_dispatched_outbound(1)
        yield self.app_helper.dispatch_event(self.app_helper.make_ack(msg))
        [req] = self.twiml_server.requests
        self.assertEqual(req['filename'], 'default.xml')
        self.assertEqual(req['request'].args['CallStatus'], ['in-progress'])

    @inlineCallbacks
    def test_make_call_nack_response(self):
        response = twiml.Response()
        self.twiml_server.add_response('default.xml', response)
        yield self._twilio_client_create_call(
            'default.xml', from_='+12345', to='+54321')
        [msg] = yield self.app_helper.wait_for_dispatched_outbound(1)
        yield self.app_helper.dispatch_event(self.app_helper.make_nack(msg))
        [req] = self.twiml_server.requests
        self.assertEqual(req['filename'], 'default.xml')
        self.assertEqual(req['request'].args['CallStatus'], ['failed'])

    @inlineCallbacks
    def test_make_call_parsing_play_verb(self):
        response = twiml.Response()
        response.play('test_url')
        self.twiml_server.add_response('default.xml', response)

        yield self._twilio_client_create_call(
            'default.xml', from_='+12345', to='+54321')
        [msg] = yield self.app_helper.wait_for_dispatched_outbound(1)
        yield self.app_helper.dispatch_event(self.app_helper.make_ack(msg))
        [_, reply] = yield self.app_helper.wait_for_dispatched_outbound(1)
        self.assertEqual(
            reply['helper_metadata']['voice']['speech_url'], 'test_url')
        self.assertEqual(reply['from_addr'], '+12345')
        self.assertEqual(reply['to_addr'], '+54321')

    @inlineCallbacks
    def test_make_call_parsing_hangup_verb(self):
        response = twiml.Response()
        response.hangup()
        self.twiml_server.add_response('default.xml', response)

        yield self._twilio_client_create_call(
            'default.xml', from_='+12345', to='+54321')
        [msg] = yield self.app_helper.wait_for_dispatched_outbound(1)
        yield self.app_helper.dispatch_event(self.app_helper.make_ack(msg))
        [_, reply] = yield self.app_helper.wait_for_dispatched_outbound(1)
        self.assertEqual(
            reply['session_event'], TransportUserMessage.SESSION_CLOSE)
        self.assertEqual(reply['from_addr'], '+12345')
        self.assertEqual(reply['to_addr'], '+54321')

    @inlineCallbacks
    def test_make_call_parsing_gather_verb_defaults(self):
        response = twiml.Response()
        response.gather()
        self.twiml_server.add_response('default.xml', response)

        yield self._twilio_client_create_call(
            'default.xml', from_='+12345', to='+54321')
        [msg] = yield self.app_helper.wait_for_dispatched_outbound(1)
        yield self.app_helper.dispatch_event(self.app_helper.make_ack(msg))
        [_, reply] = yield self.app_helper.wait_for_dispatched_outbound(1)
        self.assertEqual(reply['helper_metadata']['voice']['wait_for'], '#')
        self.assertEqual(reply['from_addr'], '+12345')
        self.assertEqual(reply['to_addr'], '+54321')

    @inlineCallbacks
    def test_make_call_parsing_gather_verb_non_defaults(self):
        response = twiml.Response()
        response.gather(action='/test_url', method='GET', finishOnKey='*')
        self.twiml_server.add_response('default.xml', response)

        yield self._twilio_client_create_call(
            'default.xml', from_='+12345', to='+54321')
        [msg] = yield self.app_helper.wait_for_dispatched_outbound(1)
        yield self.app_helper.dispatch_event(self.app_helper.make_ack(msg))
        [_, reply] = yield self.app_helper.wait_for_dispatched_outbound(1)
        self.assertEqual(reply['helper_metadata']['voice']['wait_for'], '*')
        session = yield self.worker.session_manager.load_session('+54321')
        self.assertEqual(session['Gather_Method'], 'GET')
        self.assertEqual(
            session['Gather_Action'], self.twiml_server.url + 'test_url')
        self.assertEqual(reply['from_addr'], '+12345')
        self.assertEqual(reply['to_addr'], '+54321')

    @inlineCallbacks
    def test_make_call_parsing_gather_verb_subverbs(self):
        response = twiml.Response()
        with response.gather() as g:
            g.play('test_url')
            g.play('test_url2')
        self.twiml_server.add_response('default.xml', response)

        yield self._twilio_client_create_call(
            'default.xml', from_='+12345', to='+54321')
        [msg] = yield self.app_helper.wait_for_dispatched_outbound(1)
        yield self.app_helper.dispatch_event(self.app_helper.make_ack(msg))
        [_, reply1, reply2] = (
            yield self.app_helper.wait_for_dispatched_outbound(1))
        self.assertEqual(
            reply1['helper_metadata']['voice']['speech_url'], 'test_url')
        self.assertEqual(
            reply2['helper_metadata']['voice']['speech_url'], 'test_url2')

    @inlineCallbacks
    def test_make_call_parsing_gather_verb_with_reply(self):
        response = twiml.Response()
        response.gather(action='reply.xml')
        self.twiml_server.add_response('default.xml', response)
        response = twiml.Response()
        response.play('test_url')
        self.twiml_server.add_response('reply.xml', response)

        yield self._twilio_client_create_call(
            'default.xml', from_='+12345', to='+54321')
        [msg] = yield self.app_helper.wait_for_dispatched_outbound(1)
        yield self.app_helper.dispatch_event(self.app_helper.make_ack(msg))
        [_, rep] = yield self.app_helper.wait_for_dispatched_outbound(1)
        reply = rep.reply('123')
        yield self.app_helper.dispatch_inbound(reply)
        [_, _, play] = yield self.app_helper.wait_for_dispatched_outbound(1)
        self.assertEqual(
            play['helper_metadata']['voice']['speech_url'], 'test_url')
        request = self.twiml_server.requests[-1]
        self.assertEqual(request['filename'], 'reply.xml')
        self.assertEqual(request['request'].method, 'POST')
        self.assertEqual(request['request'].args['Digits'], ['123'])

    @inlineCallbacks
    def test_make_call_parsing_gather_verb_with_reply_get_request(self):
        response = twiml.Response()
        response.gather(action='reply.xml', method='GET')
        self.twiml_server.add_response('default.xml', response)
        response = twiml.Response()
        response.play('test_url')
        self.twiml_server.add_response('reply.xml', response)

        yield self._twilio_client_create_call(
            'default.xml', from_='+12345', to='+54321')
        [msg] = yield self.app_helper.wait_for_dispatched_outbound(1)
        yield self.app_helper.dispatch_event(self.app_helper.make_ack(msg))
        [_, rep] = yield self.app_helper.wait_for_dispatched_outbound(1)
        reply = rep.reply('123')
        yield self.app_helper.dispatch_inbound(reply)
        [_, _, play] = yield self.app_helper.wait_for_dispatched_outbound(1)
        self.assertEqual(
            play['helper_metadata']['voice']['speech_url'], 'test_url')
        request = self.twiml_server.requests[-1]
        self.assertEqual(request['filename'], 'reply.xml')
        self.assertEqual(request['request'].method, 'GET')

    @inlineCallbacks
    def test_receive_call(self):
        response = twiml.Response()
        self.twiml_server.add_response('', response)
        msg = self.app_helper.make_inbound(
            None, from_addr='+54321', to_addr='+12345',
            session_event=TransportUserMessage.SESSION_NEW)
        yield self.app_helper.dispatch_inbound(msg)
        [req] = self.twiml_server.requests
        self.assertEqual(req['filename'], '')
        self.assertEqual(req['request'].args['Direction'], ['inbound'])

    @inlineCallbacks
    def test_receive_call_parsing_play_verb(self):
        response = twiml.Response()
        response.play('test_url')
        self.twiml_server.add_response('', response)

        msg = self.app_helper.make_inbound(
            None, from_addr='+54321', to_addr='+12345',
            session_event=TransportUserMessage.SESSION_NEW)
        yield self.app_helper.dispatch_inbound(msg)
        [reply] = yield self.app_helper.wait_for_dispatched_outbound(1)

        self.assertEqual(
            reply['helper_metadata']['voice']['speech_url'], 'test_url')
        self.assertEqual(reply['in_reply_to'], msg['message_id'])

    @inlineCallbacks
    def test_receive_call_parsing_hangup_verb(self):
        response = twiml.Response()
        response.hangup()
        self.twiml_server.add_response('', response)

        msg = self.app_helper.make_inbound(
            '', from_addr='+54321', to_addr='+12345',
            session_event=TransportUserMessage.SESSION_NEW)
        yield self.app_helper.dispatch_inbound(msg)
        [reply] = yield self.app_helper.wait_for_dispatched_outbound(1)

        self.assertEqual(
            reply['session_event'], TransportUserMessage.SESSION_CLOSE)
        self.assertEqual(reply['in_reply_to'], msg['message_id'])

    @inlineCallbacks
    def test_receive_call_parsing_gather_verb_defaults(self):
        response = twiml.Response()
        response.gather()
        self.twiml_server.add_response('', response)

        msg = self.app_helper.make_inbound(
            '', from_addr='+54321', to_addr='+12345',
            session_event=TransportUserMessage.SESSION_NEW)
        yield self.app_helper.dispatch_inbound(msg)
        [gather] = yield self.app_helper.wait_for_dispatched_outbound(1)
        self.assertEqual(gather['helper_metadata']['voice']['wait_for'], '#')
        self.assertEqual(gather['in_reply_to'], msg['message_id'])

    @inlineCallbacks
    def test_receive_call_parsing_gather_verb_nondefaults(self):
        response = twiml.Response()
        response.gather(action='/test_url', method='GET', finishOnKey='*')
        self.twiml_server.add_response('', response)

        msg = self.app_helper.make_inbound(
            '', from_addr='+54321', to_addr='+12345',
            session_event=TransportUserMessage.SESSION_NEW)
        yield self.app_helper.dispatch_inbound(msg)
        [gather] = yield self.app_helper.wait_for_dispatched_outbound(1)
        self.assertEqual(gather['helper_metadata']['voice']['wait_for'], '*')
        session = yield self.worker.session_manager.load_session('+54321')
        self.assertEqual(session['Gather_Method'], 'GET')
        self.assertEqual(
            session['Gather_Action'], self.twiml_server.url + 'test_url')
        self.assertEqual(gather['in_reply_to'], msg['message_id'])

    @inlineCallbacks
    def test_receive_call_parsing_gather_verb_with_subverbs(self):
        response = twiml.Response()
        with response.gather() as g:
            g.play('test_url')
            g.play('test_url2')
        self.twiml_server.add_response('', response)

        msg = self.app_helper.make_inbound(
            '', from_addr='+54231', to_addr='+12345',
            session_event=TransportUserMessage.SESSION_NEW)
        yield self.app_helper.dispatch_inbound(msg)
        [gather1, gather2] = (
            yield self.app_helper.wait_for_dispatched_outbound(1))
        self.assertEqual(
            gather1['helper_metadata']['voice']['speech_url'], 'test_url')
        self.assertEqual(
            gather2['helper_metadata']['voice']['speech_url'], 'test_url2')
        self.assertEqual(
            gather2['helper_metadata']['voice']['wait_for'], '#')

    @inlineCallbacks
    def test_receive_call_parsing_gather_verb_with_reply(self):
        response = twiml.Response()
        response.gather(action='reply.xml')
        self.twiml_server.add_response('', response)
        response = twiml.Response()
        response.play('test_url')
        self.twiml_server.add_response('reply.xml', response)

        msg = self.app_helper.make_inbound(
            '', from_addr='+54231', to_addr='+12345',
            session_event=TransportUserMessage.SESSION_NEW)
        yield self.app_helper.dispatch_inbound(msg)
        [rep] = yield self.app_helper.wait_for_dispatched_outbound(1)
        reply = rep.reply('123')
        yield self.app_helper.dispatch_inbound(reply)
        [_, play] = yield self.app_helper.wait_for_dispatched_outbound(1)
        self.assertEqual(
            play['helper_metadata']['voice']['speech_url'], 'test_url')
        request = self.twiml_server.requests[-1]
        self.assertEqual(request['filename'], 'reply.xml')
        self.assertEqual(request['request'].method, 'POST')
        self.assertEqual(request['request'].args['Digits'], ['123'])

    @inlineCallbacks
    def test_receive_call_parsing_gather_verb_with_reply_get_request(self):
        response = twiml.Response()
        response.gather(action='reply.xml', method='GET')
        self.twiml_server.add_response('', response)
        response = twiml.Response()
        response.play('test_url')
        self.twiml_server.add_response('reply.xml', response)

        msg = self.app_helper.make_inbound(
            '', from_addr='+54231', to_addr='+12345',
            session_event=TransportUserMessage.SESSION_NEW)
        yield self.app_helper.dispatch_inbound(msg)
        [rep] = yield self.app_helper.wait_for_dispatched_outbound(1)
        reply = rep.reply('123')
        yield self.app_helper.dispatch_inbound(reply)
        [_, play] = yield self.app_helper.wait_for_dispatched_outbound(1)
        self.assertEqual(
            play['helper_metadata']['voice']['speech_url'], 'test_url')
        request = self.twiml_server.requests[-1]
        self.assertEqual(request['filename'], 'reply.xml')
        self.assertEqual(request['request'].method, 'GET')

    @inlineCallbacks
    def test_outgoing_call_ended_status_callback(self):
        self.twiml_server.add_response('callback.xml', twiml.Response())
        yield self._twilio_client_create_call(
            'default.xml', from_='+12345', to='+54321',
            status_callback='callback.xml')

        msg = self.app_helper.make_inbound(
            None, from_addr='+54321', to_addr='+12345',
            session_event=TransportUserMessage.SESSION_CLOSE)
        yield self.app_helper.dispatch_inbound(msg)
        [callback] = self.twiml_server.requests
        self.assertEqual(callback['filename'], 'callback.xml')
        self.assertEqual(callback['request'].args['CallStatus'], ['completed'])
        sessions = yield self.worker.session_manager.active_sessions()
        self.assertEqual(len(sessions), 0)

    @inlineCallbacks
    def test_incoming_call_ended_status_callback(self):
        self.twiml_server.add_response('', twiml.Response())
        self.twiml_server.add_response('callback.xml', twiml.Response())

        msg_start = self.app_helper.make_inbound(
            None, from_addr='+54321', to_addr='+12345',
            session_event=TransportUserMessage.SESSION_NEW)
        msg_end = self.app_helper.make_inbound(
            None, from_addr='+54321', to_addr='+12345',
            session_event=TransportUserMessage.SESSION_CLOSE)

        yield self.app_helper.dispatch_inbound(msg_start)
        yield self.app_helper.dispatch_inbound(msg_end)

        [_, callback] = self.twiml_server.requests
        self.assertEqual(callback['filename'], 'callback.xml')
        self.assertEqual(callback['request'].args['CallStatus'], ['completed'])
        sessions = yield self.worker.session_manager.active_sessions()
        self.assertEqual(len(sessions), 0)


class TestServerFormatting(TestCase):

    def test_format_xml(self):
        o = Response(
            foo={
                'bar': {
                    'baz': 'qux',
                },
                'foobar': 'bazqux',
            },
            barfoo='quxbaz',
        )

        res = o.format_xml()
        response = ET.fromstring(res)
        self.assertEqual(response.tag, 'TwilioResponse')
        [root] = list(response)
        self.assertEqual(root.tag, "Response")
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
        o = Response(
            Foo={
                'Bar': {
                    'Baz': 'Qux',
                },
                'FooBar': 'BazQux',
            },
            BarFoo='QuxBaz',
        )

        res = o.format_json()
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
