import pygame
import sys
import os
from dataclasses import dataclass

# --- Audio: safe pre-init and loader ---
pygame.mixer.pre_init(frequency=44100, size=-16, channels=2, buffer=512)
SFX = {}

def load_sfx(name, path):
    try:
        if os.path.exists(path):
            if not pygame.mixer.get_init():
                pygame.mixer.init()
            SFX[name] = pygame.mixer.Sound(path)
    except Exception:
        # Keep silent if audio device/files unavailable
        pass

# Attempt loads (no crash if files missing)
load_sfx("ping",   "assets/sfx/ping.ogg")
load_sfx("brick",  "assets/sfx/brick.ogg")
load_sfx("score",  "assets/sfx/score.ogg")
load_sfx("select", "assets/sfx/select.ogg")

# --- Config ---
WIDTH, HEIGHT = 960, 540
FPS = 60
PADDLE_W, PADDLE_H = 14, 96
BALL_SIZE = 12
BRICK_W, BRICK_H = 18, 12
BRICK_COLS, BRICK_ROWS = 14, 16  # central wall grid
WALL_GAP = 80  # vertical gap between top/bottom of wall and screen edges
WIN_SCORE = 7

# Pixel-perfect base surface (retro scaling)
BASE_W, BASE_H = 320, 180

# 8-bit-ish palette
BLACK = (0, 0, 0)
WHITE = (245, 245, 245)
NEON_CYAN = (0, 255, 255)
NEON_MAGENTA = (255, 0, 170)
NEON_YELLOW = (255, 255, 0)
NEON_ORANGE = (255, 128, 0)
NEON_GREEN = (0, 255, 128)

@dataclass
class Paddle:
    rect: pygame.Rect
    speed: int = 7

    def move(self, dy: int):
        self.rect.y += dy * self.speed
        self.rect.y = max(0, min(HEIGHT - self.rect.height, self.rect.y))

@dataclass
class Ball:
    rect: pygame.Rect
    vx: int
    vy: int
    speed_max: int = 12
    speed_min: int = 4
    hit_cooldown_frames: int = 0  # prevent double-collisions on paddles

    def update(self):
        # cooldown tick
        if self.hit_cooldown_frames > 0:
            self.hit_cooldown_frames -= 1

        self.rect.x += self.vx
        self.rect.y += self.vy

        # bounce top/bottom
        if self.rect.top <= 0 or self.rect.bottom >= HEIGHT:
            self.vy = -self.vy
            self.rect.y += self.vy
            self._clamp_speed()

    def accelerate(self, amount=1):
        # increase horizontal speed slightly, clamp
        if self.vx > 0:
            self.vx = min(self.vx + amount, self.speed_max)
        else:
            self.vx = max(self.vx - amount, -self.speed_max)
        self._clamp_speed()

    def _clamp_speed(self):
        # ensure horizontal component isn't too weak
        if abs(self.vx) < self.speed_min:
            self.vx = self.speed_min if self.vx >= 0 else -self.speed_min
        # keep vy reasonable so rallies don't go vertical-only
        if self.vy == 0:
            self.vy = 1 if pygame.time.get_ticks() % 2 else -1
        self.vy = max(-self.speed_max, min(self.vy, self.speed_max))

class BrickWall:
    def __init__(self):
        self.bricks = []
        total_h = BRICK_ROWS * BRICK_H
        start_y = (HEIGHT - total_h) // 2
        x = (WIDTH - BRICK_W) // 2
        colors = [NEON_CYAN, NEON_MAGENTA, NEON_YELLOW, NEON_ORANGE, NEON_GREEN]
        for r in range(BRICK_ROWS):
            y = start_y + r * BRICK_H
            # leave gap near top/bottom edges
            if y < WALL_GAP or y + BRICK_H > HEIGHT - WALL_GAP:
                continue
            color = colors[r % len(colors)]
            self.bricks.append((pygame.Rect(x, y, BRICK_W, BRICK_H), color))

    def draw(self, surf):
        for rect, color in self.bricks:
            pygame.draw.rect(surf, color, rect)

    def collide(self, ball: Ball):
        # check collision with any brick in list
        for i, (rect, color) in enumerate(self.bricks):
            if ball.rect.colliderect(rect):
                # decide bounce axis by penetration
                overlap_left = ball.rect.right - rect.left
                overlap_right = rect.right - ball.rect.left
                overlap_top = ball.rect.bottom - rect.top
                overlap_bottom = rect.bottom - ball.rect.top
                min_overlap = min(overlap_left, overlap_right, overlap_top, overlap_bottom)
                if min_overlap in (overlap_left, overlap_right):
                    ball.vx = -ball.vx
                else:
                    ball.vy = -ball.vy
                del self.bricks[i]
                ball.accelerate(1)
                if "brick" in SFX: SFX["brick"].play()
                return True
        return False


