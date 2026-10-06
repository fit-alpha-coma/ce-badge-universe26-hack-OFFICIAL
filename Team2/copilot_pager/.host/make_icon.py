"""Generate the dependency-free 24x24 indexed Copilot Pager launcher icon."""

import os
import struct
import zlib


SIZE = 24
BACKGROUND = 0
PANEL = 1
PURPLE = 2
GREEN = 3
WHITE = 4
MUTED = 5


def pixels():
    image = [[BACKGROUND for _ in range(SIZE)] for _ in range(SIZE)]
    for y in range(3, 21):
        for x in range(2, 22):
            if (x in (2, 21) and y in (3, 20)):
                continue
            image[y][x] = PANEL
    for x in range(4, 20):
        image[5][x] = PURPLE
    image[4][5] = image[4][6] = PURPLE
    image[4][17] = image[4][18] = PURPLE
    image[7][18] = image[7][19] = GREEN
    image[8][18] = image[8][19] = GREEN
    for offset in range(5):
        image[10 + offset][6 + offset] = WHITE
        image[14 - offset][6 + offset] = WHITE
    for x in range(12, 18):
        image[15][x] = MUTED
        image[16][x] = MUTED
    return image


def chunk(kind, data):
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)


def main():
    palette = bytes(
        (
            13, 17, 23,
            33, 38, 45,
            163, 113, 247,
            63, 185, 80,
            240, 246, 252,
            139, 148, 158,
        )
    )
    palette += b"\x00" * (768 - len(palette))
    raw = b"".join(b"\x00" + bytes(row) for row in pixels())
    png = b"\x89PNG\r\n\x1a\n"
    png += chunk(b"IHDR", struct.pack(">IIBBBBB", SIZE, SIZE, 8, 3, 0, 0, 0))
    png += chunk(b"PLTE", palette)
    png += chunk(b"IDAT", zlib.compress(raw, 9))
    png += chunk(b"IEND", b"")
    destination = os.path.join(os.path.dirname(__file__), "..", "icon.png")
    with open(destination, "wb") as output:
        output.write(png)
    print(destination)


if __name__ == "__main__":
    main()

