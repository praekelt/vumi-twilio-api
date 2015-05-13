import json
import math
import xml.etree.ElementTree as ET

from twisted.trial.unittest import TestCase

from vxtwinio.responses import Response, ListResponse


class TestResponseFormatting(TestCase):

    def test_format_xml(self):
        o = Response(
            foo={
                'bar': {
                    'baz': 'qux',
                },
                'foobar': 'bazqux',
            },
            barfoo='quxbaz',
        )

        res = o.format_xml()
        response = ET.fromstring(res)
        self.assertEqual(response.tag, 'TwilioResponse')
        [root] = list(response)
        self.assertEqual(root.tag, "Response")
        [barfoo, foo] = sorted(root, key=lambda c: c.tag)
        self.assertEqual(foo.tag, 'foo')
        self.assertEqual(barfoo.tag, 'barfoo')
        self.assertEqual(barfoo.text, 'quxbaz')
        [bar, foobar] = sorted(foo, key=lambda c: c.tag)
        self.assertEqual(bar.tag, 'bar')
        self.assertEqual(foobar.tag, 'foobar')
        self.assertEqual(foobar.text, 'bazqux')
        [baz] = list(bar)
        self.assertEqual(baz.tag, 'baz')
        self.assertEqual(baz.text, 'qux')

    def test_format_json(self):
        o = Response(
            Foo={
                'Bar': {
                    'Baz': 'Qux',
                },
                'FooBar': 'BazQux',
            },
            BarFoo='QuxBaz',
        )

        res = o.format_json()
        root = json.loads(res)
        expected = {
            'foo': {
                'bar': {
                    'baz': 'Qux',
                },
                'foo_bar': 'BazQux',
            },
            'bar_foo': 'QuxBaz',
        }
        self.assertEqual(root, expected)


