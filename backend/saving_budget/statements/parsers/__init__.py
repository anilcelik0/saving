# Importing the modules registers their parsers. Order matters: bank-specific parsers first,
# the generic fallback (accepts any PDF) must be imported LAST.
from . import enpara, garanti, qnb, vakifbank  # noqa: F401, I001
from . import generic  # noqa: F401, E402
