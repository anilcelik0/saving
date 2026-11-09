"""
Decode "(cid:N)" glyphs from PDFs whose embedded fonts lack a unicode map (common in Turkish bank PDFs).

The cid -> letter mapping differs per PDF/font subset, so it is inferred from the document itself:
tokens containing cids are matched against a dictionary of words that appear in almost every
Turkish statement ("İşlem", "Ödeme", "Açıklama", ...). Each match votes for cid -> letter.
Case is taken from the surrounding token (UPPERCASE token -> uppercase letter).
"""

import re
from collections import Counter, defaultdict

from .utils import tr_lower

CID = re.compile(r"\(cid:(\d+)\)")
TOKEN = re.compile(r"(?:[A-Za-zÇĞİÖŞÜçğıöşü]|\(cid:\d+\))+")

WORDS = """
işlem işlemler işlemleri açıklama ödeme ödemeler ödemesi ödenmesi önceki ücret ücretler ücretsiz ücreti
diğer şube şubesi şubeniz tarihi güncel değerleri değişikliği değişiklik sözleşme aşağıdan ulaşabilirsiniz
alışveriş alışverişiniz büyük büyükdere mükellefler müşteri şişli istanbul dönem dönemi
kayıp çalıntı günlerde kullanılabilir sipariş karşılığı yapacağınız şehit öğretmen çankaya gecikme
kartınızla kartınız kartınızın sayın türkiye kişisel hesabınız hesabınızdan ekstrenizin ekstreniz
nakit çekim çekimi faizi oranı aylık yıllık toplamı borcunuz borçlu ödenecek gerçekleşen gerçekleştirilen
mamülleri mamüller ürünleri gıda eczanesi eczane döner dönerci çiğköfte börek börekçi çörekçi
""".split()
WORDS_BY_LEN = defaultdict(list)
for _w in set(WORDS):
    WORDS_BY_LEN[len(_w)].append(_w)

TR_UPPER = {"i": "İ", "ı": "I"}


def _upper(ch: str) -> str:
    return TR_UPPER.get(ch, ch.upper())


def _parts(token: str) -> list:
    """'(cid:6)(cid:7)lem' -> [6, 7, 'l', 'e', 'm']"""
    out, i = [], 0
    while i < len(token):
        m = CID.match(token, i)
        if m:
            out.append(int(m.group(1)))
            i = m.end()
        else:
            out.append(token[i])
            i += 1
    return out


def learn_mapping(text: str) -> dict[int, str]:
    votes: dict[int, Counter] = defaultdict(Counter)
    for token in TOKEN.findall(text):
        if "(cid:" not in token:
            continue
        parts = _parts(token)
        for word in WORDS_BY_LEN.get(len(parts), ()):
            if all(isinstance(p, int) or tr_lower(p) == word[i] for i, p in enumerate(parts)):
                for i, p in enumerate(parts):
                    if isinstance(p, int):
                        votes[p][word[i]] += 1
    return {cid: counter.most_common(1)[0][0] for cid, counter in votes.items()}


def decode(text: str, mapping: dict[int, str]) -> str:
    def fix_token(m):
        token = m.group(0)
        if "(cid:" not in token:
            return token
        letters = [c for c in CID.sub("", token) if c.isalpha()]
        upper = bool(letters) and all(c.isupper() for c in letters) and len(letters) > 1
        return CID.sub(lambda c: (_upper if upper else str)(mapping.get(int(c.group(1)), "")), token)

    return TOKEN.sub(fix_token, text)


def decode_lines(lines: list[str]) -> list[str]:
    text = "\n".join(lines)
    if "(cid:" not in text:
        return lines
    mapping = learn_mapping(text)
    return [decode(line, mapping) for line in lines]
