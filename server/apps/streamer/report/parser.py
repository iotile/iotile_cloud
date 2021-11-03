import logging
import struct
import hashlib
import hmac
import os

logger = logging.getLogger(__name__)

# Current Max Size of report (before the mobile is upgraded to send larger sizes)
# If the report is within 16 bytes of this max, then we can assume the report was
# chopped off
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
    def __init__(self, msg):
        logger.error("ParseReportException with message: {0}".format(msg))
        super(ParseReportException, self).__init__(msg)


class ReportParser(object):
    expected_count = None
    device_id = None
    report_id = None
    header = {}
    footer = {}
    length = 0
    data = []

    def __init__(self):
        self.length = 0
        self.header = {}
        self.footer = {}
        self.data = []

    def _unpack(self, format, raw):
        result = {}
        unpack_format = ''.join(['<',] + [item['type'] for item in format])

        try:
            obj = struct.unpack(unpack_format, raw)
        except Exception as e:
            raise ParseReportException(str(e))

        for i in range(len(format)):
            result[format[i]['label']] = obj[i]

        return result

    def _parse(self, fp, format, length):
        raw = fp.read(length)
        return self._unpack(format, raw)

    def parse_header(self, fp):
        fp.seek(0)
        self.header = self._parse(fp, HEADER_FORMAT, HEADER_LENGTH)
        if self.header['fmt'] != 1:
            raise ParseReportException('Unsupported Report Format: {}'.format(self.header['fmt']))

        logger.debug('Header: {0}'.format(str(self.header)))

        self.length = (self.header['len_high'] << 8) | self.header['len_low']
        logger.debug('length={}'.format(self.length))
        self.expected_count = int((self.length - HEADER_LENGTH - FOOTER_LENGTH) / READINGS_LENGTH)
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

    def chopped_off(self):
        return self.length > (DEFAULT_REPORT_MAX_LENGTH - READINGS_LENGTH) and self.length < DEFAULT_REPORT_MAX_LENGTH

