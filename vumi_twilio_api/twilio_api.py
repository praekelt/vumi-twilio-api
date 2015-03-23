import json
from klein import Klein
import re
from twisted.internet.defer import inlineCallbacks
from vumi.application import ApplicationWorker
from vumi.config import ConfigInt, ConfigText
import xml.etree.ElementTree as ET


class TwilioAPIConfig(ApplicationWorker.CONFIG_CLASS):
    """Config for the Twilio API worker"""
    web_path = ConfigText(
        "The path the worker should expose the API on",
        required=True, static=True)
    web_port = ConfigInt(
        "The port the worker should open for the API",
        required=True, static=True)


class TwilioAPIWorker(ApplicationWorker):
    """Emulates the Twilio API to use vumi as if it was Twilio"""
    CONFIG_CLASS = TwilioAPIConfig

    def setup_application(self):
        """Application specific setup"""
        self.config = self.get_static_config()
        self.server = TwilioAPIServer(self)
        self.webserver = self.start_web_resources([
            (self.server.app.resource(), self.config.web_path)],
            self.config.web_port)

    @inlineCallbacks
    def teardown_application(self):
        """Clean-up of setup done in `setup_application`"""
        yield self.webserver.loseConnection()


class TwilioAPIUsageException(Exception):
    """Called when in incorrect query is sent to the API"""
    def __init__(self, message, format_='xml'):
        super(TwilioAPIUsageException, self).__init__(message)
        self.format_ = format_


class TwilioAPIServer(object):
    app = Klein()

    def __init__(self, vumi_worker):
        self.vumi_worker = vumi_worker

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
        return json.dumps(dct)

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
    def make_call(self, request, account_sid, format_):
        fields = _validate_make_call_fields(request, format_)

    def _get_field(self, request, field, default=None):
        return request.args.get(field, [default])[0]

    def _validate_make_call_required_fields(self, request, format_):
        """Validates the required fields as detailed by
        https://www.twilio.com/docs/api/rest/making-calls#post-parameters-required
        """
        #TODO: Support 'ApplicationSid' parameter
        required_fields = ['From', 'To', 'Url']
        fields = {}
        for field in required_fields:
            value = self._get_field(request, field)
            if not value:
                raise TwilioAPIUsageException(
                    'Required field %r not supplied' % field,
                    format_)
            fields[field] = value
        return fields

    def _validate_make_call_optional_fields(self, request, format_):
        """Validates the required fields as detailed by
        https://www.twilio.com/docs/api/rest/making-calls#post-parameters-optional
        """
        fields = {}
        fields['Method'] = self._get_field('Method', 'POST')
        fields['FallbackUrl'] = self._get_field('FallbackUrl')
        fields['FallbackMethod'] = self._get_field('FallbackMethod', 'POST')
        fields['StatusCallback'] = self._get_field('StatusCallback')
        fields['StatusCallbackMethod'] = self._get_field(
            'StatusCallbackMethod', 'POST')
        fields['SendDigits'] = self._get_field('SendDigits')
        if fields['SendDigits']:
            if not all(re.match('[0-9#*w]', c) for c in fields['SendDigits']):
                raise TwilioAPIUsageException(
                    "SendDigits value %r is not valid. May only contain the "
                    "characters (0-9), '#', '*' and 'w'" % fields['SendDigits'],
                    format_)
        fields['IfMachine'] = self._get_field('IfMachine')
        valid_fields_IfMachine = [None, 'Continue', 'Hangup']
        if not fields['IfMachine'] in valid_fields_IfMachine:
            raise TwilioAPIUsageException(
                "IfMachine value must be one of %r" % valid_fields_IfMachine,
                format_)
        fields['Timeout'] = self._get_field('Timeout', 60)
        fields['Record'] = self._get_field('Record', False)

    def _validate_make_call_fields(self, request, format_):
        """Validates the fields sent to the request according to
        https://www.twilio.com/docs/api/rest/making-calls"""
        fields =  self._validate_make_call_required_fields(request, format_)
        fields.update(self._validate_make_call_optional_fields(request, format_))
        return fields

