import logging
import struct
import hashlib
import hmac
import os
import sys
import pprint
import datetime
from dateutil import parser as dt_parser

"""
This script is used to parse and analyze IOTile Device Streamer Reports
Script has copy of apps.streamer.report.parser 
       TODO: Build a reusable package
       
Usage:
     python streamer-report-parser.py <file_name>
     python streamer-report-parser.py -v <file_name> # To also show all readings
"""
Y2K = datetime.datetime(2000, 1, 1)

int16gid = lambda n: '-'.join(['{:04x}'.format(n >> (i << 4) & 0xFFFF) for i in range(0, 1)[::-1]])
int64gid = lambda n: '-'.join(['{:04x}'.format(n >> (i << 4) & 0xFFFF) for i in range(0, 4)[::-1]])
formatted_gdid = lambda id: '--'.join(['d', int64gid(id)])
formatted_gtid = lambda id, index: '--'.join(['t', int64gid(id), int16gid(index)])

logger = logging.getLogger(__name__)

# Current Max Size of report (before the mobile is upgraded to send larger sizes)
DEFAULT_REPORT_MAX_LENGTH = 196608


"""Header Format"""
HEADER_LENGTH = 20
HEADER_FORMAT = [
    {
        'label': 'fmt',
        'type': 'B'
    },
    {
        'label': 'len_low',
        'type': 'B'
    },
    {
        'label': 'len_high',
        'type': 'H'
    },
    {
        'label': 'dev_id',
        'type': 'L'
    },
    {
        'label': 'rpt_id',
        'type': 'L'
    },
    {
        'label': 'sent_timestamp',
        'type': 'L'
    },
    {
        'label': 'signature_flags',
        'type': 'B'
    },
    {
        'label': 'streamer_index',
        'type': 'B'
    },
    {
        'label': 'streamer_selector',
        'type': 'H'
    }
]


"""Single Reading (data point) Format"""
# stream, _, reading_id, timestamp, value = unpack("<HHLLL", reading)
READINGS_LENGTH = 16
READINGS_FORMAT = [
    {
        'label': 'stream',
        'type': 'H'
    },
    {
        'label': '_',
        'type': 'H'
    },
    {
        'label': 'id',
        'type': 'L'
    },
    {
        'label': 'timestamp',
        'type': 'L'
    },
    {
        'label': 'value',
        'type': 'L'
    },
]


"""Footer Format"""
# lowest_id, highest_id, signature = unpack("<LL16s", footer)
FOOTER_LENGTH = 24
FOOTER_FORMAT = [
    {
        'label': 'lowest_id',
        'type': 'L'
    },
    {
        'label': 'highest_id',
        'type': 'L'
    },
    {
        'label': 'signature',
        'type': '16s'
    },
]


class ParseReportException(Exception):
    def __init__(self, *args, **kwargs):
        super(ParseReportException, self).__init__(*args, **kwargs)


