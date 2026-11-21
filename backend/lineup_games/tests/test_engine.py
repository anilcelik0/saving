"""Unit tests of the pure-Python engine (no database). Run: python manage.py test lineup_games"""

from datetime import datetime, timedelta
from decimal import Decimal
from unittest import TestCase

from lineup_games.engine import decks, timeline
from lineup_games.engine.decks import DeckCard, DeckParams
from lineup_games.engine.values import Value, compare, gap


def year(y, m=None, d=None):
    return Value(year=y, month=m, day=d)


def num(n):
    return Value(number=Decimal(n))


class CompareTests(TestCase):
    def test_dates_order(self):
        self.assertEqual(compare(year(1453), year(1923)), -1)
        self.assertEqual(compare(year(1923), year(1453)), 1)

    def test_bc_before_ad(self):
        self.assertEqual(compare(year(-1200), year(1)), -1)
        self.assertEqual(compare(year(-1200), year(-500)), -1)

    def test_coarser_precision_tie(self):
        self.assertEqual(compare(year(2001), year(2001, 5, 3)), 0)
        self.assertEqual(compare(year(2001, 5), year(2001, 5, 30)), 0)

    def test_same_precision_decides(self):
        self.assertEqual(compare(year(2001, 5), year(2001, 6, 2)), -1)
        self.assertEqual(compare(year(1453, 5, 29), year(1453, 5, 30)), -1)
        self.assertEqual(compare(year(1999, 8, 17), year(1999, 8, 17)), 0)

    def test_numbers(self):
        self.assertEqual(compare(num("4479525"), num("15840900")), -1)
        self.assertEqual(compare(num("10.5"), num("10.50")), 0)

    def test_date_vs_number_rejected(self):
        with self.assertRaises(ValueError):
            compare(year(2000), num("2000"))

    def test_gap(self):
        self.assertEqual(gap(year(1950), year(1999, 3)), 49)
        self.assertAlmostEqual(gap(num("80"), num("100")), 0.2)
        self.assertEqual(gap(num("0"), num("0")), 0.0)


def pool(count=30, start=1900, step=5, **kw):
    return [DeckCard(id=f"c{i:02d}", value=year(start + i * step), **kw) for i in range(count)]


class DeckTests(TestCase):
    def test_same_seed_same_deck(self):
        params = DeckParams(size=13)
        self.assertEqual(decks.generate("abc", pool(), params), decks.generate("abc", pool(), params))

    def test_candidate_order_does_not_matter(self):
        params = DeckParams(size=13)
        self.assertEqual(decks.generate("abc", pool(), params), decks.generate("abc", list(reversed(pool())), params))

    def test_different_seed_different_deck(self):
        params = DeckParams(size=13)
        self.assertNotEqual(decks.generate("abc", pool(), params), decks.generate("xyz", pool(), params))

    def test_size_and_unique(self):
        deck = decks.generate("s", pool(), DeckParams(size=13))
        self.assertEqual(len(deck), 13)
        self.assertEqual(len(set(deck)), 13)

    def test_small_pool_gives_short_deck(self):
        self.assertEqual(len(decks.generate("s", pool(count=5), DeckParams(size=13))), 5)

    def test_min_gap_respected_when_possible(self):
        cards = pool(count=200, step=1)  # 1900..2099: plenty of room for 10 cards 5 years apart
        deck = decks.generate("s", cards, DeckParams(size=10, min_gap=5))
        years = sorted(int(c[1:]) + 1900 for c in deck)
        self.assertTrue(all(b - a >= 5 for a, b in zip(years, years[1:])), years)

    def test_gap_relaxed_when_pool_too_small(self):
        cards = pool(count=13, step=1)  # 13 consecutive years: a 15-year gap cannot hold 13 cards
        self.assertEqual(len(decks.generate("s", cards, DeckParams(size=13, min_gap=15))), 13)

    def test_popularity_filter(self):
        cards = [DeckCard(id=f"c{i}", value=year(1900 + i), popularity=10 if i % 2 else 90) for i in range(20)]
        deck = decks.generate("s", cards, DeckParams(size=20, min_popularity=60))
        self.assertEqual(len(deck), 10)
        self.assertTrue(all(int(c[1:]) % 2 == 0 for c in deck))

    def test_type_and_tag_filters(self):
        cards = [DeckCard(id=f"f{i}", value=year(1950 + i), type_key="film") for i in range(5)] + \
                [DeckCard(id=f"e{i}", value=year(1500 + i), type_key="event", tags=frozenset({"osmanli"}))
                 for i in range(5)]
        films = decks.generate("s", cards, DeckParams(size=10, type_keys=frozenset({"film"})))
        self.assertEqual(sorted(films), [f"f{i}" for i in range(5)])
        tagged = decks.generate("s", cards, DeckParams(size=10, tags=frozenset({"osmanli"})))
        self.assertEqual(sorted(tagged), [f"e{i}" for i in range(5)])

    def test_difficulty_presets(self):
        self.assertEqual(decks.params_for("easy", 13, is_date=True).min_gap, 15)
        self.assertEqual(decks.params_for("easy", 13, is_date=False).min_gap, 0.3)
        self.assertEqual(decks.params_for("hard", 13, is_date=True).min_popularity, 0)


