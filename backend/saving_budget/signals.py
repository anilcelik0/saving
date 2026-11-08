from django.conf import settings
from django.db.models.signals import post_save
from django.dispatch import receiver

from .services import create_default_categories

SAVING_APP_SLUG = "saving"


@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def seed_saving_user(sender, instance, created, **kwargs):
    if created and instance.app_id and instance.app.slug == SAVING_APP_SLUG:
        create_default_categories(instance)
