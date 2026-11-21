"""Unit tests of the pure-Python engine (no database). Run: python manage.py test lineup_games"""

from datetime import datetime, timedelta
from decimal import Decimal
from unittest import TestCase

from lineup_games.engine import decks, energy, streak, timeline
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

    def wrong_slot(self, state):
        slots = timeline.valid_slots([self.values[c] for c in state.line], self.values[state.current])
        return next(i for i in range(len(state.line) + 1) if i not in slots)

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

    def test_slot_out_of_range(self):
        with self.assertRaises(ValueError):
            timeline.place(self.state, 5, self.values)

    def test_three_mistakes_lose(self):
        state = self.state
        for _ in range(3):
            state = timeline.place(state, self.wrong_slot(state), self.values).state
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
        state = timeline.place(self.state, self.wrong_slot(self.state), self.values).state
        state = timeline.place(state, self.wrong_slot(state), self.values).state
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


class StreakTests(TestCase):
    def setUp(self):
        self.values = make_values([1950, 1900, 2000, 2000, 1800])
        self.state = streak.start(["c0", "c1", "c2", "c3", "c4"])

    def test_start(self):
        self.assertEqual((self.state.open, self.state.current), ("c0", "c1"))
        self.assertEqual((self.state.lives, self.state.score, self.state.status), (1, 0, streak.PLAYING))

    def test_right_guess_extends_and_moves_on(self):
        result = streak.guess(self.state, streak.LOWER, self.values)  # 1900 < 1950
        self.assertTrue(result.correct)
        self.assertEqual(result.relation, streak.LOWER)
        self.assertEqual((result.state.score, result.state.open, result.state.current), (1, "c1", "c2"))

    def test_wrong_guess_loses_the_only_life(self):
        result = streak.guess(self.state, streak.HIGHER, self.values)
        self.assertFalse(result.correct)
        self.assertEqual((result.state.status, result.state.lives, result.state.score), (streak.LOST, 0, 0))
        self.assertIsNone(result.state.current)
        with self.assertRaises(ValueError):
            streak.guess(result.state, streak.LOWER, self.values)

    def test_equal_values_accept_either_guess(self):
        state = streak.guess(self.state, streak.LOWER, self.values).state
        state = streak.guess(state, streak.HIGHER, self.values).state  # 2000 after 1900
        for choice in streak.GUESSES:
            result = streak.guess(state, choice, self.values)  # 2000 after 2000
            self.assertTrue(result.correct)
            self.assertEqual(result.relation, "equal")

    def test_precision_tie(self):
        values = {"a": year(2001, 5, 3), "b": year(2001)}
        state = streak.start(["a", "b"])
        self.assertTrue(streak.guess(state, streak.LOWER, values).correct)
        self.assertTrue(streak.guess(state, streak.HIGHER, values).correct)

    def test_deck_runs_out(self):
        state = self.state
        for choice in (streak.LOWER, streak.HIGHER, streak.HIGHER, streak.LOWER):
            state = streak.guess(state, choice, self.values).state
        self.assertEqual((state.status, state.score), (streak.FINISHED, 4))

    def test_unknown_guess(self):
        with self.assertRaises(ValueError):
            streak.guess(self.state, "same", self.values)

    def test_continue_once(self):
        lost = streak.guess(self.state, streak.HIGHER, self.values).state
        self.assertTrue(streak.can_continue(lost))
        resumed = streak.resume(lost)
        self.assertEqual((resumed.status, resumed.lives, resumed.continues_used), (streak.PLAYING, 1, 1))
        self.assertEqual(resumed.current, "c2")
        lost_again = streak.guess(resumed, streak.LOWER, self.values).state  # 2000 after 1900: wrong
        self.assertFalse(streak.can_continue(lost_again))
        with self.assertRaises(ValueError):
            streak.resume(lost_again)

    def test_no_continue_while_playing_or_without_cards(self):
        self.assertFalse(streak.can_continue(self.state))
        values = make_values([1950, 2000])
        lost = streak.guess(streak.start(["c0", "c1"]), streak.LOWER, values).state
        self.assertEqual(lost.status, streak.LOST)
        self.assertFalse(streak.can_continue(lost))


