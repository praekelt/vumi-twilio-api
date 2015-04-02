from datetime import datetime
from dateutil.tz import tzutc
import json
from klein import Klein
import os
import re
import treq
from twisted.internet.defer import inlineCallbacks, returnValue
import uuid
from vumi.application import ApplicationWorker
from vumi.components.message_store import MessageStore
from vumi.components.session import SessionManager
from vumi.config import ConfigDict, ConfigInt, ConfigRiak, ConfigText
from vumi.message import TransportUserMessage
from vumi.persist.txredis_manager import TxRedisManager
from vumi.persist.txriak_manager import TxRiakManager
import xml.etree.ElementTree as ET

from vumi_twilio_api.twiml_parser import TwiMLParser


c2s = re.compile('(?!^)([A-Z+])')


def camel_to_snake(string):
    return c2s.sub(r'_\1', string).lower()


def convert_dict_keys(dct):
    res = {}
    for key, value in dct.iteritems():
        if isinstance(value, dict):
            res[camel_to_snake(key)] = convert_dict_keys(value)
        else:
            res[camel_to_snake(key)] = value
    return res


class TwilioAPIConfig(ApplicationWorker.CONFIG_CLASS):
    """Config for the Twilio API worker"""
    web_path = ConfigText(
        "The path the worker should expose the API on",
        required=True, static=True)
    web_port = ConfigInt(
        "The port the worker should open for the API",
        required=True, static=True)
    api_version = ConfigText(
        "The version of the API, used in the api URL",
        default="2010-04-01", static=True)
    redis_manager = ConfigDict("Redis config.", required=True, static=True)
    riak_manager = ConfigRiak("Riak config.", required=True, static=True)
    client_path = ConfigText(
        "The web path that the API worker should send requests to",
        required=True, static=True)
    client_method = ConfigText(
        "The HTTP method that the API worker uses when sending requests",
        default='POST', static=True)
    status_callback_path = ConfigText(
        "The web path that the API sends a request to when the call ends",
        default=None, static=True)
    status_callback_method = ConfigText(
        "The HTTP method to use when sending the callback status",
        default='POST', static=True)


class TwilioAPIWorker(ApplicationWorker):
    """Emulates the Twilio API to use vumi as if it was Twilio"""
    CONFIG_CLASS = TwilioAPIConfig

    @inlineCallbacks
    def setup_application(self):
        """Application specific setup"""
        self.config = self.get_static_config()
        self.server = TwilioAPIServer(self, self.config.api_version)
        path = os.path.join(self.config.web_path, self.config.api_version)
        self.webserver = self.start_web_resources([
            (self.server.app.resource(), path)],
            self.config.web_port)
        redis = yield TxRedisManager.from_config(self.config.redis_manager)
        riak = yield TxRiakManager.from_config(self.config.riak_manager)
        self.session_manager = SessionManager(redis)
        self.message_store = MessageStore(riak, redis)
        self.twiml_parser = TwiMLParser()

    @inlineCallbacks
    def teardown_application(self):
        """Clean-up of setup done in `setup_application`"""
        yield self.webserver.loseConnection()
        yield self.session_manager.stop()

    def _http_request(self, url='', method='GET', data={}):
        return treq.request(method, url, persistent=False, data=data)

    def _request_data_from_session(self, session):
        return {
            'CallSid': session['CallId'],
            'AccountSid': session['AccountSid'],
            'From': session['From'],
            'To': session['To'],
            'CallStatus': session['Status'],
            'ApiVersion': self.config.api_version,
            'Direction': session['Direction'],
        }

    @inlineCallbacks
    def _get_twiml_from_client(self, session):
        data = self._request_data_from_session(session)
        twiml_raw = yield self._http_request(
            session['Url'], session['Method'], data)
        if twiml_raw.code < 200 or twiml_raw.code >= 300:
            twiml_raw = yield self._http_request(
                session['FallbackUrl'], session['FallbackMethod'], data)
        twiml_raw = yield twiml_raw.content()
        returnValue(self.twiml_parser.parse(twiml_raw))

    @inlineCallbacks
    def _handle_connected_call(
            self, session_id, session, status='in-progress'):
        # TODO: Support sending ForwardedFrom parameter
        # TODO: Support sending CallerName parameter
        # TODO: Support sending geographic data parameters
        session['Status'] = status
        self.session_manager.save_session(session_id, session)
        twiml = yield self._get_twiml_from_client(session)
        for verb in twiml:
            self._handle_twiml_verb(verb)

    def _handle_twiml_verb(self, verb):
        pass

    @inlineCallbacks
    def consume_ack(self, event):
        message_id = event['user_message_id']
        message = yield self.message_store.get_outbound_message(message_id)
        session = yield self.session_manager.load_session(message['to_addr'])

        if session['Status'] == 'queued':
            yield self._handle_connected_call(message['to_addr'], session)

    @inlineCallbacks
    def consume_nack(self, event):
        message_id = event['user_message_id']
        message = yield self.message_store.get_outbound_message(message_id)
        session = yield self.session_manager.load_session(message['to_addr'])

        if session['Status'] == 'queued':
            yield self._handle_connected_call(
                message['to_addr'], session, status='failed')

    @inlineCallbacks
    def new_session(self, message):
        yield self.message_store.add_inbound_message(message)
        session = {
            'CallId': self.server._get_sid(),
            'AccountSid': self.server._get_sid(),
            'From': message['from_addr'],
            'To': message['to_addr'],
            'Status': 'in-progress',
            'Direction': 'inbound',
            'Url': self.config.client_path,
            'Method': self.config.client_method,
            'StatusCallback': self.config.status_callback_path,
            'StatusCallbackMethod': self.config.status_callback_method,
        }
        yield self.session_manager.create_session(
            message['from_addr'], **session)

        twiml = yield self._get_twiml_from_client(session)
        for verb in twiml:
            self._handle_twiml_verb(verb)

    @inlineCallbacks
    def close_session(self, message):
        # TODO: Implement call duration parameters
        # TODO: Implement recording parameters
        yield self.message_store.add_inbound_message(message)
        session = yield self.session_manager.load_session(message['from_addr'])
        yield self.session_manager.clear_session(message['from_addr'])
        url = session.get('StatusCallback')

        if url and url != 'None':
            session['Status'] = 'completed'
            data = self._request_data_from_session(session)
            yield self._http_request(
                session['StatusCallback'], session['StatusCallbackMethod'],
                data)


