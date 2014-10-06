''' Consumer for Wayne State University -- Digital Commons '''

from __future__ import unicode_literals

import requests
from datetime import date, timedelta, datetime
from dateutil.parser import *
import time
from lxml import etree
from scrapi.linter import lint
from scrapi.linter.document import RawDocument, NormalizedDocument
from nameparser import HumanName
import os


NAME = "wayne"
OAI_DC_BASE_URL = 'http://digitalcommons.wayne.edu/do/oai/?verb=ListRecords'
NAMESPACES = {'dc': 'http://purl.org/dc/elements/1.1/', 
              'oai_dc': 'http://www.openarchives.org/OAI/2.0/',
              'ns0': 'http://www.openarchives.org/OAI/2.0/'}
DEFAULT = datetime(1970, 01, 01)
DEFAULT_ENCODING = 'utf-8'
record_encoding = None


def consume(days_back=5):
    start_date = date.today() - timedelta(days_back)
    url = OAI_DC_BASE_URL + '&metadataPrefix=oai_dc&from='
    url += str(start_date)
    records = get_records(url)

    xml_list = []
    for record in records:
        set_spec = record.xpath('ns0:header/ns0:setSpec/node()', namespaces=NAMESPACES)[0]
        doc_id = record.xpath('ns0:header/ns0:identifier/node()', namespaces=NAMESPACES)[0]
        record = etree.tostring(record)
        xml_list.append(RawDocument({
            'doc': record,
            'source': NAME,
            'docID': copy_to_unicode(doc_id),
            'filetype': u'xml'
        }))

    return xml_list


def get_records(url):
    data = requests.get(url)
    record_encoding = data.encoding
    doc = etree.XML(data.content)
    records = doc.xpath('//ns0:record', namespaces=NAMESPACES)
    token = doc.xpath('//ns0:resumptionToken/node()', namespaces=NAMESPACES)

    if len(token) == 1:
        time.sleep(0.5)
        url = OAI_DC_BASE_URL + '&resumptionToken=' + token[0]
        records += get_records(url)

    return records


def copy_to_unicode(element):
    encoding = record_encoding or DEFAULT_ENCODING
    element = ''.join(element)
    if isinstance(element, unicode):
        return element
    else:
        return unicode(element, encoding=encoding)


def get_contributors(record):
    contributors = record.xpath('//dc:creator/node()', namespaces=NAMESPACES)
    contributor_list = []
    for person in contributors:
        name = HumanName(person)
        contributor = {
            'prefix': name.title,
            'given': name.first,
            'middle': name.middle,
            'family': name.last,
            'suffix': name.suffix,
            'email': u'',
            'ORCID': u'',
        }
        contributor_list.append(contributor)
    return contributor_list


def get_tags(record):
    tags = record.xpath('//dc:subject/node()', namespaces=NAMESPACES)
    return [copy_to_unicode(tag.lower()) for tag in tags]


def get_ids(record, doc):
    serviceID = doc.get('docID')
    all_urls = record.xpath('//dc:identifier/node()', namespaces=NAMESPACES)
    url = ''
    for identifier in all_urls:
        if 'viewcontent' not in identifier and 'http://digitalcommons.wayne.edu' in identifier:
            url = identifier
    if url is '':
        raise Exception('Warning: No url provided!')

    return {'serviceID': copy_to_unicode(serviceID),
            'url': copy_to_unicode(url),
            'doi': ''}


def get_properties(record):
    publisher = (record.xpath('//dc:publisher/node()', namespaces=NAMESPACES))[0]
    source = (record.xpath('//dc:source/node()', namespaces=NAMESPACES))[0]
    type = (record.xpath('//dc:type/node()', namespaces=NAMESPACES))[0]
    format = (record.xpath('//dc:format/node()', namespaces=NAMESPACES))[0]
    props = {
        'type': copy_to_unicode(type),
        'source': copy_to_unicode(source),
        'format': copy_to_unicode(format),
        'publisherInfo': {
            'publisher': copy_to_unicode(publisher),
        },
    }
    return props


def get_date_created(record):
    date_created = (record.xpath('ns0:metadata/oai_dc:dc/dc:date/node()', namespaces=NAMESPACES) or [''])[0]
    a_date = parse(date_created, yearfirst=True,  default=DEFAULT).isoformat()
    return a_date


def get_date_updated(record):
    dateupdated = (record.xpath('ns0:header/ns0:datestamp/node()', namespaces=NAMESPACES) or [''])[0]
    date_updated = parse(dateupdated).isoformat()
    return date_updated


def normalize(raw_doc):
    doc = raw_doc.get('doc')
    record = etree.XML(doc)

    # # load the list of approved series_names as a file
    with open(os.path.join(os.path.dirname(__file__), 'series_names.txt')) as series_names:
        series_name_list = [word.replace('\n', '') for word in series_names]
    set_spec = record.xpath('ns0:header/ns0:setSpec/node()', namespaces=NAMESPACES)[0]

    if set_spec.replace('publication:', '') not in series_name_list:
        print('Series not in approved list, not normalizing...')
        return None

    title = record.xpath('//dc:title/node()', namespaces=NAMESPACES)[0]

    try:
        description = record.xpath('ns0:metadata/oai_dc:dc/dc:description/node()', namespaces=NAMESPACES)[0]
    except IndexError:
        description = ''

    payload = {
        'title': copy_to_unicode(title),
        'contributors': get_contributors(record),
        'properties': get_properties(record),
        'description': copy_to_unicode(description),
        'tags': get_tags(record),
        'id': get_ids(record, raw_doc),
        'source': NAME,
        'dateUpdated': copy_to_unicode(get_date_updated(record)),
        'dateCreated': copy_to_unicode(get_date_created(record)),
    }


    # import json
    # print(json.dumps(payload, indent=4))
    return NormalizedDocument(payload)
        

if __name__ == '__main__':
    print(lint(consume, normalize))
