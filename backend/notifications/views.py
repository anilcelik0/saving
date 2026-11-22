from rest_framework import serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView

from . import services


class DeviceSerializer(serializers.Serializer):
    token = serializers.CharField(max_length=512)
    platform = serializers.ChoiceField(choices=["android", "ios"], default="android")


class DeviceView(APIView):
    """POST {token, platform}: this device gets pushes for the signed-in user. DELETE {token}: stop (logout)."""

    def post(self, request):
        data = DeviceSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        services.register_device(request.user, data.validated_data["token"], data.validated_data["platform"])
        return Response(status=status.HTTP_204_NO_CONTENT)

    def delete(self, request):
        data = DeviceSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        services.unregister_device(request.user, data.validated_data["token"])
        return Response(status=status.HTTP_204_NO_CONTENT)
