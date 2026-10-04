# A small seeded random number generator (xorshift32). MicroPython's random
# module has no Random class, and this gives identical sequences on the badge
# and on a desktop, so seeded races and tests are reproducible everywhere.

import random as _random

_MASK = 0xFFFFFFFF


class Rng:
    def __init__(self, seed=None):
        if seed is None:
            seed = _random.getrandbits(30)
        s = (int(seed) * 2654435761 + 0x9E3779B9) & _MASK
        self.s = s or 0x2545F491

    def next32(self):
        x = self.s
        x ^= (x << 13) & _MASK
        x ^= x >> 17
        x ^= (x << 5) & _MASK
        self.s = x
        return x

    def random(self):
        return self.next32() / 4294967296.0

    def uniform(self, a, b):
        return a + (b - a) * self.random()

    def randrange(self, a, b=None):
        if b is None:
            a, b = 0, a
        return a + int(self.random() * (b - a))

    def randint(self, a, b):
        return self.randrange(a, b + 1)

    def choice(self, seq):
        return seq[self.randrange(len(seq))]
