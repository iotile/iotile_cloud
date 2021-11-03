
"""
Represents the different Stremer Report Selectors used by the IOTile devices
The streamer_selector is included on every StreamerReport header
See apps.streamer.report.parser
"""
STREAMER_SELECTOR = {
    'USER_NO_REBOOTS': 0x057FF,
    'SYSTEM'         : 0x05FFF,
    'USER'           : 0x0D7FF,
    'TRIP_SYSTEM'    : 0x00FFF,
    'VIRTUAL1'       : 0x10000,
}
