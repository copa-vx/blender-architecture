"""The answers of the chat: a small house architect with no AI model.

It works as the basic bot of Copa-ai/personal-nutrition (docs/chat-arquitectura.md, 2g): it
reads plain sentences in English or Spanish, changes the parametric model of this repository
(`blender.model.House`), and answers with an HTML widget (chat.md 5.4) and a keyboard form
(chat.md 5.5), both as text in a `TextContent`. A render runs the unchanged
`build_house.py` in headless Blender and posts the PNG, the house JSON and the .blend.

One instance is one conversation and one house (chat.md section 2, "Session"). Each change
is checked by `House.validate()` before it is kept; a change that fails keeps the old house.
"""

import copy
import html
import json
import os
import re
import unicodedata

from blender.model import Door, Floor, House, Room, ValidationError, Window

from .render import QUALITY, RenderError

NUM = r"(\d+(?:[.,]\d+)?)"
WORDS = {
    "one": 1, "a": 1, "an": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
    "uno": 1, "una": 1, "un": 1, "dos": 2, "tres": 3, "cuatro": 4, "cinco": 5, "seis": 6,
}
COUNT = r"(\d+|" + "|".join(sorted(WORDS, key=len, reverse=True)) + r")"
STYLES = {"cottage": "cottage", "rustic": "cottage", "rustico": "cottage", "rustica": "cottage",
          "medieval": "medieval", "modern": "modern", "moderno": "modern", "moderna": "modern"}
PRESETS = {"small": "small_house", "pequena": "small_house", "cottage": "cottage",
           "medieval": "medieval_house"}
SPANISH = re.compile(r"\b(casa|planta|plantas|ancho|fondo|tejado|ventana|renderiza|hola|ayuda|"
                     r"dormitorios?|habitaciones?|arboles|estilo|piedra|nueva|deshacer|quita|"
                     r"anade|pon|quiero|haz|muestra|ensename|mas|metros|con|una|dos|tres)\b")
MIN_ROOM = 2.6  # a room narrower than this has no room for a 1.4 m window
MAX_SIDE = 40.0
MAX_FLOORS = 4

