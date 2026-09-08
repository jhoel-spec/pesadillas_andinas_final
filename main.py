"""NEON BREACH: mini shooter raycaster didáctico hecho con Python + Pygame."""

import asyncio
import json
import math
from pathlib import Path
import random
import sys
import traceback

import pygame

from audio import Sounds
from entities import Player, create_enemy, normalized_angle
from map_data import (
    ENEMY_SPAWNS, AVAILABLE_MAPS, get_current_map, set_map, 
    get_enemy_spawns_for_map, update_map_vars
)
from raycasting import cast_all_rays, cast_one_ray
from renderer import (
    ACTIVE_WEAPON_STYLES, draw_background, draw_crosshair,
    draw_damage_vignette, draw_enemies, draw_hud, draw_minimap,
    draw_particles, draw_walls, draw_weapon,
    draw_ceiling_details, draw_world_atmosphere, make_particles,
)
from settings import (
    BLACK, DOOM_AMBER, DOOM_BLACK, DOOM_BLOOD, DOOM_BONE, DOOM_RED,
    DOOM_RUST, DOOM_STEEL, END_SCREEN_REVEAL, FPS, HEIGHT,
    INITIAL_ENEMY_COUNT, MOUSE_SENSITIVITY, POINTS_PER_ENEMY,
    RIFLE_HURT_REACTION_CHANCE, SHOTGUN_BREAK_START, SHOTGUN_CYCLE,
    VICTORY_AFTERMATH, WEAPON_SWITCH_TIME, WIDTH,
)

ROOT = Path(__file__).resolve().parent
RANKING_PATH = ROOT / "ranking.json"


