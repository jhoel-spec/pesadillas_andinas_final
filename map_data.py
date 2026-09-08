"""Múltiples mapas para el juego: Calles de Sacaba, Minas de Potosí, Defiende al Cristo."""

import math
import random

# ============================================================================
# MAPA 1: LAS CALLES DE SACABA - Avenidas, calles estrechas y callejones
# ============================================================================
def _build_city_map(width=34, height=26):
    """Construye una cuadrícula urbana con avenidas y callejones sin salida."""
    cells = [["1"] * width for _ in range(height)]

    def carve_horizontal(grid_y, start_x=1, end_x=None):
        for grid_x in range(start_x, end_x or width - 1):
            cells[grid_y][grid_x] = "."

    def carve_vertical(grid_x, start_y=1, end_y=None):
        for grid_y in range(start_y, end_y or height - 1):
            cells[grid_y][grid_x] = "."

    # Avenidas de dos celdas y calles longitudinales mas estrechas.
    for grid_y in (3, 4, 12, 13, 21):
        carve_horizontal(grid_y)
    for grid_x in (5, 16, 27):
        carve_vertical(grid_x)

    # Callejones que terminan contra edificios y conectan con una sola calle.
    for grid_y in range(6, 12):
        cells[grid_y][10] = "."
    for grid_x in range(6, 12):
        cells[8][grid_x] = "."
    for grid_y in range(14, 21):
        cells[grid_y][23] = "."
    for grid_x in range(18, 24):
        cells[18][grid_x] = "."
    for grid_y in range(22, 25):
        cells[grid_y][13] = "."

    return tuple("".join(row) for row in cells)


MAP_1_SACABA = _build_city_map()
PLAYER_START_1 = (3.5, 3.5)

