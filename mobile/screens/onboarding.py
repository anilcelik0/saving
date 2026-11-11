"""
First-run app tour: a few swipeable pages with a small illustration each (built from the design-system blocks),
shown once per user on this device and reachable again from Diğer > Uygulama turu.
"""

import flet as ft

from .theme import CARD, CHART, EXPENSE, INCOME, MUTED, donut, icon_badge, kind_badge, muted, text_badge


# ---------------------------------------------------------------- illustrations
def _pill(text, selected=False):
    return ft.Container(
        ft.Text(text, size=12, weight=ft.FontWeight.W_600, color=ft.Colors.ON_PRIMARY if selected else None),
        padding=ft.Padding.symmetric(horizontal=12, vertical=8), border_radius=999,
        bgcolor=ft.Colors.PRIMARY if selected else CARD,
        border=None if selected else ft.Border.all(1, ft.Colors.OUTLINE_VARIANT),
    )


def _row(badge, title, sub, amount=None, color=None):
    return ft.Row([
        badge,
        ft.Column([ft.Text(title, size=13, weight=ft.FontWeight.W_600), muted(sub, size=11)], spacing=0, expand=True),
        ft.Text(amount or "", size=13, weight=ft.FontWeight.W_700, color=color),
    ], spacing=10)


def _frame(*controls, spacing=12):
    return ft.Container(ft.Column(list(controls), spacing=spacing), bgcolor=CARD, border_radius=24, padding=18,
                        width=300, shadow=ft.BoxShadow(blur_radius=24, color="#140F172A", offset=ft.Offset(0, 8)))


def _welcome():
    return _frame(
        muted("Toplam bakiye", size=12),
        ft.Text("24.000 ₺", size=30, weight=ft.FontWeight.W_800),
        ft.Row([donut([(45, CHART[0]), (25, CHART[1]), (18, CHART[2]), (12, CHART[3])], size=88, thickness=12),
                ft.Column([_row(kind_badge("income", size=30), "Gelir", "Bu ay", "+68.000 ₺", INCOME),
                           _row(kind_badge("expense", size=30), "Gider", "Bu ay", "-41.250 ₺", EXPENSE)],
                          spacing=10, expand=True)], spacing=14),
    )


def _accounts():
    return _frame(
        _row(icon_badge(ft.Icons.ACCOUNT_BALANCE, "#0F766E", 34), "Ziraat Maaş", "Banka", "18.000 ₺"),
        _row(icon_badge(ft.Icons.CREDIT_CARD, "#6366F1", 34), "Enpara", "Banka · kart kesimi 15", "6.500 ₺"),
        _row(icon_badge(ft.Icons.PAYMENTS, "#D97706", 34), "Cüzdan", "Nakit", "1.500 ₺"),
    )


def _add_menu():
    def tile(icon, color, text):
        return ft.Column([icon_badge(icon, color, 44), ft.Text(text, size=11, weight=ft.FontWeight.W_600,
                                                                text_align=ft.TextAlign.CENTER)],
                         spacing=6, horizontal_alignment=ft.CrossAxisAlignment.CENTER, expand=True)
    return _frame(
        ft.Row([tile(ft.Icons.SWAP_VERT, "#0F766E", "Gelir/gider"), tile(ft.Icons.UPLOAD_FILE, "#1D4ED8", "Ekstre")]),
        ft.Row([tile(ft.Icons.DIAMOND, "#D97706", "Altın/döviz"), tile(ft.Icons.SAVINGS, "#7C3AED", "Mevduat")]),
        ft.Row([ft.Container(ft.Icon(ft.Icons.ADD, color=ft.Colors.ON_PRIMARY, size=30), width=56, height=56,
                             border_radius=28, bgcolor=ft.Colors.PRIMARY, alignment=ft.Alignment.CENTER)],
               alignment=ft.MainAxisAlignment.CENTER),
        spacing=16,
    )


