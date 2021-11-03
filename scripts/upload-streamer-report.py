"""
Script to upload IOTile Device Streamer Reports (containing stream data)

"""
import sys
import json
import os
import datetime
import argparse
import getpass
import logging
import pytz
from pprint import pprint
from iotile_cloud.api.connection import Api
from iotile_cloud.api.exceptions import HttpClientError

PRODUCTION_DOMAIN_NAME = 'https://iotile.cloud'
STAGE_DOMAIN_NAME = 'https://cloud.corp.archsys.io'
TEST_DOMAIN_NAME = 'http://127.0.0.1:8000'

logger = logging.getLogger(__name__)
if __name__ == '__main__':
    # Test
    # Logger Format
    from logging import StreamHandler, Formatter
    FORMAT = '[%(asctime)-15s] %(levelname)-6s %(message)s'
    DATE_FORMAT = '%d/%b/%Y %H:%M:%S'
    formatter = Formatter(fmt=FORMAT, datefmt=DATE_FORMAT)
    handler = StreamHandler()
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('-u', '--user', dest='email', type=str, help='Email used for login')
    parser.add_argument('-s', '--server', dest='server', type=str,
                        default=TEST_DOMAIN_NAME, help='Server to upload to')

    parser.add_argument('file', metavar='file', type=str, help='File Path')
    parser.add_argument('-t', '-timestamp', dest='ts', type=str, help='timestamp when the gateway received the report')

    args = parser.parse_args()
    logger.info('--------------')

    if not args.email:
        logger.error('User email is required: --user')
        sys.exit(1)

    # 1.- Check that file exists
    if not os.path.exists(args.file):
        logger.error('File not found: {}'.format(args.file))
        sys.exit(1)

    password = getpass.getpass()

    domain = args.server
    logger.info('------------------------------')
    logger.info('Uploading to {}'.format(domain))
    logger.info('------------------------------')

    c = Api(domain)

    ok = c.login(email=args.email, password=password)
    if ok:
        logger.info('Welcome {0}'.format(args.email))

        logger.info('Uploading: {0}'.format(args.file))
        if not args.ts:
            ts_aware = pytz.utc.localize(datetime.datetime.utcnow())
            ts = '{}'.format(ts_aware.isoformat())
        else:
            ts = args.ts
        logger.info('timestamp {}'.format(ts))
        try:
            # resp = c.streamer().report.upload_file(filename=args.file, timestamp=ts)
            with open(args.file, 'rb') as fp:
                resp = c.streamer().report.upload_fp(fp=fp, timestamp=ts)
            pprint(resp)
        except HttpClientError as e:
            logger.error(e)
            for item in json.loads(e.content.decode()):
                logger.error(item)

        logger.info('Goodbye!!')
        c.logout()