class ValidSlotsTests(TestCase):
    line = [year(1900), year(1950), year(2000)]

    def test_single_slot(self):
        self.assertEqual(timeline.valid_slots(self.line, year(1920)), (1,))
        self.assertEqual(timeline.valid_slots(self.line, year(1800)), (0,))
        self.assertEqual(timeline.valid_slots(self.line, year(2020)), (3,))

    def test_tie_gives_both_sides(self):
        self.assertEqual(timeline.valid_slots(self.line, year(1950)), (1, 2))
        self.assertEqual(timeline.valid_slots(self.line, year(1950, 6, 1)), (1, 2))  # year-only neighbour

    def test_precision_tie_with_neighbours(self):
        line = [year(2001, 1, 5), year(2001, 12, 30)]
        self.assertEqual(timeline.valid_slots(line, year(2001)), (0, 1, 2))


def make_values(deck_years):
    return {f"c{i}": year(y) for i, y in enumerate(deck_years)}


class TimelineTests(TestCase):
    def setUp(self):
        # c0 starts the line (1950); then 1900, 2000, 1925, 1975 ...
        self.years = [1950, 1900, 2000, 1925, 1975, 1960, 1910, 1990, 1930, 1940, 1980, 1995, 1905]
        self.values = make_values(self.years)
        self.state = timeline.start([f"c{i}" for i in range(len(self.years))])

    def correct_slot(self, state):
        return timeline.valid_slots([self.values[c] for c in state.line], self.values[state.current])[0]

    def test_start(self):
        self.assertEqual(self.state.line, ("c0",))
        self.assertEqual(self.state.current, "c1")
        self.assertEqual((self.state.lives, self.state.score, self.state.status), (3, 0, timeline.PLAYING))

    def test_correct_move_inserts_in_order(self):
        result = timeline.place(self.state, 0, self.values)  # 1900 before 1950
        self.assertTrue(result.correct)
        self.assertEqual(result.state.line, ("c1", "c0"))
        self.assertEqual(result.state.score, 1)
        self.assertEqual(result.state.current, "c2")

    def test_wrong_move_costs_a_life_and_discards(self):
        result = timeline.place(self.state, 1, self.values)  # 1900 after 1950: wrong
        self.assertFalse(result.correct)
        self.assertEqual(result.valid_slots, (0,))
        self.assertEqual(result.state.line, ("c0",))
        self.assertEqual(result.state.lives, 2)
        self.assertEqual(result.state.current, "c2")

    def test_timeout_is_wrong(self):
        result = timeline.place(self.state, None, self.values)
        self.assertTrue(result.timed_out)
        self.assertFalse(result.correct)
        self.assertEqual(result.state.lives, 2)
        late = timeline.place(self.state, 0, self.values, timed_out=True)  # right slot but too late
        self.assertFalse(late.correct)

    def test_slot_out_of_range(self):
        with self.assertRaises(ValueError):
            timeline.place(self.state, 5, self.values)

    def test_three_mistakes_lose(self):
        state = self.state
        for _ in range(3):
            state = timeline.place(state, None, self.values).state
        self.assertEqual((state.status, state.lives), (timeline.LOST, 0))
        self.assertIsNone(state.current)
        with self.assertRaises(ValueError):
            timeline.place(state, 0, self.values)

    def test_win_at_target(self):
        state = self.state
        while state.status == timeline.PLAYING:
            state = timeline.place(state, self.correct_slot(state), self.values).state
        self.assertEqual(state.status, timeline.WON)
        self.assertEqual(len(state.line), timeline.TARGET)
        line_years = [self.values[c].year for c in state.line]
        self.assertEqual(line_years, sorted(line_years))

    def test_win_with_mistakes_on_the_way(self):
        state = timeline.place(self.state, None, self.values).state
        state = timeline.place(state, None, self.values).state
        while state.status == timeline.PLAYING:
            state = timeline.place(state, self.correct_slot(state), self.values).state
        self.assertEqual((state.status, state.lives), (timeline.WON, 1))

    def test_deck_runs_out(self):
        values = make_values([1950, 1900, 2000])
        state = timeline.start(["c0", "c1", "c2"])
        state = timeline.place(state, 0, values).state
        state = timeline.place(state, 2, values).state
        self.assertEqual((state.status, state.score), (timeline.FINISHED, 2))

    def test_tie_accepted_on_either_side(self):
        values = {"a": year(1999), "b": year(1999, 8, 17), "c": year(1999)}
        left = timeline.place(timeline.start(["a", "b", "c"]), 0, values)
        right = timeline.place(timeline.start(["a", "b", "c"]), 1, values)
        self.assertTrue(left.correct and right.correct)

    def test_needs_two_cards(self):
        with self.assertRaises(ValueError):
            timeline.start(["only"])

    def test_deck_size(self):
        self.assertEqual(timeline.deck_size(), timeline.TARGET + timeline.LIVES)


class TimerTests(TestCase):
    def test_within_limit_and_grace(self):
        dealt = datetime(2026, 1, 1, 12, 0, 0)
        self.assertFalse(timeline.is_timed_out(dealt, dealt + timedelta(seconds=10)))
        self.assertFalse(timeline.is_timed_out(dealt, dealt + timedelta(seconds=12)))
        self.assertTrue(timeline.is_timed_out(dealt, dealt + timedelta(seconds=12, milliseconds=1)))