class Game:
    """Coordina entradas, actualización y dibujo. Es el director del juego."""

    def __init__(self):
        pygame.mixer.pre_init(22050, -16, 1, 512)
        pygame.init()
        pygame.display.set_caption("PESADILLAS ANDINAS")
        self.fullscreen = any(
            option in sys.argv for option in ("--pantalla-completa", "--fullscreen")
        )
        desktops = pygame.display.get_desktop_sizes()
        self.desktop_size = desktops[0] if desktops else (WIDTH, HEIGHT)
        self.game_window = None
        self.screen = self._create_display()
        self.frame = pygame.Surface((WIDTH, HEIGHT))
        self.world_frame = pygame.Surface((WIDTH, HEIGHT))
        # Superficie intermedia para el balanceo de cámara. Evita desplazar el
        # mismo frame con Surface.scroll(), que deja bordes stale y mezcla el
        # mundo con overlays cuando se dispara mientras se camina.
        self.camera_frame = pygame.Surface((WIDTH, HEIGHT))
        self.clock = pygame.time.Clock()
        self.font = pygame.font.SysFont("consolas", 23, bold=True)
        self.big_font = pygame.font.SysFont("impact", 84)
        self.medium_font = pygame.font.SysFont("consolas", 32, bold=True)
        self.small_font = pygame.font.SysFont("consolas", 14, bold=True)
        self.sounds = Sounds()
        self.menu_background = self._load_menu_background()
        self.weapon_style = ACTIVE_WEAPON_STYLES[0]
        self.show_hud = "--sin-hud" not in sys.argv
        self.running = True
        self.state = "menu"
        self.selected_map = 0  # Índice del mapa seleccionado
        self.legend_index = 0
        self.paused = False
        self.pause_legend_view = False
        self.time = 0.0
        self.touch_state = {
            "move_id": None,
            "move_center": (WIDTH * 0.18, HEIGHT * 0.80),
            "move_value": (0.0, 0.0),
            "look_id": None,
            "look_last": (WIDTH * 0.82, HEIGHT * 0.46),
            "look_delta": 0.0,
            "shoot_id": None,
            "shoot_pressed": False,
        }
        self.ranking = self._load_ranking()
        self.player_name = ""
        self.reset_game()

    @staticmethod
    def _load_ranking():
        try:
            entries = json.loads(RANKING_PATH.read_text(encoding="utf-8"))
            return sorted(
                ((str(item["name"])[:12], int(item["score"])) for item in entries),
                key=lambda item: item[1], reverse=True,
            )[:10]
        except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError):
            return []

    def _save_score(self):
        name = "".join(char for char in self.player_name.strip()
                       if char.isalnum() or char in " _-")[:12] or "JUGADOR"
        self.ranking = sorted(self.ranking + [(name, self.score)],
                              key=lambda item: item[1], reverse=True)[:10]
        try:
            RANKING_PATH.write_text(
                json.dumps([{"name": name, "score": score}
                            for name, score in self.ranking],
                           ensure_ascii=True, indent=2), encoding="utf-8"
            )
        except OSError:
            pass
        self.player_name = name

    def _create_display(self):
        """Crea borde cero y calcula un ajuste completo sin recortar el juego."""
        size = self.desktop_size if self.fullscreen else (WIDTH, HEIGHT)
        flags = pygame.NOFRAME if self.fullscreen else 0
        screen = pygame.display.set_mode(size, flags)
        try:
            from pygame._sdl2 import Window
            window = Window.from_display_module()
            self.game_window = window
            window.position = (
                (0, 0) if self.fullscreen else
                ((self.desktop_size[0] - WIDTH) // 2,
                 (self.desktop_size[1] - HEIGHT) // 2)
            )
            # Al lanzarse desde una terminal integrada, Windows puede dejar el
            # foco en la consola y enviar allí R/Enter. Elevamos explícitamente
            # la ventana de Pygame para que reciba la entrada desde el inicio.
            window.focus()
        except (ImportError, pygame.error, TypeError):
            self.game_window = None
            pass

        display_width, display_height = screen.get_size()
        scale = min(display_width / WIDTH, display_height / HEIGHT)
        present_width = max(1, int(WIDTH * scale))
        present_height = max(1, int(HEIGHT * scale))
        self.presentation_size = (present_width, present_height)
        self.presentation_offset = (
            (display_width - present_width) // 2,
            (display_height - present_height) // 2,
        )
        self.presentation_surface = pygame.Surface(self.presentation_size)
        return screen

    def toggle_fullscreen(self):
        self.fullscreen = not self.fullscreen
        self.screen = self._create_display()
        gameplay_visible = self.state == "playing"
        pygame.event.set_grab(gameplay_visible)
        pygame.mouse.set_visible(not gameplay_visible)
        pygame.mouse.get_rel()

    def _load_menu_background(self):
        candidates = [
            ROOT / "assets" / "fondo de pantalla del juego .jpeg",
            ROOT / "assets" / "menu_background_doom.png",
        ]
        for image_path in candidates:
            if image_path.exists():
                try:
                    image = pygame.image.load(str(image_path)).convert()
                    return pygame.transform.smoothscale(image, (WIDTH, HEIGHT))
                except (pygame.error, OSError):
                    continue
        return None

    def reset_game(self):
        self.player = Player()
        
        # Configurar el mapa actual
        self.current_map_config = get_current_map()
        self.current_enemy_spawns = get_enemy_spawns_for_map(self.selected_map)
        
        # Establecer la posición del jugador según el mapa seleccionado
        player_start = self.current_map_config["player_start"]
        self.player.x = player_start[0]
        self.player.y = player_start[1]
        self.player.health = 100
        
        self.enemies = []
        self.score = 0
        self.wave = 1
        self.player_name = ""
        self.shot_cooldown = 0.0
        self.muzzle_flash = 0.0
        self.recoil = 0.0
        self.weapon_action_timer = 0.0
        self.weapon_switch_timer = 0.0
        self.weapon_switch_to = self.weapon_style
        self.screen_shake = 0.0
        self.damage_flash = 0.0
        self.hit_confirm_timer = 0.0
        self.camera_bob_x = 0.0
        self.camera_bob_y = 0.0
        self.particles = []
        self.spawn_delay = 0.0
        self.victory_timer = 0.0
        self.victory_delay = 0.0
        self.end_screen_timer = 0.0
        
        self._fill_enemy_wave(self._wave_enemy_count())

    def _enemy_cap_for_map(self):
        if self.current_map_config["id"] == 2:
            return 6
        if self.current_map_config["id"] == 3:
            return 10
        return 8

    def _wave_enemy_count(self):
        cap = self._enemy_cap_for_map()
        return min(len(self.current_enemy_spawns), cap + max(0, self.wave - 1) * 1)

    def _select_enemy_kind(self):
        map_id = self.current_map_config["id"]
        if map_id == 1:
            return random.choices(["demon", "jarjacha"], weights=[3, 2], k=1)[0]
        if map_id == 2:
            return "tio"
        if map_id == 3:
            return random.choices(["demon", "jarjacha", "tio"], weights=[2, 2, 2], k=1)[0]
        return "demon"

    def _fill_enemy_wave(self, amount):
        available = list(self.current_enemy_spawns)
        random.shuffle(available)
        for x, y in available:
            if len(self.enemies_alive()) >= amount:
                break
            if math.hypot(x - self.player.x, y - self.player.y) > 4:
                min_health = 2 + (self.wave - 1) // 3
                max_health = 3 + (self.wave - 1) // 2
                self.enemies.append(
                    create_enemy(x, y, min_health, max_health, kind=self._select_enemy_kind())
                )

    def enemies_alive(self):
        return [enemy for enemy in self.enemies if enemy.alive]

    async def run(self):
        try:
            while self.running:
                dt = min(self.clock.tick(FPS) / 1000.0, 0.04)
                self.time += dt
                self.handle_events()
                self.update(dt)
                self.draw()
                await asyncio.sleep(0)
        except Exception:
            # Si el juego se abre con doble clic, el traceback de Python
            # desaparece junto con la consola. Conservamos el diagnóstico.
            error_path = ROOT / "neon_breach_error.log"
            error_path.write_text(traceback.format_exc(), encoding="utf-8")
            raise
        finally:
            pygame.quit()

    def _touch_input_state(self):
        move_value = self.touch_state["move_value"]
        look_delta = self.touch_state["look_delta"]
        self.touch_state["look_delta"] = 0.0
        return move_value, look_delta

    def _handle_touch_event(self, event):
        x = event.x * WIDTH
        y = event.y * HEIGHT
        touch_id = getattr(event, "touch_id", None)

        if event.type == pygame.FINGERDOWN:
            if self.state == "menu":
                if self._menu_button_rect("JUGAR").collidepoint((x, y)):
                    self.state = "map_select"
                elif self._menu_button_rect("LEYENDAS").collidepoint((x, y)):
                    self.state = "enemy_legend"
                elif self._menu_button_rect("SALIR").collidepoint((x, y)):
                    self.running = False
            elif self.state == "map_select":
                for index, _ in enumerate(AVAILABLE_MAPS):
                    rect = self._map_card_rect(index)
                    if rect.collidepoint((x, y)):
                        self.selected_map = index
                        break
                if self._start_button_rect().collidepoint((x, y)):
                    set_map(self.selected_map)
                    update_map_vars()
                    self.start_game()
            elif self.state == "enemy_legend":
                if self._legend_nav_rect("prev").collidepoint((x, y)):
                    self.legend_index = (self.legend_index - 1) % len(self._legend_entries())
                elif self._legend_nav_rect("next").collidepoint((x, y)):
                    self.legend_index = (self.legend_index + 1) % len(self._legend_entries())
                elif self._legend_nav_rect("back").collidepoint((x, y)):
                    self.state = "menu"
            elif self.state == "playing":
                if self.paused:
                    actions = self._pause_action_rects()
                    if actions["continue"].collidepoint((x, y)):
                        self._toggle_pause()
                    elif actions["legend"].collidepoint((x, y)):
                        self.legend_index = (self.legend_index + 1) % len(self._legend_entries())
                    elif actions["exit"].collidepoint((x, y)):
                        self.paused = False
                        self.state = "menu"
                        pygame.event.set_grab(False)
                        pygame.mouse.set_visible(True)
                    return
                if self._draw_pause_button().collidepoint((x, y)):
                    self._toggle_pause()
                elif x < WIDTH * 0.38 and y > HEIGHT * 0.52:
                    self.touch_state["move_id"] = touch_id
                    self.touch_state["move_center"] = (x, y)
                    self.touch_state["move_value"] = (0.0, 0.0)
                elif x > WIDTH * 0.62 and y > HEIGHT * 0.35:
                    self.touch_state["look_id"] = touch_id
                    self.touch_state["look_last"] = (x, y)
                    self.touch_state["look_delta"] = 0.0
                if x > WIDTH * 0.72 and y > HEIGHT * 0.62:
                    self.touch_state["shoot_id"] = touch_id
                    self.touch_state["shoot_pressed"] = True
                    self.shoot()
            elif x < WIDTH * 0.38 and y > HEIGHT * 0.52:
                self.touch_state["move_id"] = touch_id
                self.touch_state["move_center"] = (x, y)
                self.touch_state["move_value"] = (0.0, 0.0)
            elif x > WIDTH * 0.62 and y > HEIGHT * 0.35:
                self.touch_state["look_id"] = touch_id
                self.touch_state["look_last"] = (x, y)
                self.touch_state["look_delta"] = 0.0
            if x > WIDTH * 0.72 and y > HEIGHT * 0.62:
                self.touch_state["shoot_id"] = touch_id
                self.touch_state["shoot_pressed"] = True
                if self.state == "playing":
                    self.shoot()

        elif event.type == pygame.FINGERUP:
            if touch_id == self.touch_state["move_id"]:
                self.touch_state["move_id"] = None
                self.touch_state["move_value"] = (0.0, 0.0)
            if touch_id == self.touch_state["look_id"]:
                self.touch_state["look_id"] = None
                self.touch_state["look_delta"] = 0.0
            if touch_id == self.touch_state["shoot_id"]:
                self.touch_state["shoot_id"] = None
                self.touch_state["shoot_pressed"] = False

        elif event.type == pygame.FINGERMOTION:
            if touch_id == self.touch_state["move_id"]:
                dx = x - self.touch_state["move_center"][0]
                dy = y - self.touch_state["move_center"][1]
                radius = min(60.0, max(1.0, math.hypot(dx, dy)))
                nx = max(-1.0, min(1.0, dx / radius))
                ny = max(-1.0, min(1.0, dy / radius))
                self.touch_state["move_value"] = (nx, -ny)
            if touch_id == self.touch_state["look_id"]:
                last_x, last_y = self.touch_state["look_last"]
                self.touch_state["look_delta"] += (x - last_x) * 0.0085
                self.touch_state["look_last"] = (x, y)

    def handle_events(self):
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False

            if event.type in (pygame.FINGERDOWN, pygame.FINGERUP, pygame.FINGERMOTION):
                self._handle_touch_event(event)

            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_F11:
                    self.toggle_fullscreen()
                elif event.key == pygame.K_ESCAPE:
                    if self.state == "menu":
                        self.running = False
                    elif self.state == "map_select":
                        self.state = "menu"
                    elif self.state == "enemy_legend":
                        self.state = "menu"
                    elif self.state == "name_entry":
                        self.state = "menu"
                    elif self.state == "playing":
                        self._toggle_pause()
                    else:
                        self.state = "menu"
                        pygame.event.set_grab(False)
                        pygame.mouse.set_visible(True)
                elif self.state == "playing" and self.paused:
                    if self.pause_legend_view:
                        if event.key == pygame.K_LEFT:
                            self.legend_index = (self.legend_index - 1) % len(self._legend_entries())
                        elif event.key == pygame.K_RIGHT:
                            self.legend_index = (self.legend_index + 1) % len(self._legend_entries())
                        elif event.key in (pygame.K_ESCAPE, pygame.K_BACKSPACE, pygame.K_l):
                            self.pause_legend_view = False
                        elif event.key in (pygame.K_RETURN, pygame.K_SPACE, pygame.K_p):
                            self._toggle_pause()
                        continue
                    if event.key in (pygame.K_RETURN, pygame.K_SPACE, pygame.K_p):
                        self._toggle_pause()
                    elif event.key == pygame.K_l:
                        self.pause_legend_view = True
                    elif event.key in (pygame.K_q, pygame.K_m):
                        self.paused = False
                        self.state = "menu"
                        self.pause_legend_view = False
                        pygame.event.set_grab(False)
                        pygame.mouse.set_visible(True)
                elif self.state == "name_entry":
                    if event.key == pygame.K_BACKSPACE:
                        self.player_name = self.player_name[:-1]
                    elif event.key == pygame.K_RETURN:
                        self._save_score()
                        self.state = "lost"
                        self.end_screen_timer = 0.0
                elif self.state == "map_select":
                    if event.key == pygame.K_LEFT:
                        self.selected_map = (self.selected_map - 1) % len(AVAILABLE_MAPS)
                    elif event.key == pygame.K_RIGHT:
                        self.selected_map = (self.selected_map + 1) % len(AVAILABLE_MAPS)
                    elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
                        set_map(self.selected_map)
                        update_map_vars()
                        self.start_game()
                elif self.state == "enemy_legend":
                    if event.key == pygame.K_LEFT:
                        self.legend_index = (self.legend_index - 1) % len(self._legend_entries())
                    elif event.key == pygame.K_RIGHT:
                        self.legend_index = (self.legend_index + 1) % len(self._legend_entries())
                    elif event.key in (pygame.K_ESCAPE, pygame.K_BACKSPACE):
                        self.state = "menu"
                elif event.key in (pygame.K_RETURN, pygame.K_r):
                    if self.state == "menu":
                        self.state = "map_select"
                    elif self.state == "enemy_legend":
                        self.state = "menu"
                    elif self.state not in ("playing", "name_entry"):
                        self.start_game()
                elif event.key == pygame.K_p and self.state == "playing":
                    self._toggle_pause()
                elif event.key == pygame.K_SPACE and self.state == "playing":
                    self.shoot()
                elif event.key == pygame.K_1 and self.state == "playing":
                    self._request_weapon_switch(ACTIVE_WEAPON_STYLES[0])
                elif event.key == pygame.K_2 and self.state == "playing":
                    self._request_weapon_switch(ACTIVE_WEAPON_STYLES[1])

            if event.type == pygame.MOUSEBUTTONDOWN:
                if self.state == "menu":
                    if self._menu_button_rect("JUGAR").collidepoint(event.pos):
                        self.state = "map_select"
                    elif self._menu_button_rect("LEYENDAS").collidepoint(event.pos):
                        self.state = "enemy_legend"
                    elif self._menu_button_rect("SALIR").collidepoint(event.pos):
                        self.running = False
                elif self.state == "map_select":
                    for index, map_config in enumerate(AVAILABLE_MAPS):
                        rect = self._map_card_rect(index)
                        if rect.collidepoint(event.pos):
                            self.selected_map = index
                            set_map(self.selected_map)
                            update_map_vars()
                            self.start_game()
                            break
                    else:
                        if self._start_button_rect().collidepoint(event.pos):
                            set_map(self.selected_map)
                            update_map_vars()
                            self.start_game()
                elif self.state == "enemy_legend":
                    if self._legend_nav_rect("prev").collidepoint(event.pos):
                        self.legend_index = (self.legend_index - 1) % len(self._legend_entries())
                    elif self._legend_nav_rect("next").collidepoint(event.pos):
                        self.legend_index = (self.legend_index + 1) % len(self._legend_entries())
                    elif self._legend_nav_rect("back").collidepoint(event.pos):
                        self.state = "menu"
                elif self.state == "playing":
                    if self.paused:
                        if self.pause_legend_view:
                            if self._legend_nav_rect("prev").collidepoint(event.pos):
                                self.legend_index = (self.legend_index - 1) % len(self._legend_entries())
                            elif self._legend_nav_rect("next").collidepoint(event.pos):
                                self.legend_index = (self.legend_index + 1) % len(self._legend_entries())
                            elif self._legend_nav_rect("back").collidepoint(event.pos):
                                self.pause_legend_view = False
                            return
                        actions = self._pause_action_rects()
                        if actions["continue"].collidepoint(event.pos):
                            self._toggle_pause()
                        elif actions["legend"].collidepoint(event.pos):
                            self.pause_legend_view = True
                        elif actions["exit"].collidepoint(event.pos):
                            self.paused = False
                            self.state = "menu"
                            self.pause_legend_view = False
                            pygame.event.set_grab(False)
                            pygame.mouse.set_visible(True)
                    elif self._draw_pause_button().collidepoint(event.pos):
                        self._toggle_pause()
                    elif event.button == 1:
                        self.shoot()

            if (event.type == pygame.TEXTINPUT and self.state == "name_entry" and
                    len(self.player_name) < 12):
                self.player_name += "".join(
                    char for char in event.text if char.isalnum() or char in " _-"
                )[:12 - len(self.player_name)]

            if event.type == pygame.MOUSEMOTION and self.state == "playing" and not self.paused:
                self.player.angle += event.rel[0] * MOUSE_SENSITIVITY

    def start_game(self):
        self.reset_game()
        self.state = "playing"
        if self.game_window is not None:
            try:
                self.game_window.focus()
            except pygame.error:
                pass
        pygame.event.set_grab(True)
        pygame.mouse.set_visible(False)
        pygame.mouse.get_rel()

    def _request_weapon_switch(self, weapon_style):
        """Baja el arma actual y levanta la nueva antes de permitir disparar."""
        if (weapon_style == self.weapon_style or
                self.weapon_switch_timer > 0 or
                self.weapon_action_timer > 0):
            return
        self.weapon_switch_to = weapon_style
        self.weapon_switch_timer = WEAPON_SWITCH_TIME

    def _legend_entries(self):
        return [
            {
                "key": "karisiri",
                "title": "KARISIRI",
                "description": (
                    "Leyenda urbana boliviana. Se dice que aparece bajo la luz de la\n"
                    "medianoche en caminos apartados y que su mirada puede paralizar\n"
                    "a quien se atreve a cruzarse con él. Es más un presagio que un\n"
                    "enemigo común."
                ),
                "asset": ROOT / "assets" / "enemies" / "demon_idle.png",
            },
            {
                "key": "jarjacha",
                "title": "JARJACHA",
                "description": (
                    "Criatura de la leyenda boliviana que se cuenta entre los pueblos:\n"
                    "pasa por senderos mojados, lleva el olor de la tierra y, cuando\n"
                    "siente miedo, aparece con un paso silencioso y una mirada fija."
                ),
                "asset": ROOT / "assets" / "enemies" / "izquierdo.png",
            },
            {
                "key": "tio",
                "title": "TÍO DE LAS MINAS",
                "description": (
                    "Leyenda de Potosí que se dice habita en galerías profundas y túneles\n"
                    "abandonados. Según la tradición, el espíritu vigila a quienes buscan\n"
                    "tesoros o se adentran sin respeto, y su presencia se siente como\n"
                    "un frío que no viene del aire sino de la tierra misma."
                ),
                "asset": ROOT / "assets" / "enemies" / "parado.png",
            },
        ]

    def _spawn_legend_sprite(self, asset_path, target_size=(180, 180)):
        try:
            sprite = pygame.image.load(str(asset_path)).convert_alpha()
        except (FileNotFoundError, pygame.error):
            sprite = pygame.Surface((128, 128), pygame.SRCALPHA)
            pygame.draw.circle(sprite, DOOM_BONE, (64, 64), 40)
        if sprite.get_size() != target_size:
            sprite = pygame.transform.smoothscale(sprite, target_size)
        return sprite

    def _toggle_pause(self):
        if self.state != "playing":
            return
        self.paused = not self.paused
        if self.paused:
            self.pause_legend_view = False
            pygame.event.set_grab(False)
            pygame.mouse.set_visible(True)
        else:
            self.pause_legend_view = False
            pygame.event.set_grab(True)
            pygame.mouse.set_visible(False)
            pygame.mouse.get_rel()

    def _draw_pause_button(self):
        button_rect = pygame.Rect(20, 18, 150, 42)
        label = self.font.render("PAUSA" if not self.paused else "CONTINUAR", False, DOOM_BONE)
        color = DOOM_AMBER if not self.paused else DOOM_RED
        pygame.draw.rect(self.frame, (25, 18, 18, 200), button_rect, border_radius=12)
        pygame.draw.rect(self.frame, color, button_rect, 2, border_radius=12)
        self.frame.blit(label, label.get_rect(center=button_rect.center))
        return button_rect

    def _pause_action_rects(self):
        return {
            "continue": pygame.Rect(WIDTH // 2 - 170, 260, 340, 52),
            "legend": pygame.Rect(WIDTH // 2 - 170, 330, 340, 52),
            "exit": pygame.Rect(WIDTH // 2 - 170, 400, 340, 52),
        }

    def _draw_pause_legend_detail(self):
        title = self.big_font.render("LEYENDA", False, DOOM_BONE)
        self.frame.blit(title, title.get_rect(center=(WIDTH // 2, 110)))

        entries = self._legend_entries()
        entry = entries[self.legend_index]
        sprite = self._spawn_legend_sprite(entry["asset"], (210, 210))
        portrait_box = pygame.Rect(WIDTH // 2 - 120, 170, 240, 240)
        pygame.draw.rect(self.frame, (22, 18, 18, 200), portrait_box, border_radius=12)
        pygame.draw.rect(self.frame, DOOM_AMBER, portrait_box, 2, border_radius=12)
        self.frame.blit(sprite, sprite.get_rect(center=portrait_box.center))

        name = self.medium_font.render(entry["title"], False, DOOM_AMBER)
        self.frame.blit(name, name.get_rect(center=(WIDTH // 2, 430)))

        for i, line in enumerate(entry["description"].split("\n")):
            text = self.small_font.render(line, False, DOOM_BONE)
            self.frame.blit(text, text.get_rect(center=(WIDTH // 2, 470 + i * 22)))

        prev = self._legend_nav_rect("prev")
        next_ = self._legend_nav_rect("next")
        back = self._legend_nav_rect("back")
        for rect, label in ((prev, "ANTERIOR"), (next_, "SIGUIENTE"), (back, "VOLVER")):
            pygame.draw.rect(self.frame, (22, 18, 18, 200), rect, border_radius=10)
            pygame.draw.rect(self.frame, DOOM_AMBER, rect, 2, border_radius=10)
            rendered = self.font.render(label, False, DOOM_BONE)
            self.frame.blit(rendered, rendered.get_rect(center=rect.center))

    def _weapon_switch_progress(self):
        if self.weapon_switch_timer <= 0:
            return 0.0
        return 1.0 - self.weapon_switch_timer / WEAPON_SWITCH_TIME

    def update(self, dt):
        self.shot_cooldown = max(0.0, self.shot_cooldown - dt)
        self.muzzle_flash = max(0.0, self.muzzle_flash - dt)
        self.recoil = max(0.0, self.recoil - dt * 6)
        previous_weapon_action = self.weapon_action_timer
        self.weapon_action_timer = max(0.0, self.weapon_action_timer - dt)
        if self.weapon_switch_timer > 0:
            self.weapon_switch_timer = max(0.0, self.weapon_switch_timer - dt)
            if self._weapon_switch_progress() >= 0.5:
                self.weapon_style = self.weapon_switch_to
            if self.weapon_switch_timer <= 0:
                self.weapon_style = self.weapon_switch_to
        break_trigger_timer = SHOTGUN_CYCLE - SHOTGUN_BREAK_START
        if (previous_weapon_action > break_trigger_timer >=
                self.weapon_action_timer and
                self.weapon_style == "doom_shotgun" and
                self.state in ("playing", "won")):
            self.sounds.play(self.sounds.shotgun_followup)
        self.screen_shake = max(0.0, self.screen_shake - dt * 30)
        self.damage_flash = max(0.0, self.damage_flash - dt * 1.45)
        self.hit_confirm_timer = max(0.0, self.hit_confirm_timer - dt)

        for particle in self.particles:
            particle.update(dt)
        self.particles = [particle for particle in self.particles if particle.life > 0]

        # Las muertes siguen animándose durante la secuencia previa a la victoria.
        for enemy in self.enemies:
            if not enemy.alive and self.state != "won":
                enemy.update(self.player, dt)
        if self.state != "won":
            self.enemies = [
                enemy for enemy in self.enemies if not enemy.death_finished
            ]

        if self.state in ("won", "lost", "name_entry"):
            self.end_screen_timer += dt

        # Si R se pulsa justo al abrir la ventana, el KEYDOWN puede ocurrir
        # antes de que Pygame tome el foco. El sondeo evita dejar el menú
        # aparentemente congelado en ese caso.
        if self.state == "menu":
            keys = pygame.key.get_pressed()
            if keys[pygame.K_r] or keys[pygame.K_RETURN] or keys[pygame.K_SPACE]:
                self.start_game()
            return

        if self.state != "playing":
            return
        if self.paused:
            return

        move_value, look_delta = self._touch_input_state()
        self.player.update(dt, touch_move=move_value if any(move_value) else None,
                           touch_look_delta=look_delta)
        # La cámara acompaña los pasos y vuelve suavemente al centro al detenerse.
        if self.player.moving:
            target_bob_x = math.sin(self.player.walk_time) * 4.2
            target_bob_y = math.sin(self.player.walk_time * 2) * 6.2
        else:
            target_bob_x = 0.0
            target_bob_y = 0.0
        smoothing = min(1.0, dt * 13)
        self.camera_bob_x += (target_bob_x - self.camera_bob_x) * smoothing
        self.camera_bob_y += (target_bob_y - self.camera_bob_y) * smoothing

        for enemy in self.enemies_alive():
            if enemy.update(self.player, dt):
                self.player.health -= 8
                self.damage_flash = min(1.0, self.damage_flash + 0.92)
                self.screen_shake = max(self.screen_shake, 15)

        if self.player.health <= 0:
            self.state = "name_entry"
            self.end_screen_timer = 0.0
            pygame.event.set_grab(False)
            pygame.mouse.set_visible(True)
            return

        # Verificar condiciones de perder según el mapa
        if self.current_map_config["id"] == 2:  # Minas de Potosí - Defender la salida
            mine_exit = self.current_map_config.get("exit")
            for enemy in self.enemies_alive():
                if mine_exit and math.hypot(enemy.x - mine_exit[0], 
                                           enemy.y - mine_exit[1]) < 1.0:
                    # Un enemigo llegó a la salida
                    self.state = "name_entry"
                    self.end_screen_timer = 0.0
                    pygame.event.set_grab(False)
                    pygame.mouse.set_visible(True)
                    return

        elif self.current_map_config["id"] == 3:  # Defiende al Cristo - Defender el centro
            cristo_center = self.current_map_config.get("center")
            for enemy in self.enemies_alive():
                if cristo_center and math.hypot(enemy.x - cristo_center[0], 
                                               enemy.y - cristo_center[1]) < 1.5:
                    # Un enemigo llegó al centro donde está el Cristo
                    self.state = "name_entry"
                    self.end_screen_timer = 0.0
                    pygame.event.set_grab(False)
                    pygame.mouse.set_visible(True)
                    return

        if not self.enemies:
            self.wave += 1
            self._fill_enemy_wave(self._wave_enemy_count())

    def _spawn_one_enemy(self):
        occupied = {
            (int(enemy.x), int(enemy.y)) for enemy in self.enemies_alive()
        }
        choices = [
            spot for spot in self.current_enemy_spawns
            if (int(spot[0]), int(spot[1])) not in occupied
            and math.hypot(spot[0] - self.player.x, spot[1] - self.player.y) > 5
        ]
        if choices:
            self.enemies.append(
                create_enemy(*random.choice(choices), kind=self._select_enemy_kind())
            )

    def shoot(self):
        if self.paused or self.state != "playing":
            return
        if self.shot_cooldown > 0 or self.weapon_switch_timer > 0:
            return
        shotgun_fired = self.weapon_style == "doom_shotgun"
        self.shot_cooldown = SHOTGUN_CYCLE if shotgun_fired else 0.24
        self.weapon_action_timer = SHOTGUN_CYCLE if shotgun_fired else 0.0
        self.muzzle_flash = 0.18 if shotgun_fired else 0.10
        self.recoil = 1.0
        self.screen_shake = 18 if shotgun_fired else 4
        self.sounds.play(
            self.sounds.shotgun if shotgun_fired else self.sounds.shot,
            maxtime=int(SHOTGUN_CYCLE * 1000) if shotgun_fired else 0,
        )
        self.particles += make_particles(
            WIDTH // 2, HEIGHT // 2 + 80, DOOM_AMBER,
            28 if shotgun_fired else 9, 440 if shotgun_fired else 170,
        )
        if shotgun_fired:
            self.particles += make_particles(
                WIDTH // 2, HEIGHT // 2 + 65, DOOM_STEEL, 18, 330
            )

        # La pared central limita el alcance: no se dispara a través de ella.
        wall_distance = cast_one_ray(
            self.player.x, self.player.y, self.player.angle
        )[0]
        target = None
        best_aim = 999.0

        for enemy in self.enemies_alive():
            dx, dy = enemy.x - self.player.x, enemy.y - self.player.y
            distance = math.hypot(dx, dy)
            angle_to_enemy = math.atan2(dy, dx)
            aim_error = abs(normalized_angle(angle_to_enemy - self.player.angle))
            visible_width = math.atan2(0.58 if shotgun_fired else 0.42, distance)
            if distance < wall_distance + 0.25 and aim_error < visible_width:
                if aim_error < best_aim:
                    target, best_aim = enemy, aim_error

        if target:
            play_hurt_pose = (
                shotgun_fired
                or random.random() < RIFLE_HURT_REACTION_CHANCE
            )
            killed = target.take_damage(
                target.health if shotgun_fired else 1,
                play_hurt_pose=play_hurt_pose,
            )
            self.particles += make_particles(
                WIDTH // 2, HEIGHT // 2,
                DOOM_RUST if shotgun_fired else DOOM_BLOOD,
                52 if shotgun_fired else 10,
                520 if shotgun_fired else 190,
            )
            self.screen_shake = max(
                self.screen_shake, 22 if shotgun_fired else 5
            )
            self.hit_confirm_timer = 0.22 if killed else 0.14
            if killed:
                self.sounds.play(self.sounds.enemy_death)
                self.screen_shake = max(
                    self.screen_shake, 16 if shotgun_fired else 8
                )
                self.particles += make_particles(
                    WIDTH // 2, HEIGHT // 2, DOOM_BLOOD, 20, 410
                )
                self.particles += make_particles(
                    WIDTH // 2, HEIGHT // 2, DOOM_BONE, 9, 260
                )
                self.score += POINTS_PER_ENEMY + (self.wave - 1) * 25
            else:
                self.sounds.play(self.sounds.hit)

    def _begin_victory_sequence(self, final_enemy):
        """Derriba a toda la horda y deja leer la caída antes del triunfo."""
        death_sound_time = (
            self.sounds.enemy_death.get_length()
            if self.sounds.enemy_death is not None else 0.0
        )
        remaining = sorted(
            self.enemies_alive(),
            key=lambda enemy: enemy.distance_to(self.player),
        )
        last_death_delay = 0.0
        for index, enemy in enumerate(remaining):
            death_delay = 0.08 + index * 0.07
            enemy.trigger_death(death_delay)
            last_death_delay = death_delay
        self.victory_timer = 0.0
        self.victory_delay = max(
            final_enemy.DEATH_ANIMATION_TIME + 0.34,
            last_death_delay + final_enemy.DEATH_ANIMATION_TIME + 0.34,
            death_sound_time,
            self.weapon_action_timer,
        ) + VICTORY_AFTERMATH
        self.state = "victory_pending"
        self.screen_shake = max(self.screen_shake, 18)

    def _finish_victory(self):
        self.state = "won"
        self.end_screen_timer = 0.0
        for enemy in self.enemies:
            if not enemy.alive:
                # Todos llegan al fotograma final y quedan como montones
                # visibles bajo el mensaje de victoria.
                enemy.death_timer = enemy.DEATH_ANIMATION_TIME + 0.02
        pygame.event.set_grab(False)
        pygame.mouse.set_visible(True)
        self.screen_shake = max(self.screen_shake, 12)
        self.particles += make_particles(
            WIDTH // 2, HEIGHT // 2, DOOM_AMBER, 72, 520
        )
        self.particles += make_particles(
            WIDTH // 2, HEIGHT // 2, DOOM_BONE, 34, 360
        )
        self.sounds.play(self.sounds.win)

    def draw(self):
        if self.state == "menu":
            self.draw_menu()
        elif self.state == "map_select":
            self.draw_map_select()
        elif self.state == "enemy_legend":
            self.draw_enemy_legend()
        elif self.state == "playing":
            self.draw_playing()
        elif self.state in ("won", "lost", "name_entry"):
            self.draw_playing()
            self.draw_end_screen()
        shake_x = 0
        shake_y = 0
        if self.state != "menu" and self.state != "map_select":
            shake_x = random.randint(-int(self.screen_shake),
                                     int(self.screen_shake))
            shake_y = random.randint(-int(self.screen_shake),
                                     int(self.screen_shake))
        self._present_frame(shake_x, shake_y)
        pygame.display.flip()

    def _present_frame(self, shake_x=0, shake_y=0):
        """Escala el fotograma completo; HUD, arma y radar nunca se separan."""
        self.screen.fill(BLACK)
        if self.presentation_size == (WIDTH, HEIGHT):
            presented = self.frame
        else:
            pygame.transform.smoothscale(
                self.frame, self.presentation_size, self.presentation_surface
            )
            presented = self.presentation_surface
        scale = self.presentation_size[0] / WIDTH
        self.screen.blit(
            presented,
            (self.presentation_offset[0] + int(shake_x * scale),
             self.presentation_offset[1] + int(shake_y * scale)),
        )

    def draw_playing(self):
        # Mundo y HUD se componen por separado: la cámara se mueve, la interfaz no.
        rays, depth_buffer = cast_all_rays(self.player)
        draw_background(
            self.world_frame, self.time, self.player, depth_buffer
        )
        # Los elementos del techo existen detrás de los muros; el orden evita
        # que una lámpara o panel atraviese visualmente una pared cercana.
        draw_ceiling_details(
            self.world_frame, self.player, self.time, depth_buffer
        )
        draw_walls(self.world_frame, rays, self.time)
        draw_enemies(self.world_frame, self.enemies, self.player, depth_buffer)
        draw_world_atmosphere(
            self.world_frame, self.player, depth_buffer, self.time
        )

        self.frame.blit(self.world_frame, (0, 0))
        camera_x = int(self.camera_bob_x)
        camera_y = int(self.camera_bob_y)
        if camera_x or camera_y:
            # Se copia desde una superficie distinta para que los píxeles
            # expuestos en los bordes queden siempre definidos.
            self.camera_frame.fill(BLACK)
            self.camera_frame.blit(self.frame, (camera_x, camera_y))
            self.frame.blit(self.camera_frame, (0, 0))

        # El fogonazo ilumina brevemente todo el mundo, no solamente el cañón.
        if self.muzzle_flash > 0:
            strength = min(1.0, self.muzzle_flash / 0.10)
            flash_light = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
            flash_light.fill((*DOOM_AMBER, int(36 * strength)))
            self.frame.blit(flash_light, (0, 0))

        draw_particles(self.frame, self.particles)
        draw_weapon(
            self.frame, self.player, self.recoil, self.muzzle_flash,
            self.weapon_style, full_view=not self.show_hud,
            action_timer=self.weapon_action_timer,
            switch_progress=self._weapon_switch_progress(),
        )
        draw_crosshair(self.frame, self.recoil, self.hit_confirm_timer)
        if self.show_hud:
            draw_hud(
                self.frame, self.player, self.score, self.weapon_style,
                self.font, self.small_font, self.damage_flash, self.wave,
            )
        draw_minimap(self.frame, self.player, self.enemies)

        draw_damage_vignette(self.frame, self.damage_flash)
        if self.state == "playing":
            self._draw_pause_button()
            if self.paused:
                overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
                overlay.fill((8, 8, 12, 180))
                self.frame.blit(overlay, (0, 0))
                if self.pause_legend_view:
                    self._draw_pause_legend_detail()
                else:
                    pause_title = self.big_font.render("PAUSA", False, DOOM_BONE)
                    self.frame.blit(pause_title, pause_title.get_rect(center=(WIDTH // 2, 150)))

                    legend = self._legend_entries()[self.legend_index]
                    entry_desc = legend["description"].split("\n")
                    for i, line in enumerate(entry_desc):
                        text = self.small_font.render(line, False, DOOM_BONE)
                        self.frame.blit(text, text.get_rect(center=(WIDTH // 2, 200 + i * 24)))

                    actions = self._pause_action_rects()
                    for key, rect in actions.items():
                        label = {
                            "continue": "CONTINUAR",
                            "legend": "VER LEYENDA",
                            "exit": "SALIR DEL NIVEL",
                        }[key]
                        pygame.draw.rect(self.frame, (22, 18, 18, 220), rect, border_radius=12)
                        pygame.draw.rect(self.frame, DOOM_AMBER, rect, 2, border_radius=12)
                        rendered = self.font.render(label, False, DOOM_BONE)
                        self.frame.blit(rendered, rendered.get_rect(center=rect.center))

                    hint = self.font.render("PRESIONE P / ENTER / CLICK PARA CONTINUAR", False, DOOM_STEEL)
                    self.frame.blit(hint, hint.get_rect(center=(WIDTH // 2, 470)))
        self._draw_touch_controls()
        # Sin rejilla CRT sobre el mundo: YouTube conserva mejor el detalle fino.

    def _draw_touch_controls(self):
        if self.state != "playing" or self.paused:
            return
        joystick_x, joystick_y = self.touch_state["move_center"]
        knob_x = joystick_x + self.touch_state["move_value"][0] * 28
        knob_y = joystick_y + self.touch_state["move_value"][1] * 28
        pygame.draw.circle(self.frame, (255, 255, 255, 80), (int(joystick_x), int(joystick_y)), 50, 2)
        pygame.draw.circle(self.frame, (255, 255, 255, 120), (int(knob_x), int(knob_y)), 18)

        button_center = (int(WIDTH * 0.86), int(HEIGHT * 0.76))
        shoot_color = (220, 40, 40, 180) if self.touch_state["shoot_pressed"] else (120, 30, 30, 180)
        pygame.draw.circle(self.frame, shoot_color, button_center, 38)
        pygame.draw.circle(self.frame, (255, 255, 255, 130), button_center, 28, 2)
        pygame.draw.line(self.frame, (255, 255, 255, 180), (button_center[0] - 10, button_center[1]), (button_center[0] + 10, button_center[1]), 3)
        pygame.draw.line(self.frame, (255, 255, 255, 180), (button_center[0], button_center[1] - 10), (button_center[0], button_center[1] + 10), 3)

    def _menu_button_rect(self, label):
        labels = {
            "JUGAR": pygame.Rect(WIDTH // 2 - 150, 320, 300, 60),
            "LEYENDAS": pygame.Rect(WIDTH // 2 - 150, 400, 300, 60),
            "SALIR": pygame.Rect(WIDTH // 2 - 150, 480, 300, 60),
        }
        return labels.get(label, pygame.Rect(0, 0, 0, 0))

    def _map_card_rect(self, index):
        y_pos = 200 + index * 120
        return pygame.Rect(WIDTH // 2 - 200, y_pos - 20, 400, 90)

    def _start_button_rect(self):
        return pygame.Rect(WIDTH // 2 - 120, 620, 240, 50)

    def _legend_nav_rect(self, action):
        if action == "prev":
            return pygame.Rect(120, 520, 170, 50)
        if action == "next":
            return pygame.Rect(WIDTH - 290, 520, 170, 50)
        if action == "back":
            return pygame.Rect(WIDTH // 2 - 120, 640, 240, 50)
        return pygame.Rect(0, 0, 0, 0)

    def draw_menu(self):
        if self.menu_background:
            self.frame.blit(self.menu_background, (0, 0))
        else:
            self.frame.fill(DOOM_BLACK)

        title = self.big_font.render("PESADILLAS ANDINAS", False, DOOM_BONE)
        shadow = self.big_font.render("PESADILLAS ANDINAS", False, DOOM_BLOOD)
        title_rect = title.get_rect(center=(WIDTH // 2, 105))
        self.frame.blit(shadow, title_rect.move(6, 7))
        self.frame.blit(title, title_rect)
        pygame.draw.line(
            self.frame, DOOM_RUST,
            (title_rect.left + 18, title_rect.bottom + 4),
            (title_rect.right - 18, title_rect.bottom + 4), 4,
        )

        for label in ("JUGAR", "LEYENDAS", "SALIR"):
            rect = self._menu_button_rect(label)
            pygame.draw.rect(self.frame, (28, 22, 20, 220), rect, border_radius=12)
            pygame.draw.rect(self.frame, DOOM_AMBER, rect, 2, border_radius=12)
            rendered = self.font.render(label, False, DOOM_BONE)
            self.frame.blit(rendered, rendered.get_rect(center=rect.center))

        prompt = self.medium_font.render(
            "CLICK O ENTER PARA JUGAR · MOUSE/TACTO PARA NAVEGAR", False, DOOM_STEEL
        )
        if int(self.time * 2) % 2 == 0:
            self.frame.blit(
                prompt, prompt.get_rect(center=(WIDTH // 2, 630))
            )

    def draw_map_select(self):
        if self.menu_background:
            self.frame.blit(self.menu_background, (0, 0))
        else:
            self.frame.fill(DOOM_BLACK)

        title = self.big_font.render("SELECCIONA UN MAPA", False, DOOM_BONE)
        shadow = self.big_font.render("SELECCIONA UN MAPA", False, DOOM_BLOOD)
        title_rect = title.get_rect(center=(WIDTH // 2, 80))
        self.frame.blit(shadow, title_rect.move(6, 7))
        self.frame.blit(title, title_rect)
        pygame.draw.line(
            self.frame, DOOM_RUST,
            (title_rect.left + 18, title_rect.bottom + 4),
            (title_rect.right - 18, title_rect.bottom + 4), 4,
        )

        for index, map_config in enumerate(AVAILABLE_MAPS):
            rect = self._map_card_rect(index)
            is_selected = index == self.selected_map
            color = DOOM_AMBER if is_selected else DOOM_STEEL
            pygame.draw.rect(self.frame, (20, 18, 18, 200), rect, border_radius=10)
            pygame.draw.rect(self.frame, color, rect, 2 if is_selected else 1, border_radius=10)
            name = self.medium_font.render(f"{index + 1}. {map_config['name']}", False, color)
            self.frame.blit(name, name.get_rect(center=(WIDTH // 2, rect.centery - 10)))
            desc = self.small_font.render(map_config['description'], False, DOOM_BONE)
            self.frame.blit(desc, desc.get_rect(center=(WIDTH // 2, rect.centery + 22)))

        start_button = self._start_button_rect()
        pygame.draw.rect(self.frame, DOOM_AMBER, start_button, border_radius=10)
        start_label = self.font.render("INICIAR", False, DOOM_BLACK)
        self.frame.blit(start_label, start_label.get_rect(center=start_button.center))

        instructions = self.font.render(
            "CLICK EN EL MAPA O FLECHAS ← → · ENTER O CLICK EN INICIAR · ESC PARA VOLVER", False, DOOM_STEEL
        )
        self.frame.blit(
            instructions, instructions.get_rect(center=(WIDTH // 2, 690))
        )

    def draw_enemy_legend(self):
        if self.menu_background:
            self.frame.blit(self.menu_background, (0, 0))
        else:
            self.frame.fill(DOOM_BLACK)

        title = self.big_font.render("LEYENDAS URBANAS", False, DOOM_BONE)
        shadow = self.big_font.render("LEYENDAS URBANAS", False, DOOM_BLOOD)
        title_rect = title.get_rect(center=(WIDTH // 2, 70))
        self.frame.blit(shadow, title_rect.move(6, 7))
        self.frame.blit(title, title_rect)

        entries = self._legend_entries()
        entry = entries[self.legend_index]
        sprite = self._spawn_legend_sprite(entry["asset"], (200, 200))
        portrait_box = pygame.Rect(WIDTH // 2 - 110, 150, 220, 220)
        pygame.draw.rect(self.frame, (22, 18, 18, 200), portrait_box, border_radius=12)
        pygame.draw.rect(self.frame, DOOM_AMBER, portrait_box, 2, border_radius=12)
        self.frame.blit(sprite, sprite.get_rect(center=portrait_box.center))

        title_text = self.medium_font.render(entry["title"], False, DOOM_AMBER)
        self.frame.blit(title_text, title_text.get_rect(center=(WIDTH // 2, 390)))

        desc_lines = entry["description"].split("\n")
        for i, line in enumerate(desc_lines):
            text = self.small_font.render(line, False, DOOM_BONE)
            self.frame.blit(text, text.get_rect(center=(WIDTH // 2, 440 + i * 26)))

        prev = self._legend_nav_rect("prev")
        next_ = self._legend_nav_rect("next")
        back = self._legend_nav_rect("back")
        for rect, label in ((prev, "ANTERIOR"), (next_, "SIGUIENTE"), (back, "VOLVER")):
            pygame.draw.rect(self.frame, (22, 18, 18, 200), rect, border_radius=10)
            pygame.draw.rect(self.frame, DOOM_AMBER, rect, 2, border_radius=10)
            rendered = self.font.render(label, False, DOOM_BONE)
            self.frame.blit(rendered, rendered.get_rect(center=rect.center))

    def draw_end_screen(self):
        reveal = min(1.0, self.end_screen_timer / END_SCREEN_REVEAL)
        reveal = reveal * reveal * (3.0 - 2.0 * reveal)
        alpha = max(1, int(255 * reveal))
        won = self.state == "won"

        veil = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        veil.fill((8, 4, 3, int((165 if won else 215) * reveal)))
        self.frame.blit(veil, (0, 0))

        if won:
            flash = max(0.0, 1.0 - self.end_screen_timer / 0.55)
            victory_light = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
            victory_light.fill((*DOOM_AMBER, int(72 * flash)))
            self.frame.blit(victory_light, (0, 0))

        heading = "BRECHA SELLADA" if won else "SISTEMA CAÍDO"
        color = DOOM_AMBER if won else DOOM_RED
        text = self.big_font.render(heading, False, color)
        title_scale = 1.0 + (1.0 - reveal) * 0.16
        text = pygame.transform.scale(
            text,
            (max(1, int(text.get_width() * title_scale)),
             max(1, int(text.get_height() * title_scale))),
        )
        text.set_alpha(alpha)
        title_y = int(220 - 34 * (1.0 - reveal))
        shadow = text.copy()
        shadow.fill((20, 0, 0, alpha), special_flags=pygame.BLEND_RGBA_MULT)
        self.frame.blit(
            shadow, shadow.get_rect(center=(WIDTH // 2 + 6, title_y + 7))
        )
        self.frame.blit(
            text, text.get_rect(center=(WIDTH // 2, title_y))
        )

        line_half_width = int(390 * reveal)
        pygame.draw.line(
            self.frame, DOOM_RUST,
            (WIDTH // 2 - line_half_width, 268),
            (WIDTH // 2 + line_half_width, 268), 4,
        )
        outcome = self.font.render(
            "TODOS LOS DEMONIOS HAN CAÍDO"
            if won else "LA BRECHA SIGUE ABIERTA",
            False, DOOM_BONE,
        )
        outcome.set_alpha(alpha)
        self.frame.blit(
            outcome, outcome.get_rect(center=(WIDTH // 2, 300))
        )

        detail = self.font.render(
            f"PUNTUACIÓN FINAL: {self.score}", False, DOOM_BONE
        )
        detail.set_alpha(alpha)
        self.frame.blit(
            detail, detail.get_rect(center=(WIDTH // 2, 334))
        )
        if self.state == "name_entry":
            name_prompt = self.font.render(
                "ESCRIBE TU NOMBRE Y PULSA ENTER", False, DOOM_AMBER
            )
            self.frame.blit(name_prompt, name_prompt.get_rect(center=(WIDTH // 2, 390)))
            name_text = self.font.render(
                f"> {self.player_name}_", False, DOOM_BONE
            )
            self.frame.blit(name_text, name_text.get_rect(center=(WIDTH // 2, 425)))
        else:
            ranking_top = self.font.render("CLASIFICACION", False, DOOM_AMBER)
            self.frame.blit(ranking_top, ranking_top.get_rect(center=(WIDTH // 2, 408)))
            for index, (name, score) in enumerate(self.ranking[:5], 1):
                ranking_line = self.small_font.render(
                    f"{index:02d}  {name:<12} {score:06d}", False, DOOM_BONE
                )
                self.frame.blit(ranking_line,
                                ranking_line.get_rect(center=(WIDTH // 2, 438 + index * 22)))
        prompt = self.font.render(
            "PULSA R O ENTER PARA REINICIAR · ESC PARA SALIR"
            if self.state != "name_entry" else "ENTER GUARDA · ESC CANCELA",
            False, DOOM_STEEL,
        )
        prompt_reveal = max(
            0.0, min(1.0, (self.end_screen_timer - 0.38) / 0.42)
        )
        prompt.set_alpha(int(255 * prompt_reveal))
        self.frame.blit(prompt, prompt.get_rect(center=(WIDTH // 2, 570)))


if __name__ == "__main__":
    asyncio.run(Game().run())
