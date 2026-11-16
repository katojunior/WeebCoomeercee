from django.urls import path

from .views import (
    CestAPIView,
    CestsAPIView,
    CfopAPIView,
    CfopsAPIView,
    NcmAPIView,
    NcmsAPIView,
)


urlpatterns = [
    path('ncms/', NcmsAPIView.as_view(), name='ncms'),
    path('ncms/<int:pk>/', NcmAPIView.as_view(), name='ncm'),

    path('cests/', CestsAPIView.as_view(), name='cests'),
    path('cests/<int:pk>/', CestAPIView.as_view(), name='cest'),

    path('cfops/', CfopsAPIView.as_view(), name='cfops'),
    path('cfops/<int:pk>/', CfopAPIView.as_view(), name='cfop'),
]

