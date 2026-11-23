import time
import unittest

from notify.debounce import Debouncer


class DebounceTest(unittest.TestCase):
    def test_burst_sends_one_notification(self):
        sent = []
        d = Debouncer(0.05, sent.append)
        for i in range(5):
            d.trigger(i)
        time.sleep(0.06)
        self.assertEqual(sent, [4])

    def test_cancel_sends_nothing(self):
        sent = []
        d = Debouncer(0.05, sent.append)
        d.trigger(1)
        d.cancel()
        time.sleep(0.06)
        self.assertEqual(sent, [])

    def test_separate_bursts(self):
        sent = []
        d = Debouncer(0.05, sent.append)
        d.trigger("a")
        time.sleep(0.06)
        d.trigger("b")
        time.sleep(0.06)
        self.assertEqual(sent, ["a", "b"])