class TwilioAPIUsageException(Exception):
    """Called when in incorrect query is sent to the API"""
    def __init__(self, message, format_='xml'):
        super(TwilioAPIUsageException, self).__init__(message)
        self.format_ = format_


class Error(object):
    """Error HTTP response object, returned for incorred API queries"""
    def __init__(self, error_type, error_message):
        self.error_type = error_type
        self.error_message = error_message

    @classmethod
    def from_exception(cls, exception):
        return cls(exception.__class__.__name__, exception.message)


class Version(object):
    """Version HTTP response object, returned for root resource"""
    def __init__(self, name, uri, **kwargs):
        self.Name = name
        self.Uri = uri
        self.SubresourceUris = kwargs


class Call(object):
    """Call HTTP response object, returned for the Calls resource"""
    def __init__(self, **kwargs):
        for key, value in kwargs.iteritems():
            setattr(self, key, value)


class TwilioAPIServer(object):
    app = Klein()

    def __init__(self, vumi_worker, version):
        self.vumi_worker = vumi_worker
        self.version = version

    @staticmethod
    def format_xml(obj):
        response = ET.Element("TwilioResponse")
        root = ET.SubElement(response, obj.__class__.__name__)

        def format_xml_rec(dct, root):
            for key, value in dct.iteritems():
                if isinstance(value, dict):
                    sub = ET.SubElement(root, key)
                    format_xml_rec(value, sub)
                else:
                    sub = ET.SubElement(root, key)
                    sub.text = value
            return root

        format_xml_rec(obj.__dict__, root)
        return ET.tostring(response)

    @staticmethod
    def format_json(obj):
        return json.dumps(convert_dict_keys(obj.__dict__))

    def _format_response(self, request, dct, format_):
        format_ = str(format_.lstrip('.').lower()) or 'xml'
        func = getattr(
            TwilioAPIServer, 'format_' + format_, None)
        if not func:
            raise TwilioAPIUsageException(
                '%r is not a valid request format' % format_)
        request.setHeader('Content-Type', 'application/%s' % format_)
        return func(dct)

    @app.handle_errors(TwilioAPIUsageException)
    def usage_exception(self, request, failure):
        request.setResponseCode(400)
        return self._format_response(
            request, Error.from_exception(failure.value),
            failure.value.format_)

    @app.route('/', defaults={'format_': ''}, methods=['GET'])
    @app.route('/<string:format_>', methods=['GET'])
    def root(self, request, format_):
        version = Version(
            self.version,
            '/%s%s' % (self.version, format_),
            Accounts='/%s/Accounts%s' % (self.version, format_))
        return self._format_response(request, version, format_)

    @app.route(
        '/Accounts/<string:account_sid>/Calls',
        defaults={'format_': ''},
        methods=['POST'])
    @app.route(
        '/Accounts/<string:account_sid>/Calls<string:format_>',
        methods=['POST'])
    @inlineCallbacks
    def make_call(self, request, account_sid, format_):
        """Making calls endpoint
        https://www.twilio.com/docs/api/rest/making-calls"""
        # TODO: Support ApplicationSid field
        # TODO: Support SendDigits field
        # TODO: Support IfMachine field
        # TODO: Support Timeout field
        # TODO: Support Record field
        fields = self._validate_make_call_fields(request, format_)
        fields['AccountSid'] = account_sid
        fields['CallId'] = self._get_sid()
        fields['DateCreated'] = self._get_timestamp()
        fields['Uri'] = '/%s/Accounts/%s/Calls/%s' % (
            self.version, account_sid, fields['CallId'])
        fields['Status'] = 'queued'
        fields['Direction'] = 'outbound-api'
        message = yield self.vumi_worker.send_to(
            fields['To'], '',
            from_addr=fields['From'],
            session_event=TransportUserMessage.SESSION_NEW,
            to_addr_type=TransportUserMessage.AT_MSISDN,
            from_addr_type=TransportUserMessage.AT_MSISDN
        )
        yield self.vumi_worker.message_store.add_outbound_message(message)
        yield self.vumi_worker.session_manager.create_session(
            message['to_addr'], **fields)
        returnValue(self._format_response(request, Call(
            **{
                'Sid': fields['CallId'],
                'DateCreated': fields['DateCreated'],
                'DateUpdated': fields['DateCreated'],
                'ParentCallSid': None,
                'AccountSid': account_sid,
                'To': fields['To'],
                'FormattedTo': fields['To'],
                'From': fields['From'],
                'FormattedFrom': fields['From'],
                'PhoneNumberSid': None,
                'Status': fields['Status'],
                'StartTime': None,
                'EndTime': None,
                'Duration': None,
                'Price': None,
                'Direction': fields['Direction'],
                'AnsweredBy': None,
                'ApiVersion': self.version,
                'ForwardedFrom': None,
                'CallerName': None,
                'Uri': '%s%s' % (fields['Uri'], format_),
                'SubresourceUris': {
                    'Notifications': '%s/Notifications%s' % (
                        fields['Uri'], format_),
                    'Recordings': '%s/Recordings%s' % (fields['Uri'], format_),
                }
            }), format_))

    def _get_sid(self):
        return str(uuid.uuid4()).replace('-', '')

    def _get_timestamp(self):
        return datetime.now(tzutc()).strftime('%a, %d %b %Y %H:%M:%S %z')

    def _get_field(self, request, field, default=None):
        return request.args.get(field, [default])[0]

    def _validate_make_call_required_fields(self, request, format_):
        """Validates the required fields as detailed by
        https://www.twilio.com/docs/api/rest/making-calls#post-parameters-required
        """
        fields = {}
        for field in ['From', 'To', 'Url', 'ApplicationSid']:
            fields[field] = self._get_field(request, field)

        for field in ['From', 'To']:
            if not fields[field]:
                raise TwilioAPIUsageException(
                    'Required field %r not supplied' % field, format_)

        if not (fields['Url'] or fields['ApplicationSid']):
            raise TwilioAPIUsageException(
                "Request must have an 'Url' or an 'ApplicationSid' field",
                format_)

        return fields

    def _validate_make_call_optional_fields(self, request, format_):
        """Validates the required fields as detailed by
        https://www.twilio.com/docs/api/rest/making-calls#post-parameters-optional
        """
        fields = {}
        for field, default in [
                ('Method', 'POST'), ('FallbackMethod', 'POST'),
                ('StatusCallbackMethod', 'POST'), ('Timeout', 60),
                ('Record', False)]:
            fields[field] = self._get_field(request, field, default)
        for field in [
                'FallbackUrl', 'StatusCallback', 'SendDigits', 'IfMachine']:
            fields[field] = self._get_field(request, field)

        if fields['SendDigits']:
            if not all(re.match('[0-9#*w]', c) for c in fields['SendDigits']):
                raise TwilioAPIUsageException(
                    "SendDigits value %r is not valid. May only contain the "
                    "characters (0-9), '#', '*' and 'w'" % (
                        fields['SendDigits']),
                    format_)

        valid_fields_IfMachine = [None, 'Continue', 'Hangup']
        if fields['IfMachine'] not in valid_fields_IfMachine:
            raise TwilioAPIUsageException(
                "IfMachine value must be one of %r" % valid_fields_IfMachine,
                format_)

        return fields

    def _validate_make_call_fields(self, request, format_):
        """Validates the fields sent to the request according to
        https://www.twilio.com/docs/api/rest/making-calls"""
        fields = self._validate_make_call_required_fields(request, format_)
        fields.update(
            self._validate_make_call_optional_fields(request, format_))
        return fields
