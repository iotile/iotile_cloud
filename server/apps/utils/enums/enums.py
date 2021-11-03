# Status choices for StreamDataBase and StreamTimeSeries
STATUS_CHOICES = (
    ('unk', 'unknown'),
    ('cln', 'clean'),
    ('drt', 'dirty'),
    ('utc', 'utc timestamp'),
)

# Type choices for StreamData and StreamTimeSeriesValue
TYPE_CHOICES = (
    ('Num', 'Number'),  # Does not require a VarType
    ('ITR', 'Internal Type Representation'),  # Requires a VarType
    # The following are types are used for encoded streams
    # Represent the Packet start, end and element
    ('P-0', 'Packet Start Element'),
    ('P-1', 'Packet End Element'),
    ('P-E', 'Packet Data Element'),
)

# Extension choices for StreamEventData and StreamTimeSeriesEvent
EXT_CHOICES = (
    ('json', 'Json Data File'),
    ('json.gz', 'GZipped Json Data File'),
    ('csv', 'CSV Data File'),
)
