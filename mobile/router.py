import flet as ft


class Router:
    """Minimal view-stack navigation (Android back button pops the top view)."""

    def __init__(self, page: ft.Page):
        self.page = page
        page.on_view_pop = self._on_view_pop

    def reset(self, view: ft.View):
        self.page.views.clear()
        self.page.views.append(view)
        self.page.update()

    def push(self, view: ft.View):
        self.page.views.append(view)
        self.page.update()

    def pop(self):
        if len(self.page.views) > 1:
            self.page.views.pop()
            self.page.update()

    def _on_view_pop(self, e):
        self.pop()
