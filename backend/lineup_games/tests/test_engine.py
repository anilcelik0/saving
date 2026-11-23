"""Unit tests of the pure-Python engine (no database). Run: python manage.py test lineup_games"""

from datetime import datetime, timedelta
from decimal import Decimal
from unittest import TestCase

from lineup_games.engine import daily, decks, energy, streak, timeline
from lineup_games.engine.decks import DeckCard, DeckParams
from lineup_games.engine.values import Value, compare, gap, sort_key


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

    def test_sort_key_follows_compare(self):
        values = [year(-500, 3), year(-500), year(1453, 5, 29), year(1453), year(1923, 10, 29), year(1)]
        ordered = sorted(values, key=sort_key)
        self.assertEqual(ordered, [year(-500), year(-500, 3), year(1), year(1453), year(1453, 5, 29), year(1923, 10, 29)])
        self.assertLess(sort_key(num("-3.5")), sort_key(num("2")))
        self.assertEqual(sort_key(num("10.50")), 10.5)

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

    def lose(self, state):
        while state.status == timeline.PLAYING:
            state = timeline.place(state, self.wrong_slot(state), self.values).state
        return state

    def test_continue_once_after_losing(self):
        lost = self.lose(self.state)
        self.assertEqual((lost.status, lost.lives), (timeline.LOST, 0))
        self.assertTrue(timeline.can_continue(lost))
        resumed = timeline.resume(lost)
        self.assertEqual((resumed.status, resumed.lives, resumed.continues_used), (timeline.PLAYING, 1, 1))
        self.assertEqual(resumed.line, lost.line)
        self.assertEqual(resumed.current, self.state.deck[lost.next_index])
        lost_again = self.lose(resumed)
        self.assertFalse(timeline.can_continue(lost_again))
        with self.assertRaises(ValueError):
            timeline.resume(lost_again)

    def test_no_continue_unless_lost_on_lives(self):
        self.assertFalse(timeline.can_continue(self.state))
        short = timeline.start(["c0", "c1", "c2"])
        for _ in range(2):
            short = timeline.place(short, self.wrong_slot(short), self.values).state
        self.assertEqual(short.status, timeline.FINISHED)  # deck ended with lives left
        self.assertFalse(timeline.can_continue(short))

    def test_deck_has_room_for_the_continue(self):
        self.assertEqual(timeline.deck_size(), 14)
        # worst case: lost with 0 placed after 3 misses -> 1 + 3 used, 10 left >= 9 needed + 0 spare
        self.assertGreaterEqual(timeline.deck_size() - 4, timeline.TARGET - 1)

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
        self.assertEqual(timeline.deck_size(), timeline.TARGET + timeline.LIVES + timeline.MAX_CONTINUES)


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


class DailyDeckTests(TestCase):
    def setUp(self):
        self.pool = [DeckCard(id=f"y{1900 + i * 7}", value=year(1900 + i * 7), popularity=(90, 50, 10)[i % 3])
                     for i in range(30)]
        self.values = {c.id: c.value for c in self.pool}

    def test_same_seed_same_deck_any_input_order(self):
        a = decks.daily_deck("2026-11-22", self.pool, daily.SIZE, True)
        self.assertEqual(a, decks.daily_deck("2026-11-22", list(reversed(self.pool)), daily.SIZE, True))
        self.assertEqual(len(set(a)), daily.SIZE)
        self.assertNotEqual(a, decks.daily_deck("2026-11-23", self.pool, daily.SIZE, True))

    def test_known_cards_with_a_gap(self):
        deck = decks.daily_deck("s", self.pool, daily.SIZE, True)
        by_id = {c.id: c for c in self.pool}
        self.assertTrue(all(by_id[c].popularity >= 40 for c in deck))
        for i, a in enumerate(deck):
            for b in deck[i + 1:]:
                self.assertGreaterEqual(gap(self.values[a], self.values[b]), 4)

    def test_small_known_pool_falls_back_to_whole_pool(self):
        pool = [DeckCard(id=f"c{i}", value=year(2000 + i * 10), popularity=10) for i in range(8)]
        self.assertEqual(len(decks.daily_deck("s", pool, daily.SIZE, True)), daily.SIZE)

    def test_never_shown_sorted(self):
        pool = [DeckCard(id=f"c{i}", value=year(2000 + i * 10), popularity=90) for i in range(6)]
        values = {c.id: c.value for c in pool}
        for seed in map(str, range(300)):
            deck = decks.daily_deck(seed, pool, 6, True)
            self.assertNotEqual(deck, daily.solution(deck, values), seed)


class DailyTests(TestCase):
    def setUp(self):
        # sorted order: a b c d e f
        self.values = {k: year(y) for k, y in zip("abcdef", [1900, 1920, 1940, 1960, 1980, 2000])}
        self.state = daily.start(list("fedcba"))

    def test_marks_right_near_wrong(self):
        self.assertEqual(daily.marks(list("abcdef"), self.values), (daily.RIGHT,) * 6)
        self.assertEqual(daily.marks(list("bacdfe"), self.values),
                         (daily.NEAR, daily.NEAR, daily.RIGHT, daily.RIGHT, daily.NEAR, daily.NEAR))
        self.assertEqual(daily.marks(list("fbcdea"), self.values)[0], daily.WRONG)

    def test_ties_accept_either_position(self):
        values = {"a": year(1999), "b": year(1999, 5), "c": year(2010)}
        self.assertEqual(daily.rank_range("a", values), (0, 1))
        self.assertEqual(daily.marks(["b", "a", "c"], values), (daily.RIGHT,) * 3)
        self.assertEqual(daily.marks(["a", "b", "c"], values), (daily.RIGHT,) * 3)

    def test_solve_on_second_attempt(self):
        first = daily.submit(self.state, list("bacdef"), self.values)
        self.assertFalse(first.solved)
        self.assertEqual(first.state.status, daily.PLAYING)
        self.assertEqual(first.state.attempts_left, daily.ATTEMPTS - 1)
        second = daily.submit(first.state, list("abcdef"), self.values)
        self.assertTrue(second.solved)
        self.assertEqual(second.state.status, daily.WON)
        self.assertEqual(second.state.solved_in, 2)
        with self.assertRaises(ValueError):
            daily.submit(second.state, list("abcdef"), self.values)

    def test_lost_after_every_attempt_wrong(self):
        state = self.state
        for _ in range(daily.ATTEMPTS):
            state = daily.submit(state, list("bacdef"), self.values).state
        self.assertEqual(state.status, daily.LOST)
        self.assertIsNone(state.solved_in)
        self.assertEqual(daily.solution(state.deck, self.values), list("abcdef"))

    def test_order_must_hold_the_puzzle_cards(self):
        for order in (list("abcde"), list("abcdeX"), list("abcdea")):
            with self.assertRaises(ValueError):
                daily.submit(self.state, order, self.values)

    def test_streaks(self):
        self.assertEqual(daily.streaks(set(), 5), (0, 0))
        self.assertEqual(daily.streaks({3, 4, 5}, 5), (3, 3))  # solved today
        self.assertEqual(daily.streaks({3, 4}, 5), (2, 2))  # today still open: yesterday's run counts
        self.assertEqual(daily.streaks({3, 4}, 5, current_lost=True), (0, 2))  # lost today
        self.assertEqual(daily.streaks({1, 2, 3, 5}, 6), (1, 3))  # day 4 missed
        self.assertEqual(daily.streaks({1, 2}, 6), (0, 2))
