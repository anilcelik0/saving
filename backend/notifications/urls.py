from django.urls import path

from .views import DeviceView

app_name = "notifications"

urlpatterns = [
    path("devices/", DeviceView.as_view(), name="devices"),
]
