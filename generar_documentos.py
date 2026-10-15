"""
Genera los 4 documentos de la tienda como imagenes "escaneadas" (JPG).

Son documentos sinteticos: el contenido esta inventado y se dibuja con Pillow.
Despues se les anade papel envejecido, ruido y una ligera inclinacion para que
el OCR trabaje con algo parecido a un escaneo real.

Uso (una sola vez):
    python generar_documentos.py
"""

from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

CARPETA = Path(__file__).parent / "documentos"
ANCHO, ALTO = 1240, 1754          # A4 a 150 ppp
MARGEN = 100
PAPEL = (244, 237, 218)           # crema
TINTA = (28, 26, 24)


def fuente(negrita: bool, tamano: int) -> ImageFont.FreeTypeFont:
    ruta = r"C:\Windows\Fonts\consolab.ttf" if negrita else r"C:\Windows\Fonts\consola.ttf"
    try:
        return ImageFont.truetype(ruta, tamano)
    except OSError:
        return ImageFont.load_default()


# Contenido de los documentos
# Cada linea es (estilo, texto). Estilos: titulo, sub, h, p, li, fila, pie, espacio

DOCUMENTOS = {
    "1_devoluciones_garantia.jpg": [
        ("sub", "*** GAME NON STOP ***  El juego nunca para"),
        ("titulo", "POLÍTICA DE DEVOLUCIONES Y GARANTÍA"),
        ("sub", "Vigente desde 01/03/2026  -  Ref. REF-GAR-2026"),
        ("espacio", ""),
        ("h", "1. DEVOLUCIONES"),
        ("li", "Tienes 14 días naturales desde la compra para devolver un juego, siempre con el ticket."),
        ("li", "El cartucho debe estar completo y en el mismo estado en que salió de la tienda. Si traes la caja, mejor que mejor."),
        ("li", "Reembolso: en vale de compra por el 100 % del importe pagado, o en dinero por el 80 %. Paco recomienda el vale. Paco siempre recomienda el vale."),
        ("li", "No se devuelven juegos con la etiqueta rayada, mojada o decorada por manos creativas."),
        ("li", "Los juegos reservados y recogidos en tienda tienen las mismas condiciones."),
        ("espacio", ""),
        ("h", "2. GARANTÍA"),
        ("li", "Cartuchos y juegos usados: 6 meses."),
        ("li", "Consolas reacondicionadas: 12 meses."),
        ("li", "Mandos y accesorios: 3 meses."),
        ("li", "La garantía no cubre líquidos derramados sobre la consola, cartuchos soplados con saliva ni pilas de guardado agotadas por el paso del tiempo."),
        ("li", "Si la consola falla dentro de garantía, la reparación es gratuita. Fuera de garantía, el presupuesto de revisión cuesta 15,00 EUR, que se descuentan si aceptas la reparación."),
        ("li", "Si no podemos repararla en 10 días hábiles, te damos una consola equivalente."),
        ("espacio", ""),
        ("pie", 'Última revisión: 15/09/2026  -  Firmado: Paco "Cartucho"'),
    ],
    "2_tasacion_usados.jpg": [
        ("sub", "*** GAME NON STOP ***  El juego nunca para"),
        ("titulo", "TARIFA DE TASACIÓN DE JUEGOS USADOS"),
        ("sub", "Tarifa del 15/09/2026  -  Ref. REF-TAS-2026"),
        ("espacio", ""),
        ("p", "Lo que pagamos por un cartucho en buen estado:"),
        ("espacio", ""),
        ("fila_h", "PLATAFORMA        COMPLETO        SOLO CARTUCHO"),
        ("fila", "NES               18,00 EUR       10,00 EUR"),
        ("fila", "Super Nintendo     25,00 EUR       15,00 EUR"),
        ("fila", "Sega Mega Drive    12,00 EUR        7,00 EUR"),
        ("fila", "Game Boy           15,00 EUR        9,00 EUR"),
        ("fila", "Nintendo 64        20,00 EUR       12,00 EUR"),
        ("espacio", ""),
        ("p", "Completo significa con caja y manual."),
        ("espacio", ""),
        ("h", "CONDICIONES"),
        ("li", "Si cobras en vale de compra, te damos un 20 % más."),
        ("li", "La pila de guardado tiene que funcionar. Un cartucho que no guarda vale la mitad."),
        ("li", "No tasamos juegos con moho ni repros. Paco huele una repro a tres calles."),
        ("li", "Los juegos especiales (Zelda: A Link to the Past, Pokémon Red, Metroid) se tasan aparte, en tienda."),
        ("li", "Máximo 5 juegos por socio y día."),
        ("li", "La tasación es válida durante 7 días."),
        ("espacio", ""),
        ("pie", 'Firmado: Paco "Cartucho"'),
    ],
    "3_club_socios.jpg": [
        ("sub", "*** GAME NON STOP ***  El juego nunca para"),
        ("titulo", "CLUB GAME NON STOP: NIVELES Y VENTAJAS"),
        ("sub", "Normas vigentes desde 02/01/2026  -  Ref. REF-CLUB-2026"),
        ("espacio", ""),
        ("h", "CÓMO HACERSE SOCIO"),
        ("li", "Es gratis. Se hace en la tienda con tu DNI y un teléfono móvil."),
        ("li", "Ganas 1 punto por cada euro gastado. Los puntos caducan a los 12 meses."),
        ("espacio", ""),
        ("h", "NIVELES"),
        ("li", "BRONCE: alta gratuita. 5 % de descuento en juegos."),
        ("li", "PLATA: desde 500 puntos. 10 % de descuento y reserva de lanzamientos con 48 horas de antelación."),
        ("li", "ORO: desde 1.500 puntos. 15 % de descuento y un cartucho sorpresa el día de tu cumpleaños."),
        ("espacio", ""),
        ("h", "RESERVAS"),
        ("li", "Solo los socios pueden reservar juegos."),
        ("li", "Cada socio puede tener hasta 3 reservas a la vez."),
        ("li", "Las reservas se guardan 7 días en la tienda."),
        ("espacio", ""),
        ("h", "OTRAS NORMAS"),
        ("li", "Los descuentos no se acumulan con otras ofertas."),
        ("li", "Los puntos no se pueden cambiar por dinero. Se canjean por descuentos."),
        ("espacio", ""),
        ("pie", 'Firmado: Paco "Cartucho"'),
    ],
    "4_catalogo_consolas.jpg": [
        ("sub", "*** GAME NON STOP ***  El juego nunca para"),
        ("titulo", "CONSOLAS RETRO EN VENTA: CATÁLOGO DE OCTUBRE"),
        ("sub", "Actualizado el 01/10/2026"),
        ("espacio", ""),
        ("p", "Todas son consolas reacondicionadas. Incluyen mando, cables y 12 meses de garantía."),
        ("espacio", ""),
        ("fila_h", "REFERENCIA       CONSOLA            PRECIO"),
        ("fila", "REF-NES-001      NES                89,00 EUR"),
        ("fila", "REF-SNES-001     Super Nintendo    129,00 EUR"),
        ("fila", "REF-MD-001       Sega Mega Drive    79,00 EUR"),
        ("fila", "REF-GB-001       Game Boy clásica   69,00 EUR"),
        ("fila", "REF-N64-001      Nintendo 64        99,00 EUR"),
        ("espacio", ""),
        ("h", "NOTAS"),
        ("li", "Stock limitado: una o dos unidades por modelo."),
        ("li", "Los socios pueden reservarlas igual que un juego."),
        ("li", "Los juegos no están incluidos. La charla de Paco sí, y es gratis."),
        ("li", "Envío a domicilio: 4,90 EUR. Gratis a partir de 100,00 EUR de compra."),
        ("espacio", ""),
        ("pie", 'Firmado: Paco "Cartucho"'),
    ],
}


