from datetime import datetime
from dateutil.tz import tzlocal
import json
from klein import Klein
import os
import re
from twisted.internet.defer import inlineCallbacks, returnValue
import uuid
from vumi.application import ApplicationWorker
from vumi.components.session import SessionManager
from vumi.config import ConfigDict, ConfigInt, ConfigText
from vumi.message import TransportUserMessage
import xml.etree.ElementTree as ET


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
    redis_manager = ConfigDict("Redis config.", static=True)


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
        self.session_manager = yield SessionManager.from_redis_config(
            self.config.redis_manager)

    @inlineCallbacks
    def teardown_application(self):
        """Clean-up of setup done in `setup_application`"""
        yield self.webserver.loseConnection()
        yield self.session_manager.stop()


class TwilioAPIUsageException(Exception):
    """Called when in incorrect query is sent to the API"""
    def __init__(self, message, format_='xml'):
        super(TwilioAPIUsageException, self).__init__(message)
        self.format_ = format_


class TwilioAPIServer(object):
    app = Klein()

    def __init__(self, vumi_worker, version):
        self.vumi_worker = vumi_worker
        self.version = version

    @staticmethod
    def format_xml(dct, root=None):
        if root is None:
            root = ET.Element('TwilioResponse')
        for key, value in dct.iteritems():
            if isinstance(value, dict):
                sub = ET.SubElement(root, key)
                TwilioAPIServer.format_xml(value, root=sub)
            else:
                sub = ET.SubElement(root, key)
                sub.text = value
        return ET.tostring(root)

    @staticmethod
    def format_json(dct):
        if dct.get('Call'):
            dct = dct['Call']
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

        return json.dumps(convert_dict_keys(dct))

    def _format_response(self, request, dct, format_):
        format_ = str(format_.lstrip('.').lower())
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
            request, {
                'error_type': 'UsageError',
                'error_message': failure.value.message
                },
            failure.value.format_)

    @app.route('/', defaults={'format_': 'xml'}, methods=['GET'])
    @app.route('/<string:format_>', methods=['GET'])
    def root(self, request, format_):
        ret = {}
        return self._format_response(request, ret, format_)

    @app.route(
        '/Accounts/<string:account_sid>/Calls',
        defaults={'format_': 'xml'},
        methods=['POST'])
    @app.route(
        '/Accounts/<string:account_sid>/Calls<string:format_>',
        methods=['POST'])
    @inlineCallbacks
    def make_call(self, request, account_sid, format_):
        """Making calls endpoint
        https://www.twilio.com/docs/api/rest/making-calls"""
        #TODO: Support ApplicationSid field
        #TODO: Support SendDigits field
        #TODO: Support IfMachine field
        #TODO: Support Timeout field
        #TODO: Support Record field
        fields = self._validate_make_call_fields(request, format_)
        fields['AccountSid'] = account_sid
        fields['CallId'] = self._get_sid()
        fields['DateCreated'] = self._get_timestamp()
        fields['Uri'] = '/%s/Accounts/%s/Calls/%s' % (self.version, account_sid, fields['CallId'])
        message = yield self.vumi_worker.send_to(
            fields['To'], '',
            from_addr=fields['From'],
            session_event=TransportUserMessage.SESSION_NEW,
            to_addr_type=TransportUserMessage.AT_MSISDN,
            from_addr_type=TransportUserMessage.AT_MSISDN
        )
        yield self.vumi_worker.session_manager.create_session(
            message['message_id'], **fields)
        returnValue(self._format_response(request, {
            'Call': {
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
                'Status': 'queued',
                'StartTime': None,
                'EndTime': None,
                'Duration': None,
                'Price': None,
                'Direction': 'outbound-api',
                'AnsweredBy': None,
                'ApiVersion': self.version,
                'ForwardedFrom': None,
                'CallerName': None,
                'Uri': fields['Uri'],
                'SubresourceUris': {
                    'Notifications': '%s/Notifications' % fields['Uri'],
                    'Recordings': '%s/Recordings' % fields['Uri'],
                }
            }
        }, format_))

    def _get_sid(self):
        return str(uuid.uuid4()).replace('-', '')

    def _get_timestamp(self):
        return datetime.now(tzlocal()).strftime('%a, %d %v %y %H:%M:%S %z')

    def _get_field(self, request, field, default=None):
        return request.args.get(field, [default])[0]

    def _validate_make_call_required_fields(self, request, format_):
        """Validates the required fields as detailed by
        https://www.twilio.com/docs/api/rest/making-calls#post-parameters-required
        """
        required_fields = ['From', 'To']
        fields = {}
        for field in required_fields:
            value = self._get_field(request, field)
            if not value:
                raise TwilioAPIUsageException(
                    'Required field %r not supplied' % field,
                    format_)
            fields[field] = value
        fields['Url'] = self._get_field(request, 'Url')
        fields['ApplicationSid'] = self._get_field(request, 'ApplicationSid')
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
        fields['Method'] = self._get_field(request, 'Method', 'POST')
        fields['FallbackUrl'] = self._get_field(request, 'FallbackUrl')
        fields['FallbackMethod'] = self._get_field(request, 'FallbackMethod', 'POST')
        fields['StatusCallback'] = self._get_field(request, 'StatusCallback')
        fields['StatusCallbackMethod'] = self._get_field(
            request, 'StatusCallbackMethod', 'POST')
        fields['SendDigits'] = self._get_field(request, 'SendDigits')
        if fields['SendDigits']:
            if not all(re.match('[0-9#*w]', c) for c in fields['SendDigits']):
                raise TwilioAPIUsageException(
                    "SendDigits value %r is not valid. May only contain the "
                    "characters (0-9), '#', '*' and 'w'" % fields['SendDigits'],
                    format_)
        fields['IfMachine'] = self._get_field(request, 'IfMachine')
        valid_fields_IfMachine = [None, 'Continue', 'Hangup']
        if fields['IfMachine'] not in valid_fields_IfMachine:
            raise TwilioAPIUsageException(
                "IfMachine value must be one of %r" % valid_fields_IfMachine,
                format_)
        fields['Timeout'] = self._get_field(request, 'Timeout', 60)
        fields['Record'] = self._get_field(request, 'Record', False)
        return fields

    def _validate_make_call_fields(self, request, format_):
        """Validates the fields sent to the request according to
        https://www.twilio.com/docs/api/rest/making-calls"""
        fields =  self._validate_make_call_required_fields(request, format_)
        fields.update(self._validate_make_call_optional_fields(request, format_))
        return fields

