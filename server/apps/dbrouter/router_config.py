
DB1 = 'default'
DB2 = 'streamdata'
DB3 = 'streamtimeseries'

# List of apps that should use Redshift
# Currently, we don't seem to be able to add another table
# so until we figure out, we can only keep one
REDSHIFT_APPs = ['streamdata', ]

STREAM_TIME_SERIES_APPs = ['streamtimeseries', ]
