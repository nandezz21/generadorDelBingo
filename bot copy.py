import discord
import my_secrets
import requests
import cv2
import numpy as np
import asyncio
import re
import io
import base64
import os
import webserver
from discord.ext import commands
from PIL import Image, ImageDraw, ImageFont

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")


# Decodificar y abrir la imagen
plantilla_bingo = Image.open("Plantilla bingo parche de balance.png")


intents = discord.Intents.default()
intents.messages = True
intents.message_content = True  
bot = commands.Bot(command_prefix="!", intents=intents)
usuarios_en_proceso = {}  # Para rastrear quién está ejecutando el comando


mensajes_personalizados = [
    "✍️ Escribe un NERF a un monstruo o familia de 5⭐ o menos ",
    "✍️ Escribe un BUFF a un monstruo o familia de 5⭐ ",
    "✍️ Escribe un BUFF a un monstruo o familia de 5⭐ ",
    "✍️ Escribe un BUFF a un monstruo o familia de 5⭐ ",
    "✍️ Escribe un BUFF a un monstruo o familia de 4⭐ o menos ",
    "✍️ Escribe un BUFF a un monstruo o familia de 4⭐ o menos ",
    "✍️ Escribe un BUFF o NERF a un monstruo o familia de 5⭐ o menos (También en el texto)",
    "✍️ Escribe un BUFF o NERF a un monstruo o familia de 5⭐ o menos (También en el texto)",
    "✍️ Escribe un BUFF o NERF a un monstruo o familia de 5⭐ o menos (También en el texto) "
]

@bot.event
async def on_ready():
    print(f"Bot conectado como {bot.user}")

def detectar_espacio_participante_pil(img):
    """Detecta el área del rectángulo negro donde va el nombre del participante en una imagen ya abierta."""
    img = img.convert("RGB")
    pixeles = img.load()

    ancho, alto = img.size
    cafe = (185, 122, 87)

    x_min, x_max = ancho, 0
    y_min, y_max = alto, 0

    # Recorremos la imagen para encontrar el rectángulo cafe
    for y in range(alto):
        for x in range(ancho):
            if pixeles[x, y] == cafe:
                x_min = min(x_min, x)
                x_max = max(x_max, x)
                y_min = min(y_min, y)
                y_max = max(y_max, y)

    return x_min, x_max, y_min, y_max

def centrar_texto_participante(img, texto, fuente_path):
    """Centra el texto dentro del rectángulo cafe y ajusta el tamaño dinámicamente."""
    draw = ImageDraw.Draw(img)

    # Detectar el área del rectángulo cafe
    x_inicio, x_fin, y_superior, y_inferior = detectar_espacio_participante_pil(img)

    # Tamaño máximo de fuente
    tamano_fuente = 72  
    fuente = ImageFont.truetype(fuente_path, tamano_fuente, encoding="unic")

    # Ajustar tamaño de fuente si el texto es muy largo
    while draw.textbbox((0, 0), texto, font=fuente)[2] > (x_fin - x_inicio) - 10:
        tamano_fuente -= 2
        fuente = ImageFont.truetype(fuente_path, tamano_fuente, encoding="unic")

    # Calcular posición centrada
    text_width, text_height = draw.textbbox((0, 0), texto, font=fuente)[2:]
    x_text = x_inicio + (x_fin - x_inicio - text_width) // 2
    y_text = y_superior + (y_inferior - y_superior - text_height) // 2

    # Dibujar el texto en negro dentro del rectángulo negro
    draw.text((x_text, y_text), texto, fill="black", font=fuente)

    return img

