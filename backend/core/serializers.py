from rest_framework import serializers


class OwnedPrimaryKeyRelatedField(serializers.PrimaryKeyRelatedField):
    """PK field limited to objects owned by the requesting user (prevents referencing others' data)."""

    def __init__(self, owner_field="user", **kwargs):
        self.owner_field = owner_field
        super().__init__(**kwargs)

    def get_queryset(self):
        request = self.context.get("request")
        queryset = super().get_queryset()
        if request is None or not request.user.is_authenticated:
            return queryset.none()
        return queryset.filter(**{self.owner_field: request.user})
