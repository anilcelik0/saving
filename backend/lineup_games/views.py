from rest_framework import serializers, status
from rest_framework.exceptions import NotFound
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.permissions import app_permission

from . import services
from .models import Run

IsLineupUser = app_permission("lineup")


class StartRunSerializer(serializers.Serializer):
    mode = serializers.ChoiceField(choices=Run.Mode.choices, default=Run.Mode.TIMELINE)
    difficulty = serializers.ChoiceField(choices=list(services.DIFFICULTIES.items()), default="normal")
    attribute = serializers.SlugField(required=False, help_text="Attribute key; empty = random playable one")


class MoveSerializer(serializers.Serializer):
    slot = serializers.IntegerField(min_value=0, help_text="Gap index (0 = before the first card)")


class RunListView(APIView):
    """GET: the playing run (resume) + last finished runs. POST {mode, difficulty, attribute?}: new run."""

    permission_classes = [IsLineupUser]

    def get(self, request):
        runs = Run.objects.filter(user=request.user).select_related("attribute")
        playing = runs.filter(status=Run.Status.PLAYING).first()
        recent = runs.exclude(status=Run.Status.PLAYING)[:10]
        return Response({
            "playing": services.run_payload(playing) if playing else None,
            "recent": [{"id": str(r.pk), "mode": r.mode, "status": r.status, "score": r.score,
                        "attribute": r.attribute.name, "finished_at": r.finished_at} for r in recent],
        })

    def post(self, request):
        data = StartRunSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        run = services.start_timeline(request.user, data.validated_data["difficulty"],
                                      data.validated_data.get("attribute"))
        return Response(services.run_payload(run), status=status.HTTP_201_CREATED)


class RunDetailView(APIView):
    permission_classes = [IsLineupUser]

    def get(self, request, pk):
        run = Run.objects.select_related("attribute").filter(user=request.user, pk=pk).first()
        if run is None:
            raise NotFound("Tur bulunamadı.", code="run_not_found")
        return Response(services.run_payload(run))


class RunMoveView(APIView):
    """POST {slot}: place the current card into a gap."""

    permission_classes = [IsLineupUser]

    def post(self, request, pk):
        data = MoveSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        slot = data.validated_data["slot"]
        run, result = services.play_move(request.user, pk, slot)
        return Response(services.move_payload(run, result, slot))