T = {
    "help": (
        "I design a small house and render it with Blender (Cycles, on the CPUs of the node).\n\n"
        "Tell me what you want, for example:\n"
        "- *A house of 120 m2 with two floors and three bedrooms, then render*\n"
        "- *12 x 9*, *3 floors*, *pitch 40*, *style medieval*, *stone walls on*, *8 trees*\n"
        "- *add a window*, *bigger*, *another layout*, *undo*, *json*\n"
        "- *example cottage* or *example medieval*, or paste a house JSON\n"
        "- *render* (or *render draft* / *render high*)",
        "Diseño una casa pequeña y la renderizo con Blender (Cycles, en las CPU del nodo).\n\n"
        "Dime lo que quieres, por ejemplo:\n"
        "- *Una casa de 120 m2 con dos plantas y tres dormitorios, y renderiza*\n"
        "- *12 x 9*, *3 plantas*, *pendiente 40*, *estilo medieval*, *muros de piedra*, *8 árboles*\n"
        "- *añade una ventana*, *más grande*, *otra variación*, *deshacer*, *json*\n"
        "- *ejemplo cottage* o *ejemplo medieval*, o pega un JSON de casa\n"
        "- *renderiza* (o *renderiza borrador* / *renderiza alta*)"),
    "unknown": ("I did not understand that. Here is what I can do.",
                "No lo he entendido. Esto es lo que sé hacer."),
    "changed": ("Done: %s.", "Hecho: %s."),
    "nochange": ("The house did not change.", "La casa no ha cambiado."),
    "invalid": ("I cannot do that: %s. The house stays as it was.",
                "No puedo hacerlo: %s. La casa se queda como estaba."),
    "roof": ("Only a gable roof exists in Milestone 1 (hip and flat roofs are Milestone 2+).",
             "Solo hay tejado a dos aguas en el Milestone 1 (a cuatro aguas y plano llegan después)."),
    "undo": ("Undone. ", "Deshecho. "),
    "noundo": ("There is nothing to undo.", "No hay nada que deshacer."),
    "loaded": ("Loaded the house JSON: %s.", "He cargado el JSON de la casa: %s."),
    "badjson": ("That JSON is not a house I can build: %s.", "Ese JSON no es una casa que pueda construir: %s."),
    "rendering": ("Rendering %s (%s, %dx%d, %d samples)...\n", "Renderizando %s (%s, %dx%d, %d muestras)...\n"),
    "rendered": ("Rendered in %.0f s.", "Renderizado en %.0f s."),
    "result": ("Your house: %s. The image, the house JSON and the Blender scene (.blend) are attached.",
               "Tu casa: %s. Van adjuntos la imagen, el JSON de la casa y la escena de Blender (.blend)."),
    "renderfail": ("The render failed: %s", "El render ha fallado: %s"),
    "json": ("The model of the house (send it back as text to load it again):",
             "El modelo de la casa (envíalo de nuevo como texto para cargarlo):"),
    "form": ("Change the house", "Cambia la casa"),
    "apply": ("Apply and render", "Aplicar y renderizar"),
    "say_apply": ("Width {w}, depth {d}, {f} floors, pitch {p}, style {s}, {t} trees, stone walls {stone}, render",
                  "Ancho {w}, fondo {d}, {f} plantas, pendiente {p}, estilo {s}, {t} árboles, muros de piedra {stone}, renderiza"),
    "f_w": ("Width (m)", "Ancho (m)"), "f_d": ("Depth (m)", "Fondo (m)"), "f_f": ("Floors", "Plantas"),
    "f_p": ("Roof pitch (deg)", "Pendiente del tejado (grados)"), "f_s": ("Style", "Estilo"),
    "f_t": ("Trees", "Árboles"), "f_stone": ("Stone walls", "Muros de piedra"),
    "k_render": ("Render", "Renderizar"), "say_render": ("Render", "Renderiza"),
    "k_draft": ("Quick draft", "Borrador rápido"), "say_draft": ("Render draft", "Renderiza borrador"),
    "k_undo": ("Undo", "Deshacer"), "say_undo": ("Undo", "Deshacer"),
    "k_window": ("Add a window", "Añadir ventana"), "say_window": ("Add a window", "Añade una ventana"),
    "sug": (("Render", "Add a floor", "Another layout"), ("Renderiza", "Añade una planta", "Otra variación")),
    "sug_after": (("Render high", "Add a window", "Undo"), ("Renderiza alta", "Añade una ventana", "Deshacer")),
    "title": ("House %s x %s m, %d floor(s)", "Casa %s x %s m, %d planta(s)"),
    "w_size": ("Footprint", "Planta"), "w_floors": ("Floors", "Plantas"), "w_rooms": ("Rooms", "Habitaciones"),
    "w_area": ("Built area", "Superficie"), "w_roof": ("Roof", "Tejado"), "w_style": ("Style", "Estilo"),
    "w_open": ("Doors / windows", "Puertas / ventanas"), "w_env": ("Trees / seed", "Árboles / semilla"),
    "gable": ("gable, %g deg", "a dos aguas, %g grados"),
    "toosmall": ("%d rooms do not fit on a %s m side (each room needs %.1f m)",
                 "%d habitaciones no caben en un lado de %s m (cada una necesita %.1f m)"),
}


def fold(text):
    """Lower case with no accents, for the matching only."""
    text = unicodedata.normalize("NFKD", text.lower())
    return "".join(c for c in text if not unicodedata.combining(c)).replace("²", "2")


def num(value):
    return float(value.replace(",", "."))


def count(value):
    return WORDS[value] if value in WORDS else int(value)


def g(value):
    return ("%.2f" % float(value)).rstrip("0").rstrip(".")


