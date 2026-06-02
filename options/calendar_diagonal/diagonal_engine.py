"""Alias y extensión de CalendarEngine para diagonals."""
from options.calendar_diagonal.calendar_engine import CalendarEngine, CalendarSpread


class DiagonalEngine(CalendarEngine):
    """Diagonal spreads: diferente strike Y diferente vencimiento."""

    def build(self, symbol, spot, front_contract, back_contract, quantity=1) -> CalendarSpread:
        return self.build_diagonal(symbol, spot, front_contract, back_contract, quantity)