def detectar_cuadros(img_pil, color_purpura=(163, 73, 164), tolerancia=40, debug=False):
    """Detecta el área del cuadrado púrpura y la divide en una cuadrícula de 3x3."""

    # Convertir la imagen de PIL a un array de NumPy (formato BGR para OpenCV)
    img = np.array(img_pil)
    img = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)  # OpenCV usa BGR, pero PIL usa RGB

    # Convertir el color púrpura de RGB a HSV
    color_purpura_bgr = np.uint8([[[163, 73, 164]]])  # OpenCV usa BGR, no RGB
    color_hsv = cv2.cvtColor(color_purpura_bgr, cv2.COLOR_BGR2HSV)[0][0]
    h, s, v = color_hsv  # Extraer los valores HSV

    # Convertir de BGR a HSV
    img_hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    
    # Definir los rangos de color con tolerancia
    lower = np.array([max(0, h - 10), max(50, s - tolerancia), max(50, v - tolerancia)])
    upper = np.array([min(179, h + 10), min(255, s + tolerancia), min(255, v + tolerancia)])

    # Crear máscara para detectar el color púrpura
    mask = cv2.inRange(img_hsv, lower, upper)

    # Encontrar los contornos del área púrpura
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    # Tomar el contorno más grande (suponiendo que es el cuadro púrpura)
    largest_contour = max(contours, key=cv2.contourArea)
    x, y, w, h = cv2.boundingRect(largest_contour)

    # Cargar la imagen en PIL para dibujar sobre ella
    draw = ImageDraw.Draw(img_pil)

    # Dividir en 9 partes (3x3)
    cell_w, cell_h = w // 3, h // 3
    cuadros = []

    for fila in range(3):
        for col in range(3):
            x_min = x + col * cell_w
            y_min = y + fila * cell_h
            x_max = x_min + cell_w
            y_max = y_min + cell_h
            cuadros.append((x_min, y_min, x_max, y_max))

            # Dibujar líneas para visualizar la cuadrícula (opcional)
            draw.rectangle([x_min, y_min, x_max, y_max], outline="black", width=3)

    # Guardar y mostrar la imagen con la cuadrícula para depuración
    img_pil.save("resultado_debug.png")

    return img_pil, cuadros

def dividir_texto(texto, fuente, max_ancho, prefijo=None):
    """Divide el texto en varias líneas si es más ancho que el espacio disponible."""
    palabras = texto.split()
    lineas = []
    linea_actual = ""

    # Crear una imagen temporal para medir el texto
    img_temp = Image.new("RGB", (1, 1))  
    draw = ImageDraw.Draw(img_temp)  

    for palabra in palabras:
        if draw.textbbox((0, 0), linea_actual + palabra, font=fuente)[2] <= max_ancho:
            linea_actual += palabra + " "
        else:
            lineas.append(linea_actual.strip())
            linea_actual = palabra + " "

    lineas.append(linea_actual.strip())  # Agregar última línea

    # Si hay un prefijo, agregarlo como la primera línea separada
    if prefijo:
        lineas.insert(0, prefijo)  

    return lineas


def dibujar_textos(img, cuadros, textos, fuente_path="arialbd.ttf"):
    """Dibuja los textos ingresados en los cuadros detectados, con saltos de línea si es necesario."""
    draw = ImageDraw.Draw(img)
    fuente = ImageFont.truetype(fuente_path, 72)  

    cuadros_ordenados = sorted(cuadros, key=lambda c: (c[1], c[0]))

    for i, (x_min, y_min, x_max, y_max) in enumerate(cuadros_ordenados):
        texto = textos[i]

        tamano_fuente = 72
        fuente = ImageFont.truetype(fuente_path, tamano_fuente)

        # Determinar el prefijo según la posición
        prefijo = None
        if i == 0:
            prefijo = "NERF"
        elif 1 <= i <= 5:
            prefijo = "BUFF"
        else:
            prefijo = None  # Para los últimos 3, verificamos si ya tienen "BUFF" o "NERF"
        
        # Si es uno de los últimos 3 cuadros, revisamos si contiene "BUFF" o "NERF" en cualquier parte
        if i >= 6:
            match = re.search(r"(BUFF|NERF)", texto, re.IGNORECASE)
            if match:
                prefijo = match.group(1).upper()  # Extrae la palabra encontrada
                texto = re.sub(r"(BUFF|NERF)", "", texto, flags=re.IGNORECASE).strip().capitalize()  # Elimina la palabra y capitaliza el texto

        # Dividir en líneas incluyendo prefijo si es necesario
        max_ancho = x_max - x_min - 10
        lineas = dividir_texto(texto, fuente, max_ancho, prefijo=prefijo)

        # Calcular altura total del texto con separación entre líneas
        line_height = draw.textbbox((0, 0), "Ay", font=fuente)[3] + 5  
        text_height_total = len(lineas) * line_height

        # Calcular posición Y inicial centrada
        y_text = y_min + (y_max - y_min - text_height_total) // 2

        # Dibujar cada línea con espacio entre ellas
        for linea in lineas:
            bbox = draw.textbbox((0, 0), linea, font=fuente)
            text_width = bbox[2] - bbox[0]
            x_text = x_min + (x_max - x_min - text_width) // 2
            draw.text((x_text, y_text), linea, fill="black", font=fuente)
            y_text += line_height  # Moverse a la siguiente línea

    return img

"""
@bot.event    
async def on_message(message):
    if message.author.bot:  # Evita procesar mensajes del bot
        return
    
    print(f"Mensaje recibido: {message.content}")  # Depuración
    await bot.process_commands(message)  # Permite que los comandos sigan funcionando
"""

