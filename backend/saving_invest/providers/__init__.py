from .altinkaynak import AltinkaynakProvider
from .tcmb import TcmbProvider

# provider key (Asset.provider) -> adapter class; swap or add sources here
PROVIDERS = {cls.key: cls for cls in (TcmbProvider, AltinkaynakProvider)}