class StreakDeckTests(TestCase):
    def setUp(self):
        self.pool = [DeckCard(id=f"y{1900 + i * 3}", value=year(1900 + i * 3), popularity=(90, 50, 10)[i % 3])
                     for i in range(40)]

    def test_same_seed_same_deck_any_input_order(self):
        a = decks.streak_deck("s1", self.pool, 30, True)
        b = decks.streak_deck("s1", list(reversed(self.pool)), 30, True)
        self.assertEqual(a, b)
        self.assertEqual(len(a), 30)
        self.assertEqual(len(set(a)), 30)
        self.assertNotEqual(a, decks.streak_deck("s2", self.pool, 30, True))

    def test_famous_cards_and_wide_gaps_first(self):
        by_id = {c.id: c for c in self.pool}
        deck = [by_id[i] for i in decks.streak_deck("s1", self.pool, 30, True)]
        self.assertTrue(all(c.popularity >= 60 for c in deck[:6]))
        for previous, card in zip(deck[:5], deck[1:6]):  # positions 1..5 = easy stage
            self.assertGreaterEqual(gap(previous.value, card.value), 15)

    def test_small_pool_is_whole_pool(self):
        deck = decks.streak_deck("s1", self.pool[:4], 60, True)
        self.assertEqual(sorted(deck), sorted(c.id for c in self.pool[:4]))
        self.assertEqual(decks.streak_deck("s1", [], 60, True), [])

    def test_numbers_use_relative_gap(self):
        pool = [DeckCard(id=f"n{i}", value=num(n), popularity=90) for i, n in enumerate([100, 105, 200, 110, 400])]
        deck = decks.streak_deck("s1", pool, 3, False)
        values = {c.id: c.value for c in pool}
        for a, b in zip(deck, deck[1:]):
            self.assertGreaterEqual(gap(values[a], values[b]), 0.3)


class EnergyTests(TestCase):
    rules = energy.EnergyRules(max=5, refill=timedelta(minutes=25))
    t0 = datetime(2026, 1, 1, 12, 0)

    def at(self, minutes):
        return self.t0 + timedelta(minutes=minutes)

    def test_full_start_and_spend_starts_the_clock(self):
        e = energy.spend(energy.full(self.t0, self.rules), self.at(10), self.rules)
        self.assertEqual((e.stored, e.since), (4, self.at(10)))
        self.assertEqual(energy.next_at(e, self.rules), self.at(35))
        self.assertEqual(energy.full_at(e, self.rules), self.at(35))

    def test_refill_keeps_partial_progress(self):
        e = energy.Energy(stored=1, since=self.t0)
        e = energy.spend(e, self.at(30), self.rules)  # +1 at 25 -> 2, spend -> 1, period started at 25 continues
        self.assertEqual((e.stored, e.since), (1, self.at(25)))
        self.assertEqual(energy.settle(e, self.at(49), self.rules).stored, 1)
        self.assertEqual(energy.settle(e, self.at(50), self.rules).stored, 2)

    def test_capped_at_max(self):
        e = energy.settle(energy.Energy(stored=0, since=self.t0), self.at(1000), self.rules)
        self.assertEqual((e.stored, e.since), (5, self.at(1000)))
        self.assertIsNone(energy.next_at(e, self.rules))
        self.assertIsNone(energy.full_at(e, self.rules))

    def test_not_enough(self):
        e = energy.Energy(stored=0, since=self.t0)
        with self.assertRaises(energy.NotEnoughEnergy):
            energy.spend(e, self.at(24), self.rules)
        self.assertEqual(energy.spend(e, self.at(25), self.rules).stored, 0)

    def test_full_at_counts_missing_points(self):
        e = energy.Energy(stored=2, since=self.t0)
        self.assertEqual(energy.full_at(e, self.rules), self.at(75))

    def test_grant_above_max_and_clock_idle(self):
        e = energy.grant(energy.full(self.t0, self.rules), self.at(5), self.rules, 2)
        self.assertEqual(e.stored, 7)
        e = energy.spend(e, self.at(6), self.rules)
        self.assertEqual((e.stored, e.since), (6, self.at(6)))
        self.assertIsNone(energy.next_at(e, self.rules))

    def test_clock_going_backwards_adds_nothing(self):
        e = energy.Energy(stored=2, since=self.t0)
        self.assertEqual(energy.settle(e, self.at(-60), self.rules).stored, 2)

    def test_grace(self):
        grace = timedelta(days=3)
        self.assertTrue(energy.in_grace(self.t0, self.t0 + timedelta(days=2, hours=23), grace))
        self.assertFalse(energy.in_grace(self.t0, self.t0 + timedelta(days=3), grace))
        self.assertFalse(energy.in_grace(self.t0, self.t0, timedelta(0)))
