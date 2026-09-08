# Cambios Realizados - Sistema de 3 Mapas

## Resumen
Se ha implementado un sistema de selección de 3 mapas diferentes con estructuras únicas y condiciones de pérdida específicas para cada uno.

## Nuevos Mapas

### 1. **Las Calles de Sacaba**
- **Descripción**: Calles y callejones de una ciudad
- **Estructura**: Mapa urbano con pasillos y calles que forman un patrón de ciudad
- **Condición de Perder**: El jugador pierde si su salud llega a 0 (elimina el enemigo)
- **Objetivo**: Eliminar todos los enemigos en cada oleada
- **Enemigos**: Aparecen en calles y pasillos aleatorios

### 2. **Las Minas de Potosí**
- **Descripción**: Laberinto minero con salida en la esquina
- **Estructura**: Laberinto complejo que simula un sistema de túneles subterráneos
- **Condición de Perder**: El jugador pierde si un enemigo llega a la salida (esquina derecha inferior)
- **Objetivo**: Proteger la salida impidiendo que enemigos la alcancen
- **Enemigos**: Aparecen en los pasillos del laberinto

### 3. **Defiende al Cristo**
- **Descripción**: Mapa abierto con imagen/pared central
- **Estructura**: Área abierta con una pared (que representa la imagen del Cristo) en el centro
- **Condición de Perder**: El jugador pierde si un enemigo llega al centro donde está el Cristo
- **Objetivo**: Defender el centro del mapa evitando que enemigos lleguen a él
- **Enemigos**: Aparecen de todos lados y convergen hacia el centro

## Cambios de Código

### `map_data.py`
- Agregado sistema de múltiples mapas con configuración individual
- Creados 3 mapas con estructuras diferentes (MAP_1_SACABA, MAP_2_MINES, MAP_3_CRISTO)
- Implementado sistema de selección de mapas con variables globales actualizables
- Agregado diccionario AVAILABLE_MAPS con información de cada mapa
- Creadas funciones:
  - `get_current_map()`: Obtiene la configuración del mapa actual
  - `set_map(map_index)`: Selecciona un mapa
  - `update_map_vars()`: Actualiza variables globales cuando cambia el mapa
  - `get_enemy_spawns_for_map(map_index)`: Obtiene spawns específicos del mapa
- Mejorada función `is_wall()` para aceptar parámetro opcional de mapa

### `main.py`
- Agregado estado de juego "map_select" para la selección de mapas
- Agregado variable `self.selected_map` para rastrear el mapa seleccionado
- Agregadas variables `self.current_map_config` y `self.current_enemy_spawns` para manejar configuración por mapa
- Modificado `reset_game()` para:
  - Cargar configuración del mapa seleccionado
  - Establecer la posición inicial del jugador según el mapa
  - Usar los spawns específicos del mapa
- Actualizado `handle_events()` para:
  - Manejar navegación en menú de mapas (flechas ← →)
  - Permitir selección de mapa con ENTER o clic del ratón
  - Permitir retroceder al menú principal con ESC
- Agregado método `draw_map_select()` para mostrar interfaz de selección
- Actualizado método `draw()` para mostrar el menú de selección
- Implementada lógica de condiciones de pérdida por mapa en `update()`:
  - **Mapa 2 (Minas)**: Verifica si enemigos alcanzan la salida
  - **Mapa 3 (Cristo)**: Verifica si enemigos alcanzan el centro
  - **Mapa 1 (Calles)**: Usa la mecánica estándar (solo perder si salud = 0)
- Modificadas funciones de spawns para usar configuración dinámica del mapa

## Flujo de Juego

1. **Menú Principal** → Presionar ENTER o clic para continuar
2. **Selector de Mapas** → Navegar con flechas ← → y presionar ENTER para seleccionar
3. **Juego** → Jugar en el mapa seleccionado con sus reglas específicas
4. **Fin de Juego** → Entrada de nombre y puntuación

## Controles

### En el Menú de Selección
- **Flechas ← →**: Navegar entre mapas
- **ENTER**: Seleccionar mapa y comenzar a jugar
- **ESC**: Volver al menú principal
- **Clic del Ratón**: Seleccionar el mapa mostrado

### Durante el Juego
- **W/↑**: Avanzar
- **S/↓**: Retroceder
- **A**: Movimiento lateral izquierda
- **D**: Movimiento lateral derecha
- **Flechas ←→**: Girar
- **Movimiento del Ratón**: Mirar alrededor
- **ESPACIO**: Disparar
- **1/2**: Cambiar arma
- **ESC**: Volver al menú
- **F11**: Pantalla completa

## Características Técnicas

- Cada mapa tiene su propio conjunto de puntos de spawn de enemigos
- Los spawns se distribuyen estratégicamente según la estructura del mapa
- El sistema de raycasting y colisiones se adapta dinámicamente al mapa actual
- Las condiciones de victoria/derrota son independientes por mapa
- El minimapa se actualiza automáticamente con la estructura del mapa actual

## Próximas Mejoras Sugeridas

- Agregar texturas y decoraciones diferentes para cada mapa
- Implementar enemigos con variantes visuales según el mapa
- Agregar efectos de sonido ambientales específicos por mapa
- Aumentar la dificultad progresiva en cada mapa
- Agregar power-ups o items interactivos según el mapa
- Implementar cinemáticas de introducción para cada mapa
