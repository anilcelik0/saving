from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from accounts.models import ClientApp, LegalDocument


class Command(BaseCommand):
    help = (
        "Publish the legal texts in legal_texts/<app>/<kind>.md (first line '# Title'). A file whose text differs "
        "from the latest version becomes a new published version, so users are asked to accept it again. "
        "Example: publish_legal_documents saving"
    )

    def add_arguments(self, parser):
        parser.add_argument("app")
        parser.add_argument("--dry-run", action="store_true", help="Only report what would change")

    def handle(self, app, dry_run=False, **options):
        client_app = ClientApp.objects.filter(slug=app).first()
        if client_app is None:
            raise CommandError(f"Unknown app '{app}' (create_client_app {app} <Name>).")
        folder = Path(settings.BASE_DIR) / "legal_texts" / app
        if not folder.is_dir():
            raise CommandError(f"Folder not found: {folder}")

        for kind in LegalDocument.Kind.values:
            path = folder / f"{kind}.md"
            if not path.exists():
                self.stdout.write(f"{kind}: no file, skipped")
                continue
            title, body = self._split(path.read_text(encoding="utf-8"), path)
            latest = LegalDocument.objects.filter(app=client_app, kind=kind).order_by("-version").first()
            if latest and latest.is_published and latest.title == title and latest.body == body:
                self.stdout.write(f"{kind}: unchanged (v{latest.version})")
                continue
            if dry_run:
                self.stdout.write(f"{kind}: would publish a new version")
                continue
            doc = LegalDocument.objects.create(app=client_app, kind=kind, title=title, body=body,
                                               published_at=timezone.now())
            self.stdout.write(self.style.SUCCESS(f"{kind}: published v{doc.version} '{title}'"))

    @staticmethod
    def _split(text, path):
        lines = text.strip().splitlines()
        if not lines or not lines[0].startswith("# "):
            raise CommandError(f"{path}: first line must be the title ('# ...').")
        return lines[0][2:].strip(), "\n".join(lines[1:]).strip() + "\n"
