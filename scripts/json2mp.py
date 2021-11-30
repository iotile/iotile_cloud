"""
Description: Converts a Json file to a messagePack file

Usage:

python json2mp.py myfile.json

Generates: myfile.mp

"""
import argparse
import datetime
import decimal
import json
import logging
import os
from pprint import pprint

import msgpack

logger = logging.getLogger(__name__)

class MessagePackEncoder(object):

    def encode(self, obj):
        if isinstance(obj, datetime.datetime):
            return {'__class__': 'datetime', 'as_str': obj.isoformat()}
        elif isinstance(obj, datetime.date):
            return {'__class__': 'date', 'as_str': obj.isoformat()}
        elif isinstance(obj, datetime.time):
            return {'__class__': 'time', 'as_str': obj.isoformat()}
        elif isinstance(obj, decimal.Decimal):
            return {'__class__': 'decimal', 'as_str': str(obj)}
        else:
            return obj

if __name__ == '__main__':
    from logging import Formatter, StreamHandler
    FORMAT = '[%(asctime)-15s] %(levelname)-6s %(message)s'
    DATE_FORMAT = '%d/%b/%Y %H:%M:%S'
    formatter = Formatter(fmt=FORMAT, datefmt=DATE_FORMAT)
    handler = StreamHandler()
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)

    parser = argparse.ArgumentParser(description=__doc__)

    parser.add_argument('path', metavar='path', type=str, help='JSON file name to convert')

    args = parser.parse_args()
    logger.info('--------------')

    if not os.path.isfile(args.path):
        logger.error('File not found: {}'.format(args.path))

    with open(args.path, 'rb') as fp:
        data = json.load(fp)
        fp.close()

    packaged_data = msgpack.packb(data, default=MessagePackEncoder().encode, use_bin_type=True)

    filename, ext = os.path.splitext(args.path)
    new_path = filename + '.mp'

    with open(new_path, 'wb') as fp:
        fp.write(packaged_data)
        fp.close()

    with open(new_path, 'rb') as fp:
        msgp = fp.read()
        data = msgpack.unpackb(msgp, use_list=True, raw=False)
        pprint(data)


