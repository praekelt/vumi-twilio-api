Vumi Twilio API
===============

|travis-ci| |coveralls|

.. |travis-ci| image:: https://travis-ci.org/praekelt/vumi-twilio-api.svg
    :alt: CI build status
    :scale: 100%
    :target: https://travis-ci.org/praekelt/vumi-twilio-api

.. |coveralls| image:: https://coveralls.io/repos/praekelt/vumi-twilio-api/badge.svg?branch=develop
    :alt: Coverage status
    :scale: 100%
    :target: https://coveralls.io/r/praekelt/vumi-twilio-api?branch=develop


Provides a REST API to vumi that emulates the twilio API.

To run the tests::

    $ python setup.py install
    $ pip install -r requirements-dev.pip
    $ trial vumi_twilio_api
