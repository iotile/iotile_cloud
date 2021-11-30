"""
Script to facilitate development by uploading (or downloading) data streams via Rest API

"""
import argparse
import csv
import getpass
import json
import logging
import os
import sys
import time
from datetime import datetime
from pprint import pprint

import dateutil.parser

from iotile_cloud.api.connection import Api

PRODUCTION_DOMAIN_NAME = 'https://iotile.cloud'
TEST_DOMAIN_NAME = 'http://127.0.0.1:8000'

logger = logging.getLogger(__name__)

global_count = 0

class StreamData(object):
    data = []
    stream_id = None

    def __init__(self, stream_id):
        self.stream_id = stream_id
        self.data = []

    def append_data(self, timestamp, value):
        self.data.append({
            'timestamp': timestamp,
            'int_value': value
        })

    def write_json(self, filename):
        with open(filename, 'w') as outfile:
            json.dump(self.data, outfile, indent = 4,)


def format_extra(page, stream_id):
    parts = {}
    parts['page'] ='{0}'.format(page)
    parts['filter']='{0}'.format(stream_id)
    return parts


def fetch_stream(c, stream_data, stream_id, skip_zeros):
    global global_count

    logger.info('Downloading data for {0}'.format(stream_id))
    page = 1
    while page:
        extra = format_extra(page=page, stream_id=stream_id)
        print('{0} ===> Downloading: {1}'.format(page, str(extra)))
        raw_data = c.data.get(**extra)
        last_zero = None
        for item in raw_data['results']:
            if 'type' in item and item['type'] == 'Num':
                if skip_zeros and item['int_value'] == 0:
                    if last_zero != None:
                        # If this is the first zero we see, record it
                        last_zero = item
                        continue
                    else:
                        last_zero = item
                else:
                    if last_zero != None:
                        # We want to store the last zero before a non-zero to get
                        # a proper graph
                        stream_data.append_data(last_zero['timestamp'], last_zero['int_value'])
                        global_count += 1
                    last_zero = None

                stream_data.append_data(item['timestamp'], item['int_value'])
                global_count += 1

        if raw_data['next']:
            print('Getting more: {0}'.format(raw_data['next']))
            page += 1
        else:
            page = 0

    print('Downloaded a total of {0} records'.format(len(stream_data.data)))


def dump_data(c, filepath, stream_id, skip_zeros=True):
    print('Fetching stream_id: {0}'.format(stream_id))
    stream_data = StreamData(stream_id)
    fetch_stream(c, stream_data, stream_id, skip_zeros )
    if len(stream_data.data):
        stream_data.write_json(filepath)

def load_data(c, filepath, stream_id, skip_zeros=True):

    if not os.path.exists(filepath):
        logger.error('File not found: {0}'.format(filepath))
        return

    new_payload = []

    last_zero = None
    with open(filepath) as data_file:
        data = json.load(data_file)
        for item in data['results']:
            new_item = {
                'stream': stream_id,
                'type': 'Num',
                'timestamp': item['timestamp'],
                'int_value': item['int_value']
            }
            if skip_zeros and item['int_value'] == 0:
                if last_zero != None:
                    # If this is the first zero we see, record it
                    last_zero = new_item
                    continue
                else:
                    last_zero = new_item
            else:
                if last_zero != None:
                    # We want to store the last zero before a non-zero to get
                    # a proper graph
                    new_payload.append(last_zero)
                last_zero = None

            new_payload.append(new_item)

    if len(new_payload):
        logger.info('---> Uploading {0} entries to {1}'.format(len(new_payload), stream_id))
        c.data.post(new_payload)


if __name__ == '__main__':
    # Test
    # Logger Format
    from logging import Formatter, StreamHandler
    FORMAT = '[%(asctime)-15s] %(levelname)-6s %(message)s'
    DATE_FORMAT = '%d/%b/%Y %H:%M:%S'
    formatter = Formatter(fmt=FORMAT, datefmt=DATE_FORMAT)
    handler = StreamHandler()
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('-u', '--user', dest='email', type=str, help='Email used for login')
    parser.add_argument('-p', '--production', dest='production', action='store_true',
                        help='Set when using production iotile.cloud')

    parser.add_argument('-d', '--dump', dest='dump', type=str, help='Dump data for given Stream')
    parser.add_argument('-l', '--load', dest='load', type=str, help='Slug for stream to load into')
    parser.add_argument('-z', '--skip-zeros', dest='skip_zeros', action='store_true', help='Skip entries with value=0')

    parser.add_argument('path', metavar='path', type=str, help='File name to download/upload')

    args = parser.parse_args()
    logger.info('--------------')

    if not args.email:
        logger.error('User email is required: --user')
        sys.exit(1)

    if args.dump and args.load:
        logger.error(('--dump and --load cannot be used together'))
        sys.exit(1)

    password = getpass.getpass()

    logger.info('production={0}'.format(args.production))
    if args.production:
        domain = PRODUCTION_DOMAIN_NAME
    else:
        domain = TEST_DOMAIN_NAME

    logger.info('Using Server: {0}'.format(domain))
    c = Api(domain)

    ok = c.login(email=args.email, password=password)
    if ok:
        logger.info('Welcome {0}'.format(args.email))

        if args.dump:
            logger.info('Dumping Data using API')
            dump_data(c, args.path, args.dump, args.skip_zeros)
            logger.info('Total number of downloaded entries: {0}'.format(global_count))

        if args.load:
            logger.info('Loading Data using API')
            load_data(c, args.path, args.load, args.skip_zeros)

        logger.info('Goodbye!!')
        c.logout()
