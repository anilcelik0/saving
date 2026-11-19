import flet as ft


def safe_area(view: ft.View) -> ft.View:
    """Keep every view's content clear of the status bar / notch / camera cutout and the gesture bar.

    Android 15+ draws apps edge to edge, so views without an AppBar (forms, login) slid under the cutout and
    their top buttons could not be tapped. The view's own column settings move into the wrapper.
    Views that already start with a SafeArea are left as they are.
    """
    if len(view.controls) == 1 and isinstance(view.controls[0], ft.SafeArea):
        return view
    column = ft.Column(
        list(view.controls), expand=True, spacing=view.spacing,
        alignment=view.vertical_alignment, horizontal_alignment=view.horizontal_alignment,
        scroll=getattr(view, "scroll", None),
    )
    view.scroll = None
    view.controls = [ft.SafeArea(column, expand=True)]
    return view


class Router:
    """Minimal view-stack navigation (Android back button pops the top view)."""

    def __init__(self, page: ft.Page):
        self.page = page
        page.on_view_pop = self._on_view_pop

    def reset(self, view: ft.View):
        self.page.views.clear()
        self.page.views.append(safe_area(view))
        self.page.update()

    def push(self, view: ft.View):
        self.page.views.append(safe_area(view))
        self.page.update()

    def pop(self):
        if len(self.page.views) > 1:
            self.page.views.pop()
            self.page.update()

    def _on_view_pop(self, e):
        self.pop()