def _entry():
    def cat(icon, color, text, selected=False):
        return ft.Container(
            ft.Column([icon_badge(icon, color, 28), ft.Text(text, size=10, weight=ft.FontWeight.W_600)],
                      spacing=4, horizontal_alignment=ft.CrossAxisAlignment.CENTER),
            padding=8, border_radius=14, expand=True,
            bgcolor=ft.Colors.PRIMARY_CONTAINER if selected else None,
            border=ft.Border.all(2 if selected else 1, ft.Colors.PRIMARY if selected else ft.Colors.OUTLINE_VARIANT),
        )
    return _frame(
        ft.Row([ft.Text("1.250 ₺", size=30, weight=ft.FontWeight.W_800)], alignment=ft.MainAxisAlignment.CENTER),
        ft.Container(ft.Text("Migros", size=14, weight=ft.FontWeight.W_600), border_radius=12, padding=10,
                     border=ft.Border.all(1, ft.Colors.OUTLINE_VARIANT)),
        ft.Row([cat(ft.Icons.SHOPPING_CART, CHART[0], "Market", True), cat(ft.Icons.RESTAURANT, CHART[1], "Yeme"),
                cat(ft.Icons.BOLT, CHART[4], "Fatura")], spacing=6),
        ft.Row([_pill("Bugün", True), _pill("Dün"), _pill("Taksitli")], spacing=6, wrap=True),
    )


def _statement():
    return _frame(
        _row(icon_badge(ft.Icons.PICTURE_AS_PDF, "#DC2626", 34), "ekstre_kasim.pdf", "18 hareket bulundu"),
        ft.Divider(),
        _row(kind_badge("expense", size=30), "MIGROS", "Market · eklenecek", "-845 ₺", EXPENSE),
        _row(kind_badge("expense", size=30), "NETFLIX", "Abonelik · eşleşti", "-229 ₺", EXPENSE),
        ft.Container(ft.Row([ft.Icon(ft.Icons.LOCK, size=16, color=INCOME),
                             muted("Kart bilgisi okunmaz, dosya işlenince silinir", size=11, expand=True)],
                            spacing=6),
                     bgcolor=ft.Colors.TERTIARY_CONTAINER, border_radius=10, padding=8),
    )


def _activity():
    return _frame(
        ft.Row([ft.Icon(ft.Icons.CHEVRON_LEFT, color=MUTED), ft.Text("Kasım 2026", weight=ft.FontWeight.W_700),
                ft.Icon(ft.Icons.CHEVRON_RIGHT, color=MUTED)], alignment=ft.MainAxisAlignment.CENTER),
        _row(kind_badge("expense", size=30), "Kira", "Gecikti · 1 Kas", "-24.000 ₺", EXPENSE),
        _row(kind_badge("expense", card_spend=True, size=30), "Enpara kartı", "Ekstre · 15 Kas", "-6.120 ₺", EXPENSE),
        _row(kind_badge("income", size=30), "Maaş", "Ödendi · 5 Kas", "+68.000 ₺", INCOME),
    )


def _invest():
    return _frame(
        _row(text_badge("Au", "#D97706", 34), "Gram altın", "12 gram · bugün", "+4,2%", INCOME),
        _row(text_badge("$", "#0EA5E9", 34), "Dolar", "1.500 USD", "-0,3%", EXPENSE),
        _row(icon_badge(ft.Icons.ACCOUNT_BALANCE, "#6D28D9", 34), "Enpara 32 gün", "%42 · 18 gün kaldı",
             "104.158 ₺"),
    )


def _settings():
    def line(icon, text, trailing):
        return ft.Row([ft.Icon(icon, color=MUTED, size=20), ft.Text(text, size=13, expand=True), trailing],
                      spacing=10)
    return _frame(
        line(ft.Icons.DARK_MODE, "Tema", muted("Telefona uy", size=12)),
        line(ft.Icons.ACCOUNT_BALANCE_WALLET, "Varsayılan hesap", muted("Enpara", size=12)),
        line(ft.Icons.VISIBILITY_OFF, "Tutarları gizle", ft.Switch(value=True, scale=0.8)),
    )


