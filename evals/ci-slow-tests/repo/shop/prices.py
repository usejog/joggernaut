"""A stand-in for the price service the shop calls over the network."""
import time


class PriceServer:
    """Talks to the real price service. Each call takes about half a second."""

    def __init__(self, prices=None):
        self._prices = prices or {"apple": 120, "pear": 90, "fig": 250, "plum": 75}

    def price(self, sku):
        time.sleep(0.5)  # network round trip to the price service
        if sku not in self._prices:
            raise KeyError(sku)
        return self._prices[sku]