class Architect:
    """`answer(turn)` for `chat.Chat`. Keeps the house of the instance."""

    def __init__(self, renderer, examples_dir=None):
        self.renderer = renderer
        self.examples = examples_dir or os.environ.get(
            "EXAMPLES_DIR", os.path.join(os.environ.get("REPO_DIR", "/opt/blender-architecture"), "examples"))
        self.house = House.simple(width=10.0, depth=8.0, floors=1, name="house")
        self.house.validate()
        self.undo = []
        self.lang = 0

    # -- text helpers ---------------------------------------------------------

    def t(self, key, *args):
        text = T[key][self.lang]
        return text % args if args else text

    def title(self):
        h = self.house
        return self.t("title", g(h.width), g(h.depth), len(h.floors))

    def summary(self):
        h = self.house
        rooms = sum(len(f.rooms) for f in h.floors)
        return "%s x %s m, %d %s, %d %s, %s" % (
            g(h.width), g(h.depth), len(h.floors), ("floor(s)", "planta(s)")[self.lang],
            rooms, ("room(s)", "habitación(es)")[self.lang], h.style)

    def widget(self):
        h = self.house
        doors = sum(len(f.doors) for f in h.floors)
        windows = sum(len(f.windows) for f in h.floors)
        rows = [
            (self.t("w_size"), "%s x %s m" % (g(h.width), g(h.depth))),
            (self.t("w_floors"), "%d x %s m" % (len(h.floors), g(h.floors[0].height))),
            (self.t("w_rooms"), ", ".join("%d: %s" % (f.level, " / ".join(r.name for r in f.rooms)) for f in h.floors)),
            (self.t("w_area"), "%.1f m2" % h.area),
            (self.t("w_roof"), self.t("gable", h.roof.pitch)),
            (self.t("w_style"), h.style + (" + stone" if h.stone_walls else "")),
            (self.t("w_open"), "%d / %d" % (doors, windows)),
            (self.t("w_env"), "%d / %d" % (h.tree_count, h.seed)),
        ]
        cells = "".join("<tr><th>%s</th><td>%s</td></tr>" % (html.escape(a), html.escape(b)) for a, b in rows)
        return "```html\n<div><h4>%s</h4><table>%s</table></div>\n```" % (html.escape(h.name), cells)

    def keyboard(self):
        h = self.house
        e = html.escape

        def options(name, values, chosen):
            return "".join('<option value="%s"%s>%s</option>' % (v, " selected" if v == chosen else "", label)
                           for v, label in values)

        styles = options("s", [("cottage", "cottage"), ("medieval", "medieval"), ("modern", "modern")], h.style)
        floors = options("f", [(str(n), str(n)) for n in range(1, MAX_FLOORS + 1)], str(len(h.floors)))
        on = (" checked" if h.stone_walls else "")
        return "\n".join([
            "```keyboard",
            "<p>%s</p>" % e(self.t("form")),
            '<div><input data-name="w" type="range" min="5" max="30" step="0.5" value="%s" placeholder="%s"></div>'
            % (g(h.width), e(self.t("f_w"))),
            '<div><input data-name="d" type="range" min="5" max="30" step="0.5" value="%s" placeholder="%s"></div>'
            % (g(h.depth), e(self.t("f_d"))),
            '<div><select data-name="f" placeholder="%s">%s</select></div>' % (e(self.t("f_f")), floors),
            '<div><input data-name="p" type="range" min="15" max="60" step="5" value="%s" placeholder="%s"></div>'
            % (g(min(60, max(15, h.roof.pitch))), e(self.t("f_p"))),
            '<div><select data-name="s" placeholder="%s">%s</select></div>' % (e(self.t("f_s")), styles),
            '<div><input data-name="t" type="range" min="0" max="20" step="1" value="%d" placeholder="%s"></div>'
            % (min(20, h.tree_count), e(self.t("f_t"))),
            '<div><input data-name="stone" type="checkbox" value="on" data-off="off"%s placeholder="%s"></div>'
            % (on, e(self.t("f_stone"))),
            '<div><button data-say="%s" data-send>%s</button></div>' % (e(self.t("say_apply")), e(self.t("apply"))),
            '<div><button data-say="%s" data-send>%s</button> <button data-say="%s" data-send>%s</button> '
            '<button data-say="%s">%s</button> <button data-say="%s">%s</button></div>'
            % (e(self.t("say_render")), e(self.t("k_render")), e(self.t("say_draft")), e(self.t("k_draft")),
               e(self.t("say_window")), e(self.t("k_window")), e(self.t("say_undo")), e(self.t("k_undo"))),
            "```",
        ])

    # -- the turn ---------------------------------------------------------------

    def answer(self, turn):
        text = turn.user_text.strip()
        low = fold(text)
        if SPANISH.search(low):
            self.lang = 1
        elif re.search(r"\b(the|house|floors?|render|width|depth|please|add|with|and)\b", low):
            self.lang = 0
        plan = self.read(text, low)
        lines = []
        if plan.get("help"):
            if plan.get("unknown"):
                lines.append(self.t("unknown"))
            lines.append(self.t("help"))
        for note in plan.get("notes", []):
            lines.append(note)
        if plan.get("json"):
            lines.append(self.t("json"))
            lines.append("```json\n%s\n```" % self.house.to_json())
        turn.set_title(self.title())
        if plan.get("render"):
            if lines:
                turn.write("\n\n".join(lines) + "\n\n")
            return self.render(turn, plan["render"])
        lines.append(self.widget())
        lines.append(self.keyboard())
        turn.write("\n\n".join(lines))
        turn.finish(suggestions=T["sug"][self.lang])

    def render(self, turn, quality):
        width, height, samples = QUALITY[quality]
        turn.write(self.t("rendering", self.summary(), quality, width, height, samples))
        turn.progress(0.05, "Blender")
        try:
            result = self.renderer.render(self.house.to_json(), quality,
                                          progress=turn.progress, cancelled=turn.cancelled)
        except RenderError as error:
            turn.check()
            turn.fail(self.t("renderfail", error))
            return
        turn.check()
        turn.write(self.t("rendered", result["seconds"]))
        turn.finish()
        files = [("image", result["png"], "image/png", "house.png",
                  {"alt_text": "Render of %s" % self.summary()}),
                 ("file", result["json"], "application/json", "house.json", {})]
        if os.path.getsize(result["blend"]) <= (32 << 20):
            files.append(("file", result["blend"], "application/x-blender", "house.blend", {}))
        turn.post(self.t("result", self.summary()) + "\n\n" + self.keyboard(), files,
                  suggestions=T["sug_after"][self.lang],
                  metadata={"render_seconds": "%.1f" % result["seconds"], "quality": quality})

    # -- reading the user ---------------------------------------------------------

    def read(self, text, low):
        """Change the house for the text. Return a plan: help, notes, json, render."""
        plan = {"notes": []}
        if re.fullmatch(r"\s*(help|ayuda|hola|hi|hello|hey|start|menu|\?|que puedes hacer\??|what can you do\??)\s*", low):
            plan["help"] = True
            return plan
        if re.fullmatch(r"\s*(undo|deshacer|deshaz)\s*\.?", low):
            if self.undo:
                self.house = self.undo.pop()
                plan["notes"].append(self.t("undo") + self.t("changed", self.summary()))
            else:
                plan["notes"].append(self.t("noundo"))
            return plan
        if "{" in text and "}" in text:
            return self.load_json(text[text.index("{"):text.rindex("}") + 1], plan)
        if re.search(r"\b(json|modelo|model)\b", low):
            plan["json"] = True
        if re.search(r"\b(render\w*|dibuja\w*|draw|picture|imagen|preview|vista previa|show me|ensename|ensenamela)\b", low):
            plan["render"] = "normal"
            if re.search(r"\b(draft|borrador|quick|rapido|rapida|fast)\b", low):
                plan["render"] = "draft"
            elif re.search(r"\b(high|alta|hd|detail\w*|detalle)\b", low):
                plan["render"] = "high"
        if re.search(r"\b(flat|plano|hip|cuatro aguas|tower|torre)\b", low):
            plan["notes"].append(self.t("roof"))
        work = copy.deepcopy(self.house)
        try:
            changes = self.edit(work, low)
            if changes:
                work.validate()
        except (ValidationError, ValueError) as error:
            plan["notes"].append(self.t("invalid", str(error)))
            return plan
        if changes:
            self.undo = (self.undo + [self.house])[-20:]
            self.house = work
            plan["notes"].append(self.t("changed", ", ".join(changes)))
        elif not plan.get("render") and not plan.get("json") and not plan["notes"]:
            plan["help"] = plan["unknown"] = True
        return plan

    def load_json(self, raw, plan):
        try:
            house = House.from_dict(json.loads(raw))
            house.validate()
        except (ValueError, KeyError, TypeError) as error:  # ValidationError is a ValueError
            plan["notes"].append(self.t("badjson", str(error)[:300]))
            return plan
        self.undo = (self.undo + [self.house])[-20:]
        self.house = house
        plan["notes"].append(self.t("loaded", self.summary()))
        return plan

    def edit(self, h, low):
        """Apply every change that the text names, in a fixed order. Return the change list."""
        done = []
        m = re.search(r"\b(?:example|ejemplo|preset|plantilla|load|carga)\s+(?:de\s+|the\s+|la\s+)?(small|pequena|cottage|medieval)", low)
        if m:
            loaded = House.load(os.path.join(self.examples, PRESETS[m.group(1)] + ".json"))
            h.__dict__.update(copy.deepcopy(loaded.__dict__))
            done.append("example " + PRESETS[m.group(1)])
        elif re.search(r"\b(new house|nueva casa|reset|empezar de nuevo|start again)\b", low):
            h.__dict__.update(House.simple(width=10.0, depth=8.0).__dict__)
            done.append("new house")

        m = re.search(r"\b(?:name|nombre|call it|llamala)\s*[:=]?\s*\"?([a-z0-9][a-z0-9 _-]{0,39})", low)
        if m and re.search(r"\b(name|nombre|call it|llamala)\b", low):
            h.name = m.group(1).strip().replace(" ", "_")
            done.append("name " + h.name)

        # Floors before rooms and size, so "2 floors and 120 m2" splits the area in 2.
        floors = None
        m = re.search(COUNT + r"\s+(?:floors?|storeys?|stories|levels?|plantas?|pisos?|niveles?|alturas)\b", low) \
            or re.search(r"\b(?:floors?|storeys?|plantas?|pisos?)\s*[:=]?\s*(\d+)\b", low)
        if re.search(r"\b(add|another|one more|anade|otra|pon)\b.{0,12}\b(floor|storey|planta|piso)\b", low):
            floors = len(h.floors) + 1
        elif re.search(r"\b(remove|delete|one less|quita|elimina|borra)\b.{0,12}\b(floor|storey|planta|piso)\b", low):
            floors = len(h.floors) - 1
        elif m:
            floors = count(m.group(1))
        if floors is not None and floors != len(h.floors):
            if not 1 <= floors <= MAX_FLOORS:
                raise ValueError("a house has 1 to %d floors" % MAX_FLOORS)
            set_floors(h, floors)
            done.append("%d floor(s)" % floors)

        m = re.search(r"\b" + NUM + r"\s*(?:m)?\s*(?:x|×|por|by)\s*" + NUM + r"\b", low)
        if m:
            h.resize(check_side(num(m.group(1))), check_side(num(m.group(2))))
            done.append("%s x %s m" % (g(h.width), g(h.depth)))
        else:
            m = re.search(r"\b" + NUM + r"\s*(?:m2|m 2|sq ?m|square met\w*|metros cuadrados|metros2)", low)
            if m:
                total = num(m.group(1))
                if not 20 <= total <= 1200:
                    raise ValueError("the area must be 20 to 1200 m2")
                footprint = total / len(h.floors)
                ratio = float(h.width) / float(h.depth)
                width = (footprint * ratio) ** 0.5
                h.resize(check_side(width), check_side(footprint / width))
                done.append("%s m2 (%s x %s m)" % (g(total), g(h.width), g(h.depth)))
            width = value_after(low, r"width|wide|ancho|anchura")
            depth = value_after(low, r"depth|deep|fondo|profundidad|long|largo")
            if width or depth:
                h.resize(check_side(width or h.width), check_side(depth or h.depth))
                done.append("%s x %s m" % (g(h.width), g(h.depth)))
            scale = None
            if re.search(r"\b(bigger|larger|mas grande)\b", low):
                scale = (1.2, 1.2)
            elif re.search(r"\b(smaller|mas pequena|mas pequeno|mas chica)\b", low):
                scale = (0.8, 0.8)
            elif re.search(r"\b(wider|mas ancha|mas ancho)\b", low):
                scale = ((float(h.width) + 2) / float(h.width), 1.0)
            elif re.search(r"\b(narrower|mas estrecha|mas estrecho)\b", low):
                scale = ((float(h.width) - 2) / float(h.width), 1.0)
            elif re.search(r"\b(deeper|mas profunda|mas profundo)\b", low):
                scale = (1.0, (float(h.depth) + 2) / float(h.depth))
            if scale:
                h.resize(check_side(round(float(h.width) * scale[0] * 2) / 2),
                         check_side(round(float(h.depth) * scale[1] * 2) / 2))
                done.append("%s x %s m" % (g(h.width), g(h.depth)))

        m = re.search(COUNT + r"\s+(rooms?|bedrooms?|habitaciones?|dormitorios?|cuartos?)\b", low)
        if m:
            n = count(m.group(1))
            bedrooms = m.group(2).startswith(("bed", "dorm"))
            set_rooms(h, n, bedrooms, self.lang)
            done.append("%d %s" % (n, m.group(2)))

        height = value_after(low, r"floor height|ceiling|altura de planta|altura")
        if height:
            if not 2.4 <= height <= 4.5:
                raise ValueError("a floor is 2.4 to 4.5 m high")
            for f in h.floors:
                f.height = height
            done.append("floor height %s m" % g(height))

        pitch = value_after(low, r"pitch|slope|pendiente|inclinacion|angulo")
        if pitch is None and re.search(r"\b(steeper|mas inclinado|mas pendiente)\b", low):
            pitch = float(h.roof.pitch) + 5
        elif pitch is None and re.search(r"\b(flatter|menos inclinado|menos pendiente)\b", low):
            pitch = float(h.roof.pitch) - 5
        if pitch is not None:
            if not 10 <= pitch <= 60:
                raise ValueError("the roof pitch is 10 to 60 degrees")
            h.roof.pitch = pitch
            done.append("pitch %s" % g(pitch))

        m = re.search(r"\b(?:style|estilo)\s*[:=]?\s*(cottage|rustic|rustico|rustica|medieval|modern|moderno|moderna)\b", low) \
            or re.search(r"\b(medieval|modern|moderno|moderna|rustic|rustico|rustica)\b", low)
        if m and STYLES[m.group(1)] != h.style:
            h.style = STYLES[m.group(1)]
            done.append("style " + h.style)

        m = re.search(r"\b(?:stone walls?|muros? de piedra|paredes de piedra)\s*[:=]?\s*(on|off|yes|no|si)?\b", low)
        if m or re.search(r"\b(sin piedra|no stone)\b", low):
            on = bool(m) and (m.group(1) or "on") in ("on", "yes", "si")
            if on != h.stone_walls:
                h.stone_walls = on
                done.append("stone walls " + ("on" if on else "off"))

        m = re.search(COUNT + r"\s+(?:trees?|arboles?)\b", low) or re.search(r"\b(?:trees?|arboles?)\s*[:=]?\s*(\d+)\b", low)
        if re.search(r"\b(no trees|sin arboles)\b", low):
            h.tree_count = 0
            done.append("no trees")
        elif m:
            n = count(m.group(1))
            if not 0 <= n <= 60:
                raise ValueError("0 to 60 trees")
            h.tree_count = n
            done.append("%d trees" % n)

        m = re.search(r"\b(?:seed|semilla)\s*[:=]?\s*(\d+)\b", low)
        if m:
            h.seed = int(m.group(1))
            done.append("seed %d" % h.seed)
        elif re.search(r"\b(another layout|other layout|otra variacion|otra version|shuffle|baraja)\b", low):
            h.seed = int(h.seed) + 1
            done.append("seed %d" % h.seed)

        if re.search(r"\b(add|another|one more|anade|otra|pon|mas)\b.{0,10}\b(window|ventana)s?\b", low):
            done.append(add_window(h))
        elif re.search(r"\b(remove|delete|one less|quita|elimina|borra)\b.{0,10}\b(window|ventana)s?\b", low):
            for f in sorted(h.floors, key=lambda f: -f.level):
                if f.windows:
                    f.windows.pop()
                    done.append("one window less")
                    break
        return done


