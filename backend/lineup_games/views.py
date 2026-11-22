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
    slot = serializers.IntegerField(min_value=0, required=False, help_text="Timeline: gap index (0 = before the first card)")
    guess = serializers.ChoiceField(choices=["higher", "lower"], required=False, help_text="Streak: next card vs open card")


class DailyAttemptSerializer(serializers.Serializer):
    number = serializers.IntegerField(min_value=1, help_text="Puzzle number the order belongs to")
    order = serializers.ListField(child=serializers.CharField(max_length=64), max_length=20,
                                  help_text="Every puzzle card id, lowest value first")


class HomeView(APIView):
    """GET: energy, the runs being played per mode (resume), best streak, timeline wins."""

    permission_classes = [IsLineupUser]

    def get(self, request):
        return Response(services.home_payload(request.user))


class ProfileView(APIView):
    """GET: stats per mode (Timeline wins/best, best streak, daily solved/streak/attempt distribution)."""

    permission_classes = [IsLineupUser]

    def get(self, request):
        return Response(services.profile_payload(request.user))


class RunListView(APIView):
    """
    GET ?mode=: the playing run of that mode (resume) + last finished runs.
    POST {mode, difficulty, attribute?}: new run for one energy point (409 no_energy).
    """

    permission_classes = [IsLineupUser]

    def get(self, request):
        runs = Run.objects.filter(user=request.user, is_challenge=False).select_related("attribute")
        mode = request.query_params.get("mode")
        if mode:
            runs = runs.filter(mode=mode)
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
        run = services.start_run(request.user, data.validated_data["mode"], data.validated_data["difficulty"],
                                 data.validated_data.get("attribute"))
        return Response(services.run_payload(run), status=status.HTTP_201_CREATED)


class RunDetailView(APIView):
    permission_classes = [IsLineupUser]

    def get(self, request, pk):
        run = Run.objects.select_related("attribute").filter(user=request.user, pk=pk).first()
        if run is None:
            raise NotFound("Tur bulunamadı.", code="run_not_found")
        return Response(services.run_payload(run))


class RunContinueView(APIView):
    """POST: Pro continues a lost run without an ad (409 pro_required / cannot_continue)."""

    permission_classes = [IsLineupUser]

    def post(self, request, pk):
        return Response(services.run_payload(services.continue_run(request.user, pk)))


class RunMoveView(APIView):
    """POST {slot} (Timeline: place the current card into a gap) or {guess} (Streak: higher / lower)."""

    permission_classes = [IsLineupUser]

    def post(self, request, pk):
        data = MoveSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        slot, guess = data.validated_data.get("slot"), data.validated_data.get("guess")
        run, result = services.play_move(request.user, pk, slot=slot, guess=guess)
        return Response(services.move_payload(run, result, slot=slot, guess=guess))


class DailyView(APIView):
    """
    GET [?number=]: today's puzzle (new one at LINEUP_DAILY_RESET, Istanbul), or a past one for Pro, with the user's
    attempts; values, solution and share text once finished.
    """

    permission_classes = [IsLineupUser]

    def get(self, request):
        number = request.query_params.get("number")
        puzzle = services.daily_by_number(request.user, int(number) if number and number.isdigit() else None)
        return Response(services.daily_payload(request.user, puzzle))


class DailyArchiveView(APIView):
    """GET: past puzzles with the user's status (Pro; 409 pro_required)."""

    permission_classes = [IsLineupUser]

    def get(self, request):
        return Response({"puzzles": services.daily_archive(request.user)})


class DailyAttemptView(APIView):
    """POST {number, order}: one attempt (free, max 3). 409 daily_expired / daily_over / invalid_order."""

    permission_classes = [IsLineupUser]

    def post(self, request):
        data = DailyAttemptSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        play, result = services.submit_daily(request.user, data.validated_data["number"], data.validated_data["order"])
        return Response({
            "result": {"marks": list(result.marks), "solved": result.solved, "attempt": len(play.attempts)},
            "daily": services.daily_payload(request.user, play.puzzle, play),
        })
