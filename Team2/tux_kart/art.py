# Kart sprites, drawn with shapes at startup so the app ships no art files.
#
# Each kart has three views: from behind, from the side (facing right; blit it
# with a negative width to face left) and from the front.

SPRITE_W = 26
SPRITE_H = 22

BLACK = (18, 18, 24)
WHITE = (240, 240, 236)
BEAK = (250, 176, 28)
TYRE = (30, 30, 34)


def _pen(img, rgb, a=255):
    img.pen = color.rgb(rgb[0], rgb[1], rgb[2], a)


def _blank():
    img = image(SPRITE_W, SPRITE_H)
    img.pen = color.rgb(0, 0, 0, 0)
    img.clear()
    return img


def _darker(rgb, k=0.6):
    return (int(rgb[0] * k), int(rgb[1] * k), int(rgb[2] * k))


def _back(body, helmet):
    img = _blank()
    _pen(img, TYRE)
    img.rectangle(1, 13, 6, 9)
    img.rectangle(19, 13, 6, 9)
    _pen(img, body)
    img.shape(shape.rounded_rectangle(4, 11, 18, 8, 3))
    _pen(img, _darker(body))
    img.rectangle(6, 17, 14, 3)
    _pen(img, (200, 200, 200))
    img.rectangle(9, 18, 2, 2)
    img.rectangle(15, 18, 2, 2)
    # penguin seen from behind: all black, flippers out, coloured helmet
    _pen(img, BLACK)
    img.circle(13, 9, 5)
    img.circle(13, 4, 4)
    img.triangle(7, 7, 9, 6, 9, 11)
    img.triangle(19, 7, 17, 6, 17, 11)
    _pen(img, helmet)
    img.shape(shape.pie(13, 4, 4.5, -90, 90))
    _pen(img, WHITE)
    img.rectangle(12, 0, 2, 3)
    return img


def _side(body, helmet):
    img = _blank()
    _pen(img, body)
    img.shape(shape.rounded_rectangle(2, 12, 22, 6, 2))
    _pen(img, _darker(body))
    img.triangle(18, 12, 25, 15, 18, 17)
    _pen(img, TYRE)
    img.circle(6, 18, 3.5)
    img.circle(20, 18, 3.5)
    _pen(img, (150, 150, 150))
    img.circle(6, 18, 1.2)
    img.circle(20, 18, 1.2)
    # penguin facing right: black back, white belly, orange beak
    _pen(img, BLACK)
    img.circle(11, 9, 5)
    img.circle(13, 4, 4)
    _pen(img, WHITE)
    img.circle(13, 10, 3)
    img.circle(15, 4, 2)
    _pen(img, BLACK)
    img.rectangle(15, 3, 1, 1)
    _pen(img, BEAK)
    img.triangle(16, 4, 20, 5, 16, 6)
    _pen(img, helmet)
    img.shape(shape.pie(13, 4, 4.5, -90, 45))
    return img


def _front(body, helmet):
    img = _blank()
    _pen(img, TYRE)
    img.rectangle(1, 13, 6, 9)
    img.rectangle(19, 13, 6, 9)
    _pen(img, body)
    img.shape(shape.rounded_rectangle(4, 12, 18, 8, 3))
    _pen(img, BLACK)
    img.circle(13, 9, 5)
    img.circle(13, 4, 4)
    _pen(img, WHITE)
    img.circle(13, 10, 3.5)
    img.circle(13, 5, 2.6)
    _pen(img, BLACK)
    img.rectangle(11, 3, 1, 2)
    img.rectangle(15, 3, 1, 2)
    _pen(img, BEAK)
    img.triangle(11, 6, 15, 6, 13, 8)
    _pen(img, helmet)
    img.shape(shape.pie(13, 4, 4.5, -90, 90))
    _pen(img, _darker(body))
    img.rectangle(6, 17, 14, 2)
    return img


def kart_views(body, helmet):
    return (_back(body, helmet), _side(body, helmet), _front(body, helmet))
