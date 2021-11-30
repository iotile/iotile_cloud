import datetime
import decimal

import msgpack
from dateutil.parser import parse
from six import text_type

from rest_framework.exceptions import ParseError
from rest_framework.parsers import BaseParser
from rest_framework.renderers import BaseRenderer


class MessagePackDecoder:
    def decode(self, obj):
        if '__class__' in obj:
            decode_func = getattr(self, 'decode_%s' % obj['__class__'])
            return decode_func(obj)
        return obj

    def decode_datetime(self, obj):
        return parse(obj['as_str'])

    def decode_date(self, obj):
        return parse(obj['as_str']).date()

    def decode_time(self, obj):
        return parse(obj['as_str']).time()

    def decode_decimal(self, obj):
        return decimal.Decimal(obj['as_str'])


class MessagePackEncoder:
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


class MessagePackRenderer(BaseRenderer):
    """
    Renderer which serializes to MessagePack.
    """
    media_type = 'application/msgpack'
    format = 'msgpack'
    render_style = 'binary'
    charset = None

    def render(self, data, media_type=None, renderer_context=None):
        """
        Renders *obj* into serialized MessagePack.
        """
        if data is None:
            return ''
        return msgpack.packb(data, default=MessagePackEncoder().encode)


class MessagePackParser(BaseParser):
    """
    Parses MessagePack-serialized data.
    """
    media_type = 'application/msgpack'
    decoder = MessagePackDecoder

    def parse(self, stream, media_type=None, parser_context=None):
        try:
            return msgpack.load(stream,
                                use_list=True,
                                raw=False,
                                object_hook=self.decoder().decode)
        except Exception as exc:
            raise ParseError('MessagePack parse error - %s' % text_type(exc))


class Python2CompatMessagePackParser(BaseParser):
    """
    Parses MessagePack-serialized data.
    """

    media_type = 'application/msgpack'

    def _str_of_bytes(self, obj):
        """
        Convert all bytes in a nested object to strings
        """
        if type(obj) is str:
            return obj
        if type(obj) is bytes:
            return obj.decode('utf-8')
        # use isinstance because obj may be OrderedDict
        # assume the class can be instantiated by using a dict
        if isinstance(obj, dict):
            return type(obj)({self._str_of_bytes(k): self._str_of_bytes(v) for k, v in obj.items()})
        # if obj is another iterable, just map the function on every element
        try:
            return type(obj)((self._str_of_bytes(e) for e in obj))
        # if obj is not iterable (int, float, bool, etc.), just return it
        except TypeError:
            return obj

    def parse(self, stream, media_type=None, parser_context=None):
        try:
            report_dict = msgpack.unpack(stream,
                                         use_list=True,
                                         raw=False,
                                         object_hook=MessagePackDecoder().decode)
            # if the file was packed with Python 2, then the keys/values of report_dict are bytes instead of strings
            # we want to return a dict whose keys/values are not bytes
            return self._str_of_bytes(report_dict)
        except Exception as exc:
            raise ParseError('MessagePack parse error - %s' % text_type(exc))
