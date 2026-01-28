import pygame

from data.models import BlockParams
from game.input import InputManager
from game.renderer import Renderer
from game.scene import GameScene

pygame.init()

# 1. Создаём окно
screen = pygame.display.set_mode((800, 600))
pygame.display.set_caption("Shifrovshik")

clock = pygame.time.Clock()

# 2. Создаём вспомогательные объекты
input_manager = InputManager()
renderer = Renderer(screen)

# 3. Параметры блока (самое простое)
params = BlockParams(
    n_trials=20,
    tasks_enabled=["COLOR", "SHAPE"],
    switch_rate=0.3,
)

# 4. Создаём сцену (один игровой блок)
scene = GameScene(
    screen=screen,
    renderer=renderer,
    input_manager=input_manager,
    block_params=params,
    seed=1,
)

scene.start()

# -------------------------------------------------
# Главный игровой цикл
# -------------------------------------------------

running = True
while running:
    clock.tick(60)  # 60 FPS

    # 5. Обрабатываем события
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False

        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            running = False

        scene.handle_event(event)

    # 6. Обновляем сцену (логика + рисование)
    scene.update()

    # 7. Если блок закончился — выходим
    if scene.is_finished():
        running = False

pygame.quit()

# -------------------------------------------------
# Результаты
# -------------------------------------------------

print("Game finished")
for e in scene.get_results():
    print(
        e.trial_index,
        e.task_id,
        e.response_action,
        e.is_correct,
        e.rt_ms,
    )