@bot.command()
async def generar(ctx):
    # Si el usuario ya tiene un proceso en ejecución, lo cancelamos y eliminamos mensajes previos
    if ctx.author.id in usuarios_en_proceso:
        tarea_anterior, mensajes_proceso = usuarios_en_proceso.pop(ctx.author.id)
        tarea_anterior.cancel()  # Cancelar la tarea activa

        # Eliminar los mensajes del proceso anterior
        await ctx.channel.delete_messages(mensajes_proceso)

        # Enviar mensaje de aviso
        await ctx.send("⚠️ Has reiniciado el proceso. Usa el comando nuevamente.")
        return

    usuario = ctx.author.display_name  # Obtener el nombre del usuario en Discord

    async def proceso_bingo():
        try:
            usuario_capitalizado = usuario.capitalize()  # Capitalizar el nombre
            textos_usuario = []
            mensajes_proceso = []  # Lista para rastrear los mensajes

            for i in range(9):
                if ctx.author.id not in usuarios_en_proceso:
                    return  

                mensaje_pregunta = await ctx.send(f"#{i+1}/9: {mensajes_personalizados[i]}")
                mensajes_proceso.append(mensaje_pregunta)

                def check(m):  
                    return m.author == ctx.author and m.channel == ctx.channel  

                # Si es una de las últimas 3 opciones, validar que empiece con BUFF o NERF
                if i >= 6:
                    while True:
                        msg = await bot.wait_for("message", check=check)
                        mensajes_proceso.append(msg)
                        texto_usuario = msg.content.strip().upper()  # Convertimos a mayúsculas para comparación

                        if texto_usuario.startswith("BUFF") or texto_usuario.startswith("NERF"):
                            break  # Si el texto es válido, salimos del bucle
                        else:
                            mensaje_error = await ctx.send("⚠️ El texto debe comenzar con **BUFF** o **NERF**. Inténtalo de nuevo.")
                            mensajes_proceso.append(mensaje_error)
                else:
                    msg = await bot.wait_for("message", check=check)
                    mensajes_proceso.append(msg)
                    texto_usuario = msg.content.capitalize()

                textos_usuario.append(texto_usuario)  

            #imagen_plantilla = Image.open(io.BytesIO(image_bytes))
            plantilla = plantilla_bingo.copy()
            
            # Procesar imagen...
            img = centrar_texto_participante(plantilla, usuario_capitalizado, "arialbd.ttf")
            img, cuadros = detectar_cuadros(img)
            img = dibujar_textos(img, cuadros, textos_usuario, "arialbd.ttf")

            output_path = f"{usuario}.png"
            img.save(output_path)

            mensaje_final = await ctx.send("✅ ¡Aquí está tu bingo, muchas gracias por participar!", file=discord.File(output_path))
            mensajes_proceso.append(mensaje_final)

        except asyncio.CancelledError:
            return  # Evita mensajes extra si se cancela

        finally:
            # Quitar usuario del proceso al finalizar
            usuarios_en_proceso.pop(ctx.author.id, None)

    # Crear y almacenar la nueva tarea con los mensajes
    tarea = asyncio.create_task(proceso_bingo())
    usuarios_en_proceso[ctx.author.id] = (tarea, [])



@bot.command()
async def cancelar(ctx):
    # Verifica si el usuario tiene un proceso en ejecución
    if ctx.author.id not in usuarios_en_proceso:
        await ctx.send("❌ No tienes un proceso en curso para cancelar.")
        return
    
    # Extraer correctamente la tarea y la lista de mensajes
    datos_usuario = usuarios_en_proceso.pop(ctx.author.id, None)
    
    if datos_usuario:
        tarea_anterior, mensajes_proceso = datos_usuario  # Extraer valores correctamente
        
        if tarea_anterior and hasattr(tarea_anterior, 'cancel'):
            tarea_anterior.cancel()  # Cancelar la tarea si existe

        # Intentar eliminar los mensajes asociados a este usuario
        try:
            if mensajes_proceso:
                await ctx.channel.delete_messages(mensajes_proceso)
        except discord.Forbidden:
            await ctx.send("❌ No tengo permisos para borrar mensajes en este canal.")
        except discord.HTTPException:
            await ctx.send("⚠️ No se pudieron eliminar algunos mensajes, es posible que sean demasiado antiguos.")

    # Enviar mensaje final de cancelación
    await ctx.send("🚫 Proceso cancelado. Usa `!generar` para intentarlo nuevamente.")


webserver.keep_alive()
bot.run(DISCORD_TOKEN)