def reset_ball(direction: int = 1) -> Ball:
    # direction: 1 -> to right, -1 -> to left
    return Ball(pygame.Rect(WIDTH // 2 - BALL_SIZE // 2, HEIGHT // 2 - BALL_SIZE // 2, BALL_SIZE, BALL_SIZE),
                vx=direction * 6, vy=4)


def main():
    pygame.init()
    screen = pygame.display.set_mode((WIDTH, HEIGHT))
    pygame.display.set_caption("PongOnTheRocks 🕹️")
    clock = pygame.time.Clock()

    # base surface for crisp scaling
    base = pygame.Surface((BASE_W, BASE_H))

    # Fonts (scaled with base for retro look)
    font = pygame.font.SysFont("PressStart2P,monospace", 12)
    big = pygame.font.SysFont("PressStart2P,monospace", 18)

    # game state
    MENU, PLAY = 0, 1
    mode = MENU
    two_player = False

    # entities
    left = Paddle(pygame.Rect(16, HEIGHT // 2 - PADDLE_H // 2, PADDLE_W, PADDLE_H))
    right = Paddle(pygame.Rect(WIDTH - 16 - PADDLE_W, HEIGHT // 2 - PADDLE_H // 2, PADDLE_W, PADDLE_H))
    ball = reset_ball(direction=1)
    wall = BrickWall()

    score_l = 0
    score_r = 0
    winner = None

    def draw_center_line(surf):
        # dashed center line for retro flair (draw in screen coords then scaled, it's fine)
        dash_h = 6
        for y in range(0, BASE_H, dash_h * 2):
            pygame.draw.rect(surf, (40, 40, 40), (BASE_W // 2 - 1, y, 2, dash_h))

    while True:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit()
            if mode == MENU and event.type == pygame.KEYDOWN:
                if event.key == pygame.K_1:
                    two_player = False
                    mode = PLAY
                    if "select" in SFX: SFX["select"].play()
                    score_l = score_r = 0
                    winner = None
                    ball = reset_ball(direction=1)
                    wall = BrickWall()
                elif event.key == pygame.K_2:
                    two_player = True
                    mode = PLAY
                    if "select" in SFX: SFX["select"].play()
                    score_l = score_r = 0
                    winner = None
                    ball = reset_ball(direction=-1)
                    wall = BrickWall()

        keys = pygame.key.get_pressed()

        if mode == PLAY:
            if winner is None:
                # Player controls
                dy_l = (keys[pygame.K_s] - keys[pygame.K_w]) if keys[pygame.K_w] or keys[pygame.K_s] else 0
                left.move(dy_l)

                if two_player:
                    dy_r = (keys[pygame.K_DOWN] - keys[pygame.K_UP]) if keys[pygame.K_UP] or keys[pygame.K_DOWN] else 0
                    right.move(dy_r)
                else:
                    # simple AI: move toward ball Y with easing
                    if ball.rect.centery < right.rect.centery - 8:
                        right.move(-1)
                    elif ball.rect.centery > right.rect.centery + 8:
                        right.move(1)

                # Update ball
                ball.update()

                # Paddle collisions with cooldown and "english"
                if ball.rect.colliderect(left.rect) and ball.vx < 0 and ball.hit_cooldown_frames == 0:
                    ball.vx = -ball.vx
                    offset = (ball.rect.centery - left.rect.centery) / (PADDLE_H / 2)
                    ball.vy += int(offset * 3)
                    ball.accelerate(1)
                    ball.hit_cooldown_frames = 6
                    if "ping" in SFX: SFX["ping"].play()

                if ball.rect.colliderect(right.rect) and ball.vx > 0 and ball.hit_cooldown_frames == 0:
                    ball.vx = -ball.vx
                    offset = (ball.rect.centery - right.rect.centery) / (PADDLE_H / 2)
                    ball.vy += int(offset * 3)
                    ball.accelerate(1)
                    ball.hit_cooldown_frames = 6
                    if "ping" in SFX: SFX["ping"].play()

                # Wall collisions (and break bricks)
                wall.collide(ball)

                # Scoring
                if ball.rect.right < 0:
                    score_r += 1
                    if "score" in SFX: SFX["score"].play()
                    ball = reset_ball(direction=1)
                elif ball.rect.left > WIDTH:
                    score_l += 1
                    if "score" in SFX: SFX["score"].play()
                    ball = reset_ball(direction=-1)

                # Win check
                if score_l >= WIN_SCORE:
                    winner = "P1"
                elif score_r >= WIN_SCORE:
                    winner = "P2"

            else:
                # Winner state: restart on Enter
                if keys[pygame.K_RETURN]:
                    score_l = score_r = 0
                    ball = reset_ball(direction=1 if winner == "P2" else -1)
                    wall = BrickWall()
                    winner = None

        # --- Draw to base surface ---
        base.fill(BLACK)
        draw_center_line(base)

        if mode == MENU:
            wall.draw(base)
            title = big.render("PongOnTheRocks", True, NEON_MAGENTA)
            subtitle = font.render("1: Single  2: Two Player", True, NEON_CYAN)
            hint = font.render("W/S & ↑/↓ move  |  Enter restart  |  Esc quit", True, NEON_YELLOW)
            base.blit(title, (BASE_W//2 - title.get_width()//2, BASE_H//3 - 12))
            base.blit(subtitle, (BASE_W//2 - subtitle.get_width()//2, BASE_H//3 + 10))
            base.blit(hint, (BASE_W//2 - hint.get_width()//2, BASE_H//3 + 30))
        else:
            # draw paddles, ball, wall, score
            pygame.draw.rect(base, NEON_CYAN, pygame.Rect(int(left.rect.x * BASE_W / WIDTH), int(left.rect.y * BASE_H / HEIGHT), int(PADDLE_W * BASE_W / WIDTH), int(PADDLE_H * BASE_H / HEIGHT)))
            pygame.draw.rect(base, NEON_MAGENTA, pygame.Rect(int(right.rect.x * BASE_W / WIDTH), int(right.rect.y * BASE_H / HEIGHT), int(PADDLE_W * BASE_W / WIDTH), int(PADDLE_H * BASE_H / HEIGHT)))
            pygame.draw.rect(base, WHITE, pygame.Rect(int(ball.rect.x * BASE_W / WIDTH), int(ball.rect.y * BASE_H / HEIGHT), int(BALL_SIZE * BASE_W / WIDTH), int(BALL_SIZE * BASE_H / HEIGHT)))
            # Draw wall using screen-space rects scaled down
            for rect, color in wall.bricks:
                r = pygame.Rect(int(rect.x * BASE_W / WIDTH), int(rect.y * BASE_H / HEIGHT), int(rect.w * BASE_W / WIDTH), int(rect.h * BASE_H / HEIGHT))
                pygame.draw.rect(base, color, r)

            score_text = big.render(f"{score_l}   {score_r}", True, NEON_YELLOW)
            base.blit(score_text, (BASE_W//2 - score_text.get_width()//2, 6))

            if winner:
                banner = big.render(f"{winner} WINS! Press Enter", True, NEON_ORANGE)
                base.blit(banner, (BASE_W//2 - banner.get_width()//2, BASE_H//2 - banner.get_height()//2))

        # --- Scale base -> screen with nearest-neighbor and flip ---
        pygame.transform.scale(base, (WIDTH, HEIGHT), screen)
        pygame.display.flip()
        clock.tick(FPS)

        # global quit
        if keys[pygame.K_ESCAPE]:
            pygame.quit()
            sys.exit()


if __name__ == "__main__":
    main()
```python
import pygame
import sys
from dataclasses import dataclass

# --- Config ---
WIDTH, HEIGHT = 960, 540
FPS = 60
PADDLE_W, PADDLE_H = 14, 96
BALL_SIZE = 12
BRICK_W, BRICK_H = 18, 12
BRICK_COLS, BRICK_ROWS = 14, 16  # central wall grid
WALL_GAP = 80  # vertical gap between top/bottom of wall and screen edges

# 8-bit-ish palette
BLACK = (0, 0, 0)
WHITE = (245, 245, 245)
NEON_CYAN = (0, 255, 255)
NEON_MAGENTA = (255, 0, 170)
NEON_YELLOW = (255, 255, 0)
NEON_ORANGE = (255, 128, 0)
NEON_GREEN = (0, 255, 128)

@dataclass
class Paddle:
    rect: pygame.Rect
    speed: int = 7

    def move(self, dy: int):
        self.rect.y += dy * self.speed
        self.rect.y = max(0, min(HEIGHT - self.rect.height, self.rect.y))

@dataclass
class Ball:
    rect: pygame.Rect
    vx: int
    vy: int
    speed_max: int = 12

    def update(self):
        self.rect.x += self.vx
        self.rect.y += self.vy

        # bounce top/bottom
        if self.rect.top <= 0 or self.rect.bottom >= HEIGHT:
            self.vy = -self.vy
            self.rect.y += self.vy

    def accelerate(self, amount=1):
        # increase speed slightly, clamp
        if self.vx > 0:
            self.vx = min(self.vx + amount, self.speed_max)
        else:
            self.vx = max(self.vx - amount, -self.speed_max)

class BrickWall:
    def __init__(self):
        self.bricks = []
        total_h = BRICK_ROWS * BRICK_H
        start_y = (HEIGHT - total_h) // 2
        x = (WIDTH - BRICK_W) // 2
        colors = [NEON_CYAN, NEON_MAGENTA, NEON_YELLOW, NEON_ORANGE, NEON_GREEN]
        for r in range(BRICK_ROWS):
            y = start_y + r * BRICK_H
            # leave gap near top/bottom edges
            if y < WALL_GAP or y + BRICK_H > HEIGHT - WALL_GAP:
                continue
            color = colors[r % len(colors)]
            self.bricks.append((pygame.Rect(x, y, BRICK_W, BRICK_H), color))

    def draw(self, surf):
        for rect, color in self.bricks:
            pygame.draw.rect(surf, color, rect)

    def collide(self, ball: Ball):
        # check collision with any brick in list
        for i, (rect, color) in enumerate(self.bricks):
            if ball.rect.colliderect(rect):
                # decide bounce axis by penetration
                overlap_left = ball.rect.right - rect.left
                overlap_right = rect.right - ball.rect.left
                overlap_top = ball.rect.bottom - rect.top
                overlap_bottom = rect.bottom - ball.rect.top
                min_overlap = min(overlap_left, overlap_right, overlap_top, overlap_bottom)
                if min_overlap in (overlap_left, overlap_right):
                    ball.vx = -ball.vx
                else:
                    ball.vy = -ball.vy
                del self.bricks[i]
                ball.accelerate(1)
                return True
        return False


def reset_ball(direction: int = 1) -> Ball:
    # direction: 1 -> to right, -1 -> to left
    return Ball(pygame.Rect(WIDTH // 2 - BALL_SIZE // 2, HEIGHT // 2 - BALL_SIZE // 2, BALL_SIZE, BALL_SIZE),
                vx=direction * 6, vy=4)


def main():
    pygame.init()
    screen = pygame.display.set_mode((WIDTH, HEIGHT))
    pygame.display.set_caption("PongOnTheRocks 🕹️")
    clock = pygame.time.Clock()
    font = pygame.font.SysFont("PressStart2P,monospace", 20)
    big = pygame.font.SysFont("PressStart2P,monospace", 28)

    # game state
    MENU, PLAY = 0, 1
    mode = MENU
    two_player = False

    # entities
    left = Paddle(pygame.Rect(32, HEIGHT // 2 - PADDLE_H // 2, PADDLE_W, PADDLE_H))
    right = Paddle(pygame.Rect(WIDTH - 32 - PADDLE_W, HEIGHT // 2 - PADDLE_H // 2, PADDLE_W, PADDLE_H))
    ball = reset_ball(direction=1)
    wall = BrickWall()

    score_l = 0
    score_r = 0

    def draw_center_line():
        # dashed center line for retro flair
        dash_h = 12
        for y in range(0, HEIGHT, dash_h * 2):
            pygame.draw.rect(screen, (40, 40, 40), (WIDTH // 2 - 2, y, 4, dash_h))

    while True:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit()
            if mode == MENU and event.type == pygame.KEYDOWN:
                if event.key == pygame.K_1:
                    two_player = False
                    mode = PLAY
                    score_l = score_r = 0
                    ball = reset_ball(direction=1)
                    wall = BrickWall()
                elif event.key == pygame.K_2:
                    two_player = True
                    mode = PLAY
                    score_l = score_r = 0
                    ball = reset_ball(direction=-1)
                    wall = BrickWall()

        keys = pygame.key.get_pressed()

        if mode == PLAY:
            # Player controls
            dy_l = (keys[pygame.K_s] - keys[pygame.K_w]) if keys[pygame.K_w] or keys[pygame.K_s] else 0
            left.move(dy_l)

            if two_player:
                dy_r = (keys[pygame.K_DOWN] - keys[pygame.K_UP]) if keys[pygame.K_UP] or keys[pygame.K_DOWN] else 0
                right.move(dy_r)
            else:
                # simple AI: move toward ball Y with a little easing
                if ball.rect.centery < right.rect.centery - 8:
                    right.move(-1)
                elif ball.rect.centery > right.rect.centery + 8:
                    right.move(1)

            # Update ball
            ball.update()

            # Paddle collisions
            if ball.rect.colliderect(left.rect) and ball.vx < 0:
                ball.vx = -ball.vx
                # add a little english from where it hits the paddle
                offset = (ball.rect.centery - left.rect.centery) / (PADDLE_H / 2)
                ball.vy += int(offset * 3)
                ball.accelerate(1)

            if ball.rect.colliderect(right.rect) and ball.vx > 0:
                ball.vx = -ball.vx
                offset = (ball.rect.centery - right.rect.centery) / (PADDLE_H / 2)
                ball.vy += int(offset * 3)
                ball.accelerate(1)

            # Wall collisions (and break bricks)
            wall.collide(ball)

            # Scoring
            if ball.rect.right < 0:
                score_r += 1
                ball = reset_ball(direction=1)
            elif ball.rect.left > WIDTH:
                score_l += 1
                ball = reset_ball(direction=-1)

        # --- Draw ---
        screen.fill(BLACK)
        draw_center_line()

        if mode == MENU:
            title = big.render("PongOnTheRocks", True, NEON_MAGENTA)
            subtitle = font.render("1: Single Player    2: Two Player", True, NEON_CYAN)
            hint = font.render("W/S & ↑/↓ to move    Esc to quit", True, NEON_YELLOW)
            wall.draw(screen)
            screen.blit(title, (WIDTH//2 - title.get_width()//2, HEIGHT//3 - 30))
            screen.blit(subtitle, (WIDTH//2 - subtitle.get_width()//2, HEIGHT//3 + 20))
            screen.blit(hint, (WIDTH//2 - hint.get_width()//2, HEIGHT//3 + 60))
        else:
            # draw paddles, ball, wall, score
            pygame.draw.rect(screen, NEON_CYAN, left.rect)
            pygame.draw.rect(screen, NEON_MAGENTA, right.rect)
            pygame.draw.rect(screen, WHITE, ball.rect)
            wall.draw(screen)

            score_text = big.render(f"{score_l}   {score_r}", True, NEON_YELLOW)
            screen.blit(score_text, (WIDTH//2 - score_text.get_width()//2, 16))

        pygame.display.flip()
        clock.tick(FPS)

        # global quit
        if keys[pygame.K_ESCAPE]:
            pygame.quit()
            sys.exit()


if __name__ == "__main__":
    main()
