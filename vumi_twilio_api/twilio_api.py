import json
from klein import Klein
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
        format_ = format_.lstrip('.').lower()
        func = getattr(TwilioAPIServer, 'format_' + format_, TwilioAPIServer.format_xml)
        request.setHeader('Content-Type', 'application/%s' % format_)
        return func(dct)

    @app.route('/', defaults={'format_': 'xml'}, methods=['GET'])
    @app.route('/<string:format_>', methods=['GET'])
    def root(self, request, format_):
        ret = {}
        return self._format_response(request, ret, format_)