class ReportParser(object):

    device_id = None
    report_id = None
    expected_count = None
    header = {}
    footer = {}
    length = 0
    data = []

    def __init__(self):
        self.length = 0
        self.header = {}
        self.footer = {}
        self.data = []
        self.expected_count = 0

    def _parse(self, fp, format, length):
        result = {}
        raw = fp.read(length)

        unpack_format = ''.join(['<',] + [item['type'] for item in format])

        try:
            obj = struct.unpack(unpack_format, raw)
        except Exception as e:
            raise ParseReportException(str(e))

        for i in range(len(format)):
            result[format[i]['label']] = obj[i]

        return result

    def parse_header(self, fp):
        fp.seek(0)
        self.header = self._parse(fp, HEADER_FORMAT, HEADER_LENGTH)
        if self.header['fmt'] != 1:
            raise ParseReportException('Unsupported Report Format: {}'.format(self.header['fmt']))

        logger.debug('Header: {0}'.format(str(self.header)))

        self.length = (self.header['len_high'] << 8) | self.header['len_low']
        logger.debug('length={}'.format(self.length))
        self.expected_count = (self.length - HEADER_LENGTH - FOOTER_LENGTH) / READINGS_LENGTH
        logger.debug('expected_count={0}'.format(int(self.expected_count)))
        logger.debug('device_id={0}, report_id={1}'.format(self.header['dev_id'], self.header['rpt_id']))

    def parse_footer(self, fp):
        fp.seek(-FOOTER_LENGTH, os.SEEK_END)
        self.footer = self._parse(fp, FOOTER_FORMAT, FOOTER_LENGTH)
        logger.debug('Footer: {0}'.format(str(self.footer)))
        remaining = fp.read()
        if remaining != b'':
            raise ParseReportException('Data found after footer')

    def parse_readings(self, fp):

        fp.seek(HEADER_LENGTH)
        index = 0
        while (index < self.expected_count):
            point = self._parse(fp, READINGS_FORMAT, READINGS_LENGTH)
            self.data.append(point)
            index += 1
        if len(self.data) != self.expected_count:
            msg = 'len(data)={0}, expected={1}'.format(len(self.data), self.expected_count)
            logger.error(msg)
            raise ParseReportException(msg)

    def check_report_hash(self, fp):
        """Calculate the expected hash for a report and make sure it matches what's in the footer

        Params:
            fp File Pointer as a opened stream

        Returns:
            bool: True if the hash matches, otherwise False
        """

        fp.seek(0)
        data = fp.read()
        # logger.info('Full Report File length = {}'.format(len(data)))
        hashed_component = data[:-16]
        embedded_sig = data[-16:]

        if len(embedded_sig) != 16:
            return False

        # SHA256 results are 32 bytes long. Technically we embed a SHA-256-128 hash because
        # we truncate the hash to 16 bytes
        digest = hashlib.sha256(hashed_component).digest()
        truncated_digest = digest[:16]

        # Note the use of hmac.compare_digest instead of directly comparing the bytes
        # per https://docs.python.org/2/library/hmac.html
        return hmac.compare_digest(embedded_sig, truncated_digest)

def get_utc_timestamp(base_dt, dev_timestamp):
    if bool(int(dev_timestamp) & (1 << 31)):
        ts_seconds = int(dev_timestamp) & ((1 << 31) - 1)
        delta = datetime.timedelta(seconds=ts_seconds)
        # UTC device timestamp is based on 2000-01-01
        return Y2K + delta
    else:
        return base_dt + datetime.timedelta(seconds=dev_timestamp)

        

