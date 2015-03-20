from klein import Klein
from vumi.application import ApplicationWorker
from vumi.config import ConfigInt, ConfigText

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

    def teardown_application(self):
        """Clean-up of setup done in `setup_application`"""
        yield self.webserver.loseConnection()


class TwilioAPIServer(object):
    app = Klein()

    def __init__(self, vumi_worker):
        self.vumi_worker = vumi_worker
    
    @app.route('/Accounts/<string:account_sid>/Calls<string:form>', methods=['POST'])
    def create_call(self, request, account_sid, form):
        print request
        print account_sid
        print form
        return ''