# Dibujo

ESTILOS = {
    # estilo: (negrita, tamano, separacion tras la linea)
    "titulo": (True, 40, 14),
    "sub": (False, 26, 8),
    "h": (True, 32, 10),
    "p": (False, 29, 10),
    "li": (False, 29, 12),
    "fila_h": (True, 29, 8),
    "fila": (False, 29, 8),
    "pie": (False, 26, 8),
    "espacio": (False, 29, 20),
}


def partir_en_lineas(texto: str, fnt: ImageFont.FreeTypeFont, ancho: int) -> list[str]:
    lineas, actual = [], ""
    for palabra in texto.split(" "):
        prueba = f"{actual} {palabra}".strip()
        if fnt.getlength(prueba) <= ancho:
            actual = prueba
        else:
            lineas.append(actual)
            actual = palabra
    lineas.append(actual)
    return lineas


def dibujar(lineas_doc: list[tuple[str, str]]) -> Image.Image:
    img = Image.new("RGB", (ANCHO, ALTO), PAPEL)
    d = ImageDraw.Draw(img)
    y = MARGEN

    for estilo, texto in lineas_doc:
        negrita, tamano, sep = ESTILOS[estilo]
        fnt = fuente(negrita, tamano)
        sangria = 34 if estilo == "li" else 0
        ancho_util = ANCHO - 2 * MARGEN - sangria
        if estilo == "espacio":
            y += sep
            continue

        # Las filas de tabla no se parten ni se tocan los espacios: son columnas
        if estilo.startswith("fila"):
            trozos = [texto]
        else:
            trozos = partir_en_lineas(texto, fnt, ancho_util)

        for i, linea in enumerate(trozos):
            if estilo == "li" and i == 0:
                d.text((MARGEN, y), "-", font=fnt, fill=TINTA)
            d.text((MARGEN + sangria, y), linea, font=fnt, fill=TINTA)
            y += tamano + 8
        y += sep

    return img


def envejecer(img: Image.Image, semilla: int) -> Image.Image:
    """Papel con ruido, ligera inclinacion y un poco de desenfoque: un escaneo."""
    rng = np.random.default_rng(semilla)
    datos = np.asarray(img).astype(np.float32)

    # Degradado suave (el escaner ilumina peor los bordes) + ruido de grano
    yy, xx = np.mgrid[0:ALTO, 0:ANCHO]
    borde = np.sqrt(((xx - ANCHO / 2) / ANCHO) ** 2 + ((yy - ALTO / 2) / ALTO) ** 2)
    datos -= (borde[..., None] * 38)
    datos += rng.normal(0, 5, datos.shape)

    img = Image.fromarray(np.clip(datos, 0, 255).astype(np.uint8))
    img = img.rotate(rng.uniform(-0.9, 0.9), resample=Image.BICUBIC, fillcolor=(222, 214, 194))
    return img.filter(ImageFilter.GaussianBlur(0.5))


def main():
    CARPETA.mkdir(exist_ok=True)
    for i, (nombre, contenido) in enumerate(DOCUMENTOS.items()):
        envejecer(dibujar(contenido), semilla=i).save(CARPETA / nombre, quality=88)
        print("Creado:", CARPETA / nombre)


if __name__ == "__main__":
    main()
