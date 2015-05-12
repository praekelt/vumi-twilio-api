""" IncomingPhoneNumber list responses. """

from .base import ListResponse


class IncomingPhoneNumbers(ListResponse):
    """ Used for responding with a list of phone numnbers for the
        IncomingPhoneNumbers resource.
        """

    name = 'IncomingPhoneNumbers'
