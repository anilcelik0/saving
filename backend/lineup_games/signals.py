"""Game signals other Line Up apps listen to (lineup_social), so lineup_games never imports them."""

from django.dispatch import Signal

# sent inside the move transaction when a run stops playing (won / lost / finished); kwargs: run
run_finished = Signal()