def value_after(low, names):
    m = re.search(r"\b(?:" + names + r")\b\s*(?:of|de|a|to|=|:|is|es)?\s*" + NUM, low) \
        or re.search(NUM + r"\s*m?\s+(?:" + names + r")\b", low)
    return num(m.group(1)) if m else None


def check_side(value):
    value = float(value)
    if not 5.0 <= value <= MAX_SIDE:
        raise ValueError("a side of the house is 5 to %g m, not %s" % (MAX_SIDE, g(value)))
    return round(value, 2)


def set_floors(h, n):
    """Add copies of the top floor (no doors) or remove the top floors."""
    h.floors.sort(key=lambda f: f.level)
    while len(h.floors) > n:
        h.floors.pop()
    while len(h.floors) < n:
        top = h.floors[-1]
        level = top.level + 1
        rename = lambda wall: re.sub(r"^L\d+_", "L%d_" % level, wall)  # noqa: E731
        floor = Floor(level=level, height=top.height, wall_thickness=top.wall_thickness,
                      rooms=[Room(name=r.name if top.level else "upper_%s" % r.name, x=r.x, y=r.y,
                                  width=r.width, depth=r.depth) for r in top.rooms])
        names = {r.name: floor.rooms[i].name for i, r in enumerate(top.rooms)}
        for w in top.windows:
            wall = rename(w.wall)
            for old, new in names.items():
                wall = wall.replace("_%s:" % old, "_%s:" % new)
            floor.windows.append(Window(wall=wall, position=w.position, width=w.width, height=w.height, sill=w.sill))
        # A door of the ground floor becomes a window above it.
        for d in top.doors:
            wall = rename(d.wall)
            for old, new in names.items():
                wall = wall.replace("_%s:" % old, "_%s:" % new)
            floor.windows.append(Window(wall=wall, position=d.position))
        walls = floor.wall_map()
        kept = []
        for w in floor.windows:  # drop a copy whose wall is gone or that overlaps a kept one
            wall = walls.get(w.wall)
            if wall is None:
                continue
            lo, hi = w.span(wall.length)
            if lo < 0 or hi > wall.length or any(
                    k.wall == w.wall and min(hi, k.span(wall.length)[1]) > max(lo, k.span(wall.length)[0])
                    for k in kept):
                continue
            kept.append(w)
        floor.windows = kept
        h.floors.append(floor)