def process_file(file_name, received_dt):
    if not os.path.exists(file_name):
        logger.error('File Not Found: {}'.format(file_name))
        sys.exit()


    with open(file_name, 'rb') as fp:
        if not args.error_only:
            logger.info('')
            logger.info('--------------------------------------------------------')
            logger.info(' Report: {}'.format(os.path.basename(file_name)))
        logger.debug(' HEADER_LENGTH={0}, FOOTER_LENGTH={1}, READINGS_LENGTH={2}'.format(HEADER_LENGTH,
                                                                                         FOOTER_LENGTH,
                                                                                         READINGS_LENGTH))
        rp = ReportParser()
        rp.parse_header(fp)
        rp.parse_footer(fp)

        if not rp.check_report_hash(fp):
            logger.error('Found errors in file {}'.format(file_name))
            logger.error('  ==> Report Hash Incorrect')

        device_slug = formatted_gdid(rp.header['dev_id'])
        streamer_index = rp.header['streamer_index']
        streamer_selector = rp.header['streamer_selector']
        streamer_slug = formatted_gtid(rp.header['dev_id'], streamer_index)
        streamer_selector_hex = int16gid(streamer_selector)
        original_first_id = rp.footer['lowest_id']
        original_last_id = rp.footer['highest_id']

        sent_timestamp = rp.header['sent_timestamp']
        assert(isinstance(sent_timestamp, int ) and sent_timestamp >= 0)
        base_dt = received_dt - datetime.timedelta(seconds=sent_timestamp)

        if not args.error_only:
            logger.info(' Dev ID (from rpt: {0}): {1}'.format(rp.header['dev_id'], device_slug))
            logger.info(' Streamer ID (index from rpt: {0}): {1}'.format(rp.header['streamer_index'], streamer_slug))
            logger.info(' Streamer Selector: 0x{0}'.format(streamer_selector_hex))
            logger.info(' Sent Timestamp (from device begining of time): {} sec'.format(sent_timestamp))
            logger.info(' Base Time (absolute: received - sent): {}'.format(base_dt))
            logger.info(' Expected range: from ID={0} to ID={1}'.format(original_first_id, original_last_id))
            logger.info(' Length: {0}, Expected Count: {1}'.format(rp.length, int(rp.expected_count)))
            if rp.length > (DEFAULT_REPORT_MAX_LENGTH - READINGS_LENGTH) and rp.length < DEFAULT_REPORT_MAX_LENGTH:
                logger.info(
                    ' -> WARNING: This report was likely chopped off (due to mobile limit={})'.format(
                        DEFAULT_REPORT_MAX_LENGTH
                    )
                )
            logger.info('--------------------------------------------------------')
        rp.parse_readings(fp)
        prev_ts = None
        assert (len(rp.data) == rp.expected_count)
        for item in rp.data:
            incremental_id = item['id']
            if incremental_id < original_first_id or incremental_id > original_last_id:
                pprint.pprint(item)
                logger.error('Found errors in file {}'.format(file_name))
                logger.error('  ==> data point out of range: {0}'.format(incremental_id))
            vid = int16gid(item['stream'])
            value =  item['value']
            ts = item['timestamp']
            if prev_ts != None:
                if prev_ts > ts:
                    logger.error('Found errors in file {}'.format(file_name))
                    logger.error('  ==> potential reboot event: {}'.format(incremental_id))
                    logger.error('  ==> Previous ts={0}. Current ts={1}'.format(prev_ts, ts))
            prev_ts = ts
            reading_dt = base_dt + datetime.timedelta(seconds=ts)
            if received_dt > received_dt:
                logger.error('Found errors in file {}'.format(file_name))
                logger.error('  ==> data point in the future: {0}'.format(incremental_id))
            if args.verbose and not args.error_only:
                logger.info('ID{0} - 0x{1}: {2} ({3}s) => {4}'.format(incremental_id, vid, get_utc_timestamp(base_dt, ts), ts, value))
        if args.verbose and not args.error_only:
            logger.info('--------------------------------------------------------')



if __name__ == '__main__':
    # Test
    # Logger Format
    import argparse
    logging.basicConfig(level=logging.DEBUG,
                        format='[%(asctime)-15s] %(levelname)-6s %(message)s',
                        datefmt='%d/%b/%Y %H:%M:%S')

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('-e', '--error-only', dest='error_only', action='store_true', help='Print out only errors')
    parser.add_argument('-v', '--verbose', dest='verbose', action='store_true', help='Print out all readings')
    parser.add_argument('-r', '--received_dt', dest='received_dt', type=str, help='Print out all readings')

    # Positional Args
    parser.add_argument('file', metavar='file', type=str, help='File Name')

    args = parser.parse_args()
    logger.info('--------------')

    if not args.received_dt:
        received_dt = datetime.datetime.utcnow()
    else:
        received_dt = dt_parser.parse(args.received_dt)


    if os.path.isfile(args.file):
        try:
            process_file(args.file, received_dt)
        except ParseReportException as e:
            logger.error(str(e))
    elif os.path.isdir(args.file):
        if not args.error_only:
            logger.info('Processing all bin files in {0}'.format(os.path.abspath(args.file)))
        for file in os.listdir(args.file):
            if file.endswith(".bin"):
                logger.debug('File: {}'.format(file))
                # Parse received_date from report
                name_parts = file[:-4].split('--')
                date_from_file = name_parts[3]
                logger.debug('Sent on {0}'.format(date_from_file))
                received_dt = dt_parser.parse(date_from_file)
                try:
                    process_file(os.path.join(args.file, file), received_dt)
                except ParseReportException as e:
                    logger.error(str(e))
    else:
        logger.error('File not found: {0}'.format(args.file))


