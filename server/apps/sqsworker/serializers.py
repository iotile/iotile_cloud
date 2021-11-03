from rest_framework import serializers

from .pid import ActionPID

class ActionPidSerializer(serializers.Serializer):
    pid = serializers.CharField(max_length=26)
    info = serializers.SerializerMethodField()

    def get_info(self, obj):
        pid = ActionPID(self.validated_data['pid'])
        info = pid.info()
        if info:
            return {
                'type': info['type'],
                'created_on': info['dt']
            }
        else:
            return {
                'error': 'Not found'
            }
