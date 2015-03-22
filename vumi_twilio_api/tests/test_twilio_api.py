import treq
from twilio.rest import TwilioRestClient
from twisted.internet.defer import inlineCallbacks
from twisted.trial.unittest import TestCase
from vumi.application.tests.helpers import ApplicationHelper
from vumi.tests.helpers import VumiTestCase

from vumi_twilio_api.twilio_api import TwilioAPIServer, TwilioAPIWorker

import requests

class TwilioAPIServer(VumiTestCase):

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

