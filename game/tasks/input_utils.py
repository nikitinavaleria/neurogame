import pygame


LEFT_KEYS = {pygame.K_f, pygame.K_a}
RIGHT_KEYS = {pygame.K_j, pygame.K_o}
LEFT_CHARS = {"f", "a", "а"}  # латиница/кириллица
RIGHT_CHARS = {"j", "o", "о"}  # латиница/кириллица


def read_left_right_key(event: pygame.event.Event):
    if event.type != pygame.KEYDOWN:
        return None
    if event.key in LEFT_KEYS:
        return "LEFT"
    if event.key in RIGHT_KEYS:
        return "RIGHT"
    char = (event.unicode or "").lower()
    if char in LEFT_CHARS:
        return "LEFT"
    if char in RIGHT_CHARS:
        return "RIGHT"
    return None