PAGES = [
    (_welcome, "Saving'e hoş geldin",
     "Bakiyeni, harcamalarını, ödemelerini ve yatırımlarını tek yerden takip et. Kısa bir turla nasıl "
     "kullanacağını gösterelim."),
    (_accounts, "Önce hesaplarını ekle",
     "Banka ve nakit hesaplarını bugünkü bakiyeleriyle ekle. Kredi kartın varsa ekstre kesim gününü gir; "
     "kart harcamaları aylık özette ekstre dönemine göre sayılır."),
    (_add_menu, "Her şey ortadaki + butonunda",
     "Gelir/gider, ekstre yükleme, altın/döviz alışı, vadeli mevduat ve yeni hesap: hepsi alt çubuktaki "
     "+ butonundan eklenir."),
    (_entry, "Saniyeler içinde kayıt",
     "Tutarı yaz, isim ver, kategoriye dokun. Son kullandığın kategoriler önde gelir. Kira, abonelik veya "
     "taksitli alışveriş için \"Tekrar, taksit, not\" bölümünü aç."),
    (_statement, "Ekstreni yükle, gerisini bırak",
     "Banka veya kart ekstreni PDF/Excel olarak yükle. Hareketler önizlemede kategorileriyle gelir, mevcut "
     "kayıtlarla eşleşir; onayladığında eklenir. Kart bilgisi okunmaz, dosya işlendikten sonra silinir."),
    (_activity, "Özet ve hareketler",
     "Özet ekranında ayın bakiyesini, harcama dağılımını ve yaklaşan ödemeleri gör. Hareketler'de ay ay "
     "gezin; bekleyen ödemeleri tek dokunuşla \"Ödendi\" işaretle."),
    (_invest, "Yatırımların da burada",
     "Altın, gümüş ve döviz fiyatları her gün güncellenir. Vadeli mevduatlarda vade sonu tutarı stopaj "
     "düşülerek hesaplanır; vade dolunca yenile ya da kapat."),
    (_settings, "Sana göre ayarla",
     "Diğer > Uygulama ayarları'ndan tema, varsayılan hesap ve açılış ekranını seç; istersen tutarları gizle. "
     "Bu turu Diğer > Uygulama turu'ndan tekrar açabilirsin."),
]


# ---------------------------------------------------------------- view
def onboarding_view(state, on_finish) -> ft.View:
    """on_finish(add_account: bool) is awaited when the tour ends (skip or last page)."""
    page = state.page
    current = {"i": 0}
    switcher = ft.AnimatedSwitcher(ft.Container(), transition=ft.AnimatedSwitcherTransition.FADE, duration=220,
                                   expand=True)
    dots = ft.Row(alignment=ft.MainAxisAlignment.CENTER, spacing=6)
    back = ft.TextButton("Geri", on_click=lambda e: go(-1))
    next_button = ft.FilledButton("İleri", height=52, expand=True,
                                  style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=18)))
    secondary = ft.TextButton("Şimdilik geç", visible=False)
    needs_account = not state.accounts

    async def finish(add_account=False):
        await on_finish(add_account)

    async def next_clicked(e):
        if current["i"] < len(PAGES) - 1:
            go(1)
        else:
            await finish(add_account=needs_account)

    next_button.on_click = next_clicked
    secondary.on_click = lambda e: page.run_task(finish)

    def render():
        i = current["i"]
        illustration, title, text = PAGES[i]
        switcher.content = ft.Column([
            ft.Container(illustration(), alignment=ft.Alignment.CENTER, expand=True),
            ft.Text(title, size=24, weight=ft.FontWeight.W_800, text_align=ft.TextAlign.CENTER),
            ft.Text(text, size=15, color=MUTED, text_align=ft.TextAlign.CENTER),
        ], key=str(i), spacing=12, horizontal_alignment=ft.CrossAxisAlignment.CENTER, expand=True)
        dots.controls = [ft.Container(width=22 if n == i else 8, height=8, border_radius=4,
                                      bgcolor=ft.Colors.PRIMARY if n == i else ft.Colors.OUTLINE_VARIANT,
                                      animate=ft.Animation(200))
                         for n in range(len(PAGES))]
        last = i == len(PAGES) - 1
        back.visible = i > 0
        next_button.content = ("İlk hesabımı ekle" if needs_account else "Başla") if last else "İleri"
        secondary.visible = last and needs_account
        skip.visible = not last

    def go(delta):
        current["i"] = max(0, min(len(PAGES) - 1, current["i"] + delta))
        render()
        page.update()

    def swiped(e: ft.DragEndEvent):
        velocity = e.primary_velocity or 0
        if abs(velocity) > 200:
            go(1 if velocity < 0 else -1)

    skip = ft.TextButton("Atla", on_click=lambda e: page.run_task(finish))
    render()
    body = ft.GestureDetector(
        content=ft.Container(switcher, padding=ft.Padding.symmetric(horizontal=24), expand=True),
        on_horizontal_drag_end=swiped, expand=True,
    )
    return ft.View(
        route="/onboarding",
        padding=0,
        bgcolor=ft.Colors.SURFACE,
        controls=[ft.SafeArea(ft.Column([
            ft.Container(ft.Row([back, ft.Container(expand=True), skip]), padding=ft.Padding.only(left=8, right=8,
                                                                                                   top=8)),
            body,
            ft.Container(ft.Column([dots, ft.Row([next_button]), secondary], spacing=12,
                                   horizontal_alignment=ft.CrossAxisAlignment.CENTER),
                         padding=ft.Padding.only(left=24, right=24, top=16, bottom=20)),
        ], spacing=0, expand=True), expand=True)],
    )
