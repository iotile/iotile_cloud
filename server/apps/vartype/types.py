
STREAM_DATA_TYPE_CHOICES = (
    ('00', '00 - Not Set'),
    # StreamData
    # ----------
    ('D0', 'D0 - Single Value'),
    # StreamEventData
    # ---------------
    ('E0', 'E0 - Unstructured Events'),
    # Encoded StreamData becomes StreamEvent
    ('E1', 'E1 - Unstructured Events wth encoded data'),
    # StreamData's value points to StreamEvent record
    ('E2', 'E2 - Unstructured Events with Data Pointer'),
    # StreamEventData with absolute UTC timestamp (no device_timestamp)
    ('E3', 'E3 - Unstructured Events with UTC timestamp'),
)
