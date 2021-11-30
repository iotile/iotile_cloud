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

    filename, ext = os.path.splitext(args.path)

    with open(args.path, 'rb') as fp:
        msgp = fp.read()
        data = msgpack.unpackb(msgp, use_list=True, raw=False)
        # pprint(data)

    new_path = filename + '.json'

    with open(new_path, 'w') as fp:
        json.dump(data, fp, indent=4)
        fp.close()




