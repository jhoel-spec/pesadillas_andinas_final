Pesadillas Andinas
Un proyecto académico y didáctico para comprender cómo los videojuegos de los años 90 lograban simular mundos tridimensionales a partir de mapas 2D, matemáticas y un renderizador basado en raycasting. Inspirado en motores clásicos como el de DOOM, este proyecto busca mostrar de forma visual y práctica las bases de los shooters en primera persona.

[Parece que el resultado no era seguro para mostrar. ¡Cambiemos de enfoque y probemos algo diferente!]

Requisitos
Python 3.10 o posterior

Pygame 2.6.1

NumPy 2.x

Instala las dependencias con:

powershell
python -m pip install -r requirements.txt
Cómo ejecutar
Desde la carpeta del proyecto:

powershell
python main.py
Para abrirlo en pantalla completa:

powershell
python main.py --pantalla-completa
En Windows también puedes usar ejecutar.bat.

Ejecutar en un sitio web
El juego puede publicarse en la web usando pygbag, que compila el proyecto a WebAssembly.

powershell
python -m pip install pygbag
python -m pygbag --bind 127.0.0.1 main.py
Luego abre la URL (normalmente http://127.0.0.1:8000). Para publicarlo, sube el contenido de build/web a un hosting de archivos estáticos como GitHub Pages, Netlify o itch.io.

Controles principales
WASD: movimiento

Ratón o flechas: girar cámara

Clic izquierdo o Espacio: disparar

1 y 2: cambiar de arma

R o Enter: iniciar/reiniciar

F11: pantalla completa

Esc: volver al menú

El juego avanza por oleadas: cada ronda aumenta la dificultad y al perder puedes guardar tu puntuación en el ranking local.

Objetivo del proyecto
La meta no es recrear el código original de DOOM, sino explorar las ideas que hicieron posibles los shooters clásicos:

Cómo un mapa plano se convierte en una vista en primera persona.

Cómo se proyectan las paredes y se dibujan enemigos con sprites 2D.

Cómo se manejan colisiones, movimiento y lógica de juego.

El título Pesadillas Andinas refleja el carácter experimental y creativo del proyecto, combinando aprendizaje técnico con un estilo propio.

Qué se explora
Mapas 2D y coordenadas: representación matricial del mundo.

Raycasting y DDA: cálculo eficiente de colisiones con paredes.

Corrección de ojo de pez: distancias laterales ajustadas.

Proyección en perspectiva: altura de columnas según distancia.

Suelo, techo y materiales: texturas y geometría procedural.

Sprites y billboards: enemigos y armas como imágenes 2D escaladas.

Oclusión por profundidad: depth_buffer para evitar glitches.

Movimiento y colisiones: trigonometría y desplazamiento estable.

Enemigos: estados de IA (reposo, ataque, daño, muerte).

Bucle de juego: separación entre lógica y renderizado.

Estructura del proyecto
text
.
├── README.md
├── requirements.txt
├── ejecutar.bat
├── main.py
├── map_data.py
├── raycasting.py
├── entities.py
├── renderer.py
├── settings.py
├── audio.py
├── pruebas_logica.py
└── assets/
    ├── enemies/        — sprites de enemigos
    ├── weapons/        — sprites de armas
    ├── textures/       — paredes, suelos y techos
    ├── previews/       — capturas de gameplay
    └── menu_background_doom.png
Enfoque
Cada sistema está separado para que pueda estudiarse paso a paso:

Mapa

Raycasting

Proyección

Entidades

Renderizado final

Esto permite entender cómo funcionaban los motores de los 90 sin depender de librerías externas complejas.

Audio
El proyecto incluye un sistema de audio de respaldo procedural, por lo que se mantiene jugable incluso sin archivos de sonido originales.

Más información
Canal de YouTube: https://youtube.com/@BrayanCode

Video demostrativo: https://youtu.be/FYUqyhQbzE0
