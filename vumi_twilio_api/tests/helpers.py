from klein import Klein
from twisted.internet import reactor
from twisted.internet.defer import inlineCallbacks
from vumi.tests.helpers import IHelper
from vumi.utils import LogFilterSite
from zope.interface import implements


class TwiMLServer(object):
    """
    Server to give TwiML to requests and to store requests.
    """
    implements(IHelper)
    app = Klein()

    def __init__(self, responses={}):
        self._responses = responses.copy()
        self.requests = []

    def add_response(self, filename, response):
        """
        :param string filename: relative web path to link response to:
        :param twiml.Response response: twiml Response object to return:
        """
        self._responses[filename] = response

    def add_err(self, filename, err):
        """
        :param string filename: relative web path to link response to:
        :param string err: error message to response with:
        """
        self._responses[filename] = Exception(err)

    @app.route('/<string:filename>')
    def get_twiml(self, request, filename):
        self.requests.append({
            'filename': filename,
            'request': request,
        })
        response = self._responses[filename]
        if isinstance(response, Exception):
            request.setResponseCode(500)
            return response.message
        request.setHeader('Content-Type', 'application/xml')
        return str(self._responses[filename])

    @app.route('/')
    def get_root(self, request):
        return self.get_twiml(request, '')

    @inlineCallbacks
    def setup(self, responses={}):
        site_factory = LogFilterSite(self.app.resource())
        self._webserver = yield reactor.listenTCP(
            0, site_factory, interface='127.0.0.1')
        self.addr = self._webserver.getHost()
        self.url = "http://%s:%s/" % (self.addr.host, self.addr.port)

    @inlineCallbacks
    def cleanup(self):
        yield self._webserver.stopListening()
        yield self._webserver.loseConnection()