class TestListResponse(TestCase):
    def assertAttributesXML(self, attr, **kw):
        page = kw.get('page', 0)
        self.assertEqual(attr['page'], str(page))
        pagesize = kw.get('pagesize', 50)
        self.assertEqual(attr['pagesize'], str(pagesize))
        total = kw.get('total', 0)
        self.assertEqual(attr['total'], str(total))
        numpages = kw.get('numpages', int(math.ceil(total*1.0/pagesize)) or 1)
        self.assertEqual(attr['numpages'], str(numpages))
        start = kw.get('start', 0)
        self.assertEqual(attr['start'], str(start))
        end = kw.get('end', min(total, start + pagesize))
        self.assertEqual(attr['end'], str(end))
        uri = kw.get('uri')
        self.assertEqual(attr['uri'], uri)
        firstpageuri = '%s?Page=%s&PageSize=%s' % (uri, page, pagesize)
        self.assertEqual(attr['firstpageuri'], firstpageuri)
        if page == 0:
            previouspageuri = ''
        else:
            previouspageuri = '%s?Page=%s&PageSize=%s' % (
                uri, page - 1, pagesize)
        self.assertEqual(attr['previouspageuri'], previouspageuri)
        if kw.get('nextpage_aftersid'):
            nextpageuri = '%s?Page=%s&PageSize=%s&AfterSid=%s' % (
                uri, page + 1, pagesize, kw['nextpage_aftersid'])
        else:
            nextpageuri = ''
        self.assertEqual(attr['nextpageuri'], nextpageuri)
        lastpageuri = '%s?Page=%s&PageSize=%s' % (uri, numpages - 1, pagesize)
        self.assertEqual(attr['lastpageuri'], lastpageuri)

    def assertAttributesJSON(self, attr, **kw):
        page = kw.get('page', 0)
        self.assertEqual(attr['page'], page)
        pagesize = kw.get('pagesize', 50)
        self.assertEqual(attr['page_size'], pagesize)
        total = kw.get('total', 0)
        self.assertEqual(attr['total'], total)
        numpages = kw.get('numpages', int(math.ceil(total*1.0/pagesize)) or 1)
        self.assertEqual(attr['num_pages'], numpages)
        start = kw.get('start', 0)
        self.assertEqual(attr['start'], start)
        end = kw.get('end', min(total, start + pagesize))
        self.assertEqual(attr['end'], end)
        uri = kw.get('uri')
        self.assertEqual(attr['uri'], uri)
        firstpageuri = '%s?Page=%s&PageSize=%s' % (uri, page, pagesize)
        self.assertEqual(attr['first_page_uri'], firstpageuri)
        if page == 0:
            previouspageuri = None
        else:
            previouspageuri = '%s?Page=%s&PageSize=%s' % (
                uri, page - 1, pagesize)
        self.assertEqual(attr['previous_page_uri'], previouspageuri)
        if kw.get('nextpage_aftersid'):
            nextpageuri = '%s?Page=%s&PageSize=%s&AfterSid=%s' % (
                uri, page + 1, pagesize, kw['nextpage_aftersid'])
        else:
            nextpageuri = None
        self.assertEqual(attr['next_page_uri'], nextpageuri)
        lastpageuri = '%s?Page=%s&PageSize=%s' % (uri, numpages - 1, pagesize)
        self.assertEqual(attr['last_page_uri'], lastpageuri)

    def test_format_xml_defaults(self):
        """Default attributes should be correct for formatting xml"""
        o = ListResponse('test_url', [])
        xml = o.format_xml()
        response = ET.fromstring(xml)

        self.assertEqual(response.tag, 'TwilioResponse')
        [root] = response
        self.assertEqual(root.tag, 'ListResponse')
        self.assertAttributesXML(root.attrib, uri='test_url')

        children = list(root)
        self.assertEqual(children, [])

    def test_format_xml_one_page(self):
        o = ListResponse('test_url', [Response(Sid='1')])
        xml = o.format_xml(pagesize=2)
        response = ET.fromstring(xml)

        self.assertEqual(response.tag, 'TwilioResponse')
        [root] = response
        self.assertEqual(root.tag, 'ListResponse')
        self.assertAttributesXML(
            root.attrib, uri='test_url', pagesize=2, total=1)

        [child] = root
        self.assertEqual(child.tag, 'Response')
        [i] = child
        self.assertEqual(i.tag, 'Sid')
        self.assertEqual(i.text, '1')

    def test_format_xml_multiple_pages(self):
        o = ListResponse('test_url', [Response(Sid=str(i)) for i in range(3)])
        xml = o.format_xml(pagesize=2)
        response = ET.fromstring(xml)

        self.assertEqual(response.tag, 'TwilioResponse')
        [root] = response
        self.assertEqual(root.tag, 'ListResponse')
        self.assertAttributesXML(
            root.attrib, pagesize=2, total=3, uri='test_url',
            nextpage_aftersid='1')
        for i in range(2):
            self.assertEqual(root[i].tag, 'Response')
            [sid] = root[i]
            self.assertEqual(sid.tag, 'Sid')
            self.assertEqual(sid.text, str(i))

        xml = o.format_xml('test_url', pagesize=2, aftersid='1')
        response = ET.fromstring(xml)
        self.assertEqual(response.tag, 'TwilioResponse')

        [root] = response
        self.assertEqual(root.tag, 'ListResponse')
        self.assertAttributesXML(
            root.attrib, pagesize=2, total=3, uri='test_url', start=2, page=1)
        [child] = root
        self.assertEqual(child.tag, 'Response')
        [i] = child
        self.assertEqual(i.tag, 'Sid')
        self.assertEqual(i.text, '2')

    def test_format_xml_maximum_pages(self):
        o = ListResponse(
            'test_url', [Response(Sid=str(i)) for i in range(1001)])
        xml = o.format_xml(pagesize=1001)
        response = ET.fromstring(xml)

        self.assertEqual(response.tag, 'TwilioResponse')
        [root] = response
        self.assertEqual(root.tag, 'ListResponse')
        self.assertAttributesXML(
            root.attrib, pagesize=1000, total=1001, uri='test_url',
            nextpage_aftersid=998)
        for i in range(1000):
            self.assertEqual(root[i].tag, 'Response')
            self.assertEqual(root[i][0].tag, 'Sid')

        sids = sorted(i[0].text for i in root)

        xml = o.format_xml(pagesize=1001, page=1)
        response = ET.fromstring(xml)
        self.assertEqual(response.tag, 'TwilioResponse')

        [root] = response
        self.assertEqual(root.tag, 'ListResponse')
        self.assertAttributesXML(
            root.attrib, pagesize=1000, total=1001, uri='test_url', page=1,
            start=1000)
        [child] = root
        self.assertEqual(child.tag, 'Response')
        [i] = child
        self.assertEqual(i.tag, 'Sid')
        sids.append(i.text)
        self.assertEqual(sorted(str(i) for i in xrange(1001)), sids)

    def test_format_json_defaults(self):
        """Default attributes should be correct for formatting json"""
        o = ListResponse('test_url', [])
        text = o.format_json()
        response = json.loads(text)

        self.assertAttributesJSON(response, uri='test_url')
        self.assertEqual(response['list_response'], [])

    def test_format_json_one_page(self):
        o = ListResponse('test_url', [Response(i='1')])
        text = o.format_json(pagesize=2)
        response = json.loads(text)

        self.assertAttributesJSON(
            response, uri='test_url', pagesize=2, total=1)
        self.assertEqual(response['list_response'], [{'i': '1'}])

    def test_format_json_multiple_pages(self):
        o = ListResponse('test_url', [Response(Sid=str(i)) for i in range(3)])
        text = o.format_json(pagesize=2)
        response = json.loads(text)

        self.assertAttributesJSON(
            response, pagesize=2, total=3, uri='test_url', nextpage_aftersid=1)
        data = [{'sid': str(i)} for i in range(2)]
        self.assertEqual(
            sorted(response['list_response'], key=lambda i: i['sid']),
            data)

        text = o.format_json('test_url', pagesize=2, aftersid='1')
        response = json.loads(text)

        self.assertAttributesJSON(
            response, pagesize=2, total=3, uri='test_url', page=1, start=2)
        self.assertEqual(response['list_response'], [{'sid': '2'}])

    def test_format_json_maximum_pages(self):
        o = ListResponse(
            'test_url', [Response(Sid=str(i)) for i in range(1001)])
        text = o.format_json(pagesize=1001)
        response = json.loads(text)

        self.assertAttributesJSON(
            response, pagesize=1000, total=1001, uri='test_url',
            nextpage_aftersid=998)
        sids = [i['sid'] for i in response['list_response']]

        text = o.format_json(pagesize=1001, page=1)
        response = json.loads(text)

        self.assertAttributesJSON(
            response, pagesize=1000, total=1001, uri='test_url', page=1,
            start=1000)
        sids.append(response['list_response'][0]['sid'])
        self.assertEqual(sorted(str(i) for i in xrange(1001)), sids)