def set_rooms(h, n, bedrooms, lang):
    """Lay out every floor again as a row of rooms along the longer side.

    Bedrooms: one floor gets a living room and n bedrooms; more floors get a living room and a
    kitchen on the ground floor and the bedrooms shared out above."""
    if not 1 <= n <= 8:
        raise ValueError("1 to 8 rooms")
    names = {}
    living, kitchen, bed, room = (("living", "kitchen", "bedroom", "room"),
                                  ("salon", "cocina", "dormitorio", "habitacion"))[lang]
    floors = sorted(h.floors, key=lambda f: f.level)
    if not bedrooms:
        for f in floors:
            names[f.level] = ["%s_%d" % (room, i + 1) for i in range(n)] if n > 1 else ["main" if f.level == 0 else "upper_%d" % f.level]
    elif len(floors) == 1:
        names[0] = [living] + ["%s_%d" % (bed, i + 1) for i in range(n)]
    else:
        names[floors[0].level] = [living, kitchen]
        upper = floors[1:]
        for i, f in enumerate(upper):
            share = n // len(upper) + (1 if i < n % len(upper) else 0)
            first = sum(n // len(upper) + (1 if j < n % len(upper) else 0) for j in range(i))
            names[f.level] = ["%s_%d" % (bed, first + k + 1) for k in range(max(1, share))]
    along_x = float(h.width) >= float(h.depth)
    side = float(h.width if along_x else h.depth)
    for f in floors:
        row = names[f.level]
        if side / len(row) < MIN_ROOM:
            raise ValueError(T["toosmall"][lang] % (len(row), g(side), MIN_ROOM))
        step = side / len(row)
        f.rooms = [Room(name=name, x=i * step if along_x else 0.0, y=0.0 if along_x else i * step,
                        width=step if along_x else float(h.width), depth=float(h.depth) if along_x else step)
                   for i, name in enumerate(row)]
        f.doors, f.windows = [], []
        level = "L%d_" % f.level
        front, back = ("south", "north") if along_x else ("west", "east")
        if f.level == floors[0].level:
            f.doors.append(Door(wall=level + row[0] + ":" + front, position=0.5))
        for i, name in enumerate(row):
            f.windows.append(Window(wall=level + name + ":" + back, position=0.5))
            if i or f.level != floors[0].level:
                f.windows.append(Window(wall=level + name + ":" + front, position=0.5))
        ends = (("west", row[0]), ("east", row[-1])) if along_x else (("south", row[0]), ("north", row[-1]))
        for end, name in ends:
            f.windows.append(Window(wall=level + name + ":" + end, position=0.5))


def add_window(h):
    """Put a window in the middle of the largest free part of an exterior wall."""
    best = None
    for f in sorted(h.floors, key=lambda f: f.level):
        for wall in f.walls(base_z=h.base_z(f.level)):
            if not wall.exterior:
                continue
            spans = sorted(op.span(wall.length) for op in f.openings_for(wall.id))
            edges = [0.3] + [x for s in spans for x in s] + [wall.length - 0.3]
            for lo, hi in zip(edges[0::2], edges[1::2]):
                gap = hi - lo
                if gap >= 1.4 + 0.6 and (best is None or gap > best[0]):
                    best = (gap, f, wall, (lo + hi) / 2 / wall.length)
    if best is None:
        raise ValueError("no exterior wall has room for one more window")
    _, f, wall, position = best
    f.windows.append(Window(wall=wall.id, position=round(position, 4)))
    return "a window on %s" % wall.id
