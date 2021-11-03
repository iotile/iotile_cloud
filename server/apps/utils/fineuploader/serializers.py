"""
{
   'expiration': '2018-03-19T05:10:42.585Z',
   'conditions': [
      {
          'acl': 'public-read'
      }, {
          'bucket': 'iotile-cloud-media'
      }, {
          'Content-Type': 'image/png'
      }, {
          'success_action_status': '200'
      }, {
          'key': 'dev/incoming/a470cd29-915f-4cfb-97de-ea378c46d51c/original.png'
      }, {
          'x-amz-meta-qqfilename': 'image001.png'
      },
      ['content-length-range', '0', '4096000']
   ]
}
"""

from rest_framework import serializers

class FineUploaderSignSerializer(serializers.Serializer):
    expiration = serializers.DateTimeField()
    conditions = serializers.JSONField()
