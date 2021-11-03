
"""
System Streams used by the different IOTile Devices
"""
SYSTEM_VID = {
    'BATTERY'            : '5800', # Enabled by SG
    'ON_SCAN_BEGIN'      : '5a00', # Gateway
    'ON_SCAN_END'        : '5a01', # Gateway
    'SCAN_DEVICE_FAIL'   : '5a03', # Gateway
    'REBOOT'             : '5c00', # Device
    'ON_CONNECT'         : '5c01', # BLE Device
    'ON_DISCONNECT'      : '5c02', # BLE Device
    'OS_TAG_VERSION'     : '5c08', # Device OS TAG and Version
    'APP_TAG_VERSION'    : '5c09', # Device App TAG (SG) and Version

    # POD-1M (Shipping)
    'TRIP_START'         : '0e00', # Shipping
    'TRIP_END'           : '0e01', # Shipping
    'TRIP_RECORD'        : '0e02', # Shipping (Pause/Resume)

    # Additional System stream generated and used by the cloud only
    'COMPLETE_REPORT'     : '5a05',  # Generated at the end of each complete streamer report processed
    'CHOPPED_REPORT'      : '5a06',  # Generated after processing a chopped report
    'TRIP_SUMMARY'        : '5a07',  # Shipping Trip Summary
    'TRIP_UPDATE'         : '5a08',  # Mid-trip trip summary update
    'DEVICE_DATA_MASK'    : '5a09',  # Contains information to help mask data the user wants us to filter out
    'MACHINE_OEE_SUMMARY' : '5a0a',  # OEE computation results (Factory)
    'MID_TRIP_DATA_UPLOAD': '5a0c',  # Data (not summary) uploaded mid-trip 

    # Factory OEE Caching streams
    'DAILY_METRICS'       : '5060',  # Metrics computation results (Factory)
}

USER_VID = {

    # POD-1M (Shipping)
    'ACCEL'        : '5020', # Accelerometer Event Stream
    'PRESSURE'     : '5021', # Pressure Data
    'REL_HUMIDITY' : '5022', # Relative Humidity Data
    'TEMP'         : '5023', # Temperature Data
}


"""
Constants represent begin/end values for an encoded stream
"""
ENCODED_STREAM_VALUES = {
    'BEGIN': 0xFFFFFFFF,
    'END'  : 0xFFFFFFFE
}


"""
List of streams to ignore when doing data trimming
"""
DATA_TRIM_EXCLUSION_LIST = [
    int(SYSTEM_VID['REBOOT'], 16),
    int(SYSTEM_VID['OS_TAG_VERSION'], 16),
    int(SYSTEM_VID['APP_TAG_VERSION'], 16),
    int(SYSTEM_VID['TRIP_START'], 16),
    int(SYSTEM_VID['TRIP_END'], 16),
    int(SYSTEM_VID['TRIP_RECORD'], 16),
]
