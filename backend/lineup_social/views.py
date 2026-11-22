from django.shortcuts import render
from rest_framework import serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import ClientApp
from accounts.permissions import app_permission
from lineup_games.services import run_payload

from . import services
from .models import Challenge

IsLineupUser = app_permission("lineup")


class CreateSerializer(serializers.Serializer):
    run = serializers.UUIDField(help_text="The creator's finished run")


class SendSerializer(serializers.Serializer):
    username = serializers.CharField(max_length=30)


class ChallengeListView(APIView):
    """GET: incoming / sent / played. POST {run}: challenge from a finished run (same run → same challenge)."""

    permission_classes = [IsLineupUser]

    def get(self, request):
        return Response(services.challenge_lists(request.user))

    def post(self, request):
        data = CreateSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        challenge = services.create_challenge(request.user, data.validated_data["run"])
        return Response(services.challenge_payload(challenge, request.user), status=status.HTTP_201_CREATED)


class ChallengeDetailView(APIView):
    """GET: the challenge (score to beat, entries); never the cards."""

    permission_classes = [IsLineupUser]

    def get(self, request, code):
        return Response(services.challenge_payload(services.get_challenge(code), request.user))


class ChallengeAcceptView(APIView):
    """POST: free run on the challenge deck (409 own_challenge / challenge_expired); again = the same run."""

    permission_classes = [IsLineupUser]

    def post(self, request, code):
        entry = services.accept(request.user, code)
        return Response({"challenge": services.challenge_payload(entry.challenge, request.user),
                         "run": run_payload(entry.run)})


class ChallengeSendView(APIView):
    """POST {username}: invite a player (push + their incoming list)."""

    permission_classes = [IsLineupUser]

    def post(self, request, code):
        data = SendSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        services.send_challenge(request.user, code, data.validated_data["username"])
        return Response(status=status.HTTP_204_NO_CONTENT)


def challenge_page(request, code):
    """Public page of the invite link: opens the app through App Links when installed, else says how to join."""
    challenge = (Challenge.objects.select_related("creator", "source_run__attribute")
                 .filter(code=code.strip().upper()).first())
    app = ClientApp.objects.filter(slug="lineup").first()
    context = {"app": app, "challenge": challenge, "code": code.strip().upper(),
               "summary": services._summary(challenge) if challenge else ""}
    return render(request, "lineup_social/challenge_page.html", context, status=200 if challenge else 404)
