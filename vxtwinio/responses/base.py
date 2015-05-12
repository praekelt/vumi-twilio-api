""" Common base classes for Twilio API responses. """

import json
import re
import xml.etree.ElementTree as ET

from math import ceil

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


class Response(object):
    """ Base Response object used for HTTP responses
    """
    name = 'Response'

    def __init__(self, **kw):
        self._data = kw

    @property
    def xml(self):
        response = ET.Element("TwilioResponse")
        root = ET.SubElement(response, self.name)

        def format_xml_rec(dct, root):
            for key, value in dct.iteritems():
                if isinstance(value, dict):
                    sub = ET.SubElement(root, key)
                    format_xml_rec(value, sub)
                else:
                    sub = ET.SubElement(root, key)
                    sub.text = value
            return root

        format_xml_rec(self._data, root)
        return response

    def format_xml(self):
        return ET.tostring(self.xml)

    @property
    def dictionary(self):
        return convert_dict_keys(self._data)

    def format_json(self):
        return json.dumps(self.dictionary)

    @property
    def sid(self):
        return self._data.get("Sid")


class ListResponse(object):
    """ Used for responding to API requests with a paginated list
    """
    name = 'ListResponse'

    def __init__(self, uri, items):
        """
        :param int pagesize: The number of elements in each returned page
        :param list items: A list of Response items to be returned
        """
        self.uri = uri
        self.items = sorted(items, key=lambda k: k.sid)

    def _get_page_attributes(self, uri, page, pagesize, aftersid):
        pagesize = min(pagesize, 1000)
        numpages = int(ceil(len(self.items) * 1.0 / pagesize)) or 1
        if aftersid is not None:
            start = (
                n for n, i in enumerate(self.items) if i.sid > aftersid).next()
            page = int(start/pagesize)
        else:
            start = page * pagesize
        page_items = self.items[start:start + pagesize]
        base_uri = uri.split('?')[0]
        if len(page_items) < pagesize:
            nextpageuri = None
        else:
            nextpageuri = "%s?Page=%s&PageSize=%s&AfterSid=%s" % (
                base_uri, page + 1, pagesize, page_items[-1].sid)
        if page == 0:
            prevpageuri = None
        else:
            prevpageuri = "%s?Page=%s&PageSize=%s" % (
                base_uri, page-1, pagesize)
        last = numpages - 1

        attributes = {
            'page': page,
            'num_pages': numpages,
            'page_size': pagesize,
            'total': len(self.items),
            'start': start,
            'end': start + len(page_items),
            'uri': uri,
            'first_page_uri': '%s?Page=%s&PageSize=%s' % (
                base_uri, page, pagesize),
            'next_page_uri': nextpageuri,
            'previous_page_uri': prevpageuri,
            'last_page_uri': '%s?Page=%s&PageSize=%s' % (
                base_uri, last, pagesize),
        }

        return (attributes, page_items)

    def _format_attributes_for_xml(self, dic):
        """XML attributes must be strings"""
        ret = {}
        for key, value in dic.iteritems():
            if value is None:
                value = ''
            ret[key.replace('_', '')] = str(value)
        return ret

    def format_xml(self, page=0, pagesize=50, aftersid=None):
        response = ET.Element("TwilioResponse")
        root = ET.SubElement(response, self.name)

        root.attrib, page_items = self._get_page_attributes(
            self.uri, page, pagesize, aftersid)
        root.attrib = self._format_attributes_for_xml(root.attrib)

        for obj in page_items:
            [item] = obj.xml
            root.append(item)

        return ET.tostring(response)

    def format_json(self, page=0, pagesize=50, aftersid=None):
        attrib, page_items = self._get_page_attributes(
            self.uri, page, pagesize, aftersid)
        page_items = [item.dictionary for item in page_items]
        attrib[camel_to_snake(self.name)] = page_items
        return json.dumps(attrib)


class ErrorResponse(Response):
    """ Error HTTP response object, returned for incorred API queries
    """
    name = 'Error'

    def __init__(self, error_type, error_message):
        super(ErrorResponse, self).__init__(
            error_type=error_type, error_message=error_message)

    @classmethod
    def from_exception(cls, exception):
        return cls(exception.__class__.__name__, exception.message)
