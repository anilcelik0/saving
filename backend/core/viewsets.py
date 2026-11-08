from rest_framework import viewsets


class OwnedModelViewSet(viewsets.ModelViewSet):
    """ModelViewSet scoped to request.user; set `owner_field` for indirect ownership (e.g. 'goal__user')."""

    owner_field = "user"

    def get_queryset(self):
        return super().get_queryset().filter(**{self.owner_field: self.request.user})

    def perform_create(self, serializer):
        if self.owner_field == "user":
            serializer.save(user=self.request.user)
        else:
            serializer.save()