# ============================================================================
# MAPA 2: LAS MINAS DE POTOSÍ - Laberinto de galerías conectadas
# ============================================================================
def _build_mine_map(width=34, height=21):
    """Construye galerías de una celda con un recorrido siempre transitable."""
    cells = [["1"] * width for _ in range(height)]
    stack = [(1, 1)]
    cells[1][1] = "."
    generator = random.Random(20260827)
    while stack:
        grid_x, grid_y = stack[-1]
        neighbors = [
            (grid_x + offset_x, grid_y + offset_y)
            for offset_x, offset_y in ((2, 0), (-2, 0), (0, 2), (0, -2))
            if 1 <= grid_x + offset_x < width - 1
            and 1 <= grid_y + offset_y < height - 1
            and cells[grid_y + offset_y][grid_x + offset_x] == "1"
        ]
        if not neighbors:
            stack.pop()
            continue
        next_x, next_y = generator.choice(neighbors)
        cells[grid_y + (next_y - grid_y) // 2][grid_x + (next_x - grid_x) // 2] = "."
        cells[next_y][next_x] = "."
        stack.append((next_x, next_y))

    cells[1][2] = "."
    cells[2][2] = "."
    cells[height - 2][width - 2] = "S"
    return tuple("".join(row) for row in cells)


MAP_2_MINES = _build_mine_map()

PLAYER_START_2 = (2.5, 2.5)
MINE_EXIT = (32.5, 19.5)  # Galería de salida en la esquina inferior derecha

# ============================================================================
# MAPA 3: DEFIENDE AL CRISTO - Arena amplia con centro protegido
# ============================================================================
def _build_cristo_map(width=42, height=30):
    """Crea una arena grande y deja un pedestal central de 2x2 reservado."""
    cells = [["1"] * width for _ in range(height)]
    for grid_y in range(1, height - 1):
        for grid_x in range(1, width - 1):
            cells[grid_y][grid_x] = "."

    center_x = width // 2 - 1
    center_y = height // 2 - 1
    for grid_y in (center_y, center_y + 1):
        for grid_x in (center_x, center_x + 1):
            cells[grid_y][grid_x] = "2"
    return tuple("".join(row) for row in cells)


MAP_3_CRISTO = _build_cristo_map()
PLAYER_START_3 = (3.5, 3.5)
CRISTO_CENTER = (20.5, 14.5)  # Centro del pedestal 2x2

# ============================================================================
# SELECTOR DE MAPA Y CONFIGURACIÓN
# ============================================================================

# Mapas disponibles
AVAILABLE_MAPS = [
    {
        "id": 1,
        "name": "Las calles oscuras de Bolivia",
        "map": MAP_1_SACABA,
        "player_start": PLAYER_START_1,
        "description": "Calles y callejones de una ciudad",
        "win_condition": "defeat_all",  # Ganar eliminando todos los enemigos
    },
    {
        "id": 2,
        "name": "Las minas de Potosí",
        "map": MAP_2_MINES,
        "player_start": PLAYER_START_2,
        "description": "Laberinto minero con salida en la esquina",
        "win_condition": "defend_exit",  # Ganar protegiendo la salida
        "exit": MINE_EXIT,
    },
    {
        "id": 3,
        "name": "Defiende al Cristo",
        "map": MAP_3_CRISTO,
        "player_start": PLAYER_START_3,
        "description": "Mapa abierto con imagen central",
        "win_condition": "defend_center",  # Ganar protegiendo el centro
        "center": CRISTO_CENTER,
    },
]

# Mapa actual (se cambia según la selección)
CURRENT_MAP_INDEX = 0

def get_current_map():
    """Obtiene la configuración del mapa actual."""
    return AVAILABLE_MAPS[CURRENT_MAP_INDEX]

def set_map(map_index):
    """Selecciona el mapa a jugar."""
    global CURRENT_MAP_INDEX
    if 0 <= map_index < len(AVAILABLE_MAPS):
        CURRENT_MAP_INDEX = map_index

# Variables que usan el mapa actual
MAP = get_current_map()["map"]
MAP_WIDTH = len(MAP[0])
MAP_HEIGHT = len(MAP)
PLAYER_START = get_current_map()["player_start"]


def update_map_vars():
    """Actualiza las variables globales cuando cambia el mapa."""
    global MAP, MAP_WIDTH, MAP_HEIGHT, PLAYER_START
    map_config = get_current_map()
    MAP = map_config["map"]
    MAP_WIDTH = len(MAP[0])
    MAP_HEIGHT = len(MAP)
    PLAYER_START = map_config["player_start"]


def _build_enemy_spawns(map_data, player_start_pos, amount=24,
                        forbidden_centers=()):
    """Selecciona celdas libres alejadas del inicio y repartidas por el mapa."""
    candidates = []
    for grid_y, row in enumerate(map_data):
        for grid_x, tile in enumerate(row):
            if tile != ".":
                continue
            position = (grid_x + 0.5, grid_y + 0.5)
            if any(math.hypot(position[0] - center[0],
                              position[1] - center[1]) < radius
                       for center, radius in forbidden_centers):
                continue
            distance = math.hypot(position[0] - player_start_pos[0],
                                  position[1] - player_start_pos[1])
            if distance >= 3.0:
                candidates.append((distance, grid_x, grid_y, position))

    if not candidates:
        raise ValueError("No hay suficientes celdas libres para los spawns")

    # Muestreo de máxima distancia
    candidates.sort(key=lambda item: (-item[0], item[2], item[1]))
    selected = [candidates[0][3]]
    remaining = candidates[1:]
    while remaining and len(selected) < amount:
        best_index = max(
            range(len(remaining)),
            key=lambda index: (
                min(math.hypot(remaining[index][3][0] - other[0],
                                remaining[index][3][1] - other[1])
                    for other in selected),
                remaining[index][0],
                -remaining[index][2],
                -remaining[index][1],
            ),
        )
        candidate = remaining.pop(best_index)
        if min(math.hypot(candidate[3][0] - other[0], candidate[3][1] - other[1])
               for other in selected) >= 2.0:
            selected.append(candidate[3])

    if len(selected) < amount:
        # Si no hay suficientes, devolvemos los que encontramos
        return tuple(selected)
    return tuple(selected)


# Calcular spawns para cada mapa
ENEMY_SPAWNS_1 = _build_enemy_spawns(MAP_1_SACABA, PLAYER_START_1)
ENEMY_SPAWNS_2 = _build_enemy_spawns(MAP_2_MINES, PLAYER_START_2, amount=12)
ENEMY_SPAWNS_3 = _build_enemy_spawns(
    MAP_3_CRISTO, PLAYER_START_3, forbidden_centers=((CRISTO_CENTER, 4.0),)
)

ENEMY_SPAWNS = ENEMY_SPAWNS_1  # Se actualiza cuando cambia el mapa


def get_enemy_spawns_for_map(map_index):
    """Obtiene los spawns de enemigos para un mapa específico."""
    spawns_list = [ENEMY_SPAWNS_1, ENEMY_SPAWNS_2, ENEMY_SPAWNS_3]
    return spawns_list[map_index]


def tile_at(x, y, map_data=None):
    """Devuelve el carácter de la casilla (x, y); fuera del mapa es pared."""
    if map_data is None:
        map_data = MAP
    
    width = len(map_data[0])
    height = len(map_data)
    grid_x, grid_y = int(x), int(y)
    if 0 <= grid_x < width and 0 <= grid_y < height:
        return map_data[grid_y][grid_x]
    return "1"


def is_wall(x, y, map_data=None):
    """True cuando la posición está ocupada por una pared."""
    tile = tile_at(x, y, map_data)
    return tile not in (".", "S")  # S es la salida en el mapa 2
