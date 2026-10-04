# Super Mona Kart: the badge mascots' Grand Prix.
import os
import sys

# MicroPython has no os.path; fall back to the deployed location
APP_DIR = __file__.rsplit("/", 1)[0] if "/" in __file__ else "/system/apps/super_mona_kart"
os.chdir(APP_DIR)
sys.path.insert(0, APP_DIR)

badge.mode(HIRES | VSYNC)

from art import Art
from game import Game

game = Game(Art())


def update():
    game.update()


def on_exit():
    game.exit()


run(update)
