from django.contrib.admin.views.decorators import staff_member_required
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from .models import IssueAttachment, IssueReport
from .serializers import IssueCreateSerializer, IssueReportSerializer


class IssueReportView(APIView):
    """
    GET: the user's own reports (status, developer response).
    POST (multipart or JSON): category, message, context{}, related_type/related_id, attachments_consent,
    files `attachments` (0..n) and `statement_file` (statement re-sent from the device).
    """

    throttle_scope = "support"

    def get_throttles(self):
        return [ScopedRateThrottle()] if self.request.method == "POST" else []

    def get(self, request):
        reports = IssueReport.objects.filter(user=request.user).prefetch_related("attachments")[:50]
        return Response(IssueReportSerializer(reports, many=True).data)

    def post(self, request):
        files = [(f, IssueAttachment.Source.UPLOAD) for f in request.FILES.getlist("attachments")]
        if "statement_file" in request.FILES:
            files.append((request.FILES["statement_file"], IssueAttachment.Source.STATEMENT))
        serializer = IssueCreateSerializer(data=request.data, context={"request": request, "files": files})
        serializer.is_valid(raise_exception=True)
        report = serializer.save()
        return Response(IssueReportSerializer(report).data, status=status.HTTP_201_CREATED)


@staff_member_required
def attachment_download(request, pk):
    """Admin-only download of a report attachment (private storage, never served by nginx)."""
    attachment = get_object_or_404(IssueAttachment, pk=pk)
    if not attachment.file:
        raise Http404("Dosya saklama süresi dolduğu için silindi.")
    return FileResponse(attachment.file.open("rb"), as_attachment=True, filename=attachment.original_name)
