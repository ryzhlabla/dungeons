from dataclasses import dataclass
from html import escape
from .engine import scene_actions, scene_view, condition
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


@dataclass
class Card:
    asset: str
    caption: str
    keyboard: InlineKeyboardMarkup


def render(state, content):
    scene = scene_view(state, content)
    rows = []
    title, text = "", ""
    def row(*buttons):
        rows.append([InlineKeyboardButton(text=label, callback_data=f"g:{state.revision}:{action}")
                     for label, action in buttons])
    def back(action="ui:scene", label=content["copy"]["interface"]["Вернуться_в_игру"]):
        row((label, action))

    if state.screen == "start":
        title = content["copy"]["interface"]["ADVENTURE_Тайны_древней_пещеры"]
        text = content["copy"]["interface"]["За_лесной_дорогой_начинается_мир_забытых_троп"]
        row((content["copy"]["interface"]["Продолжить"], "ui:scene") if state.started else (content["copy"]["interface"]["Начать_приключение"], "new"))
        if state.started:
            row((content["copy"]["interface"]["Новая_игра"], "ui:confirm"))
        row((content["copy"]["interface"]["Как_играть"], "ui:help"))
    elif state.screen == "help":
        title = content["copy"]["interface"]["Как_играть"]
        text = content["copy"]["interface"]["Нажимайте_на_действия_под_картинкой_Осматривайтесь_собирайте"]
        back("ui:start", content["copy"]["interface"]["Назад"])
    elif state.screen == "scene":
        title, text = "📍 " + scene["title"].upper(), scene["text"]
        if state.item_locations["lamp"] == state.scene:
            text += content["copy"]["interface"]["Здесь_стоит_старая_переносная_лампа"]
            row((content["copy"]["interface"]["Взять_лампу"], "take_lamp"))
        if state.item_locations["keys"] == state.scene:
            text += "\n\n" + content["copy"]["keys"]["on_ground"]
            row((content["copy"]["keys"]["take_button"], "take_keys"))
        if state.item_locations["cage"] == state.scene:
            cage_copy = content["copy"]["cage"]
            text += "\n\n" + cage_copy["on_ground_full" if state.item_locations["bird"] == "cage" else "on_ground"]
            row((cage_copy["take_button"], "take_cage"))
        for a in scene_actions(state, content):
            prefix = "event:" if a.get("type") == "event" else "move:"
            row((a["label"], prefix + a["id"]))
        if state.item_locations["silver"] == state.scene:
            lit = not scene.get("dark") or condition(state, {"op": "light_here"})
            text += "\n\n" + content["copy"]["silver"]["on_ground" if lit else "on_ground_dark"]
            if lit:
                row((content["copy"]["silver"]["take_button"], "take_silver"))
        row((content["copy"]["interface"]["Осмотреться"], "ui:inspect"), (content["copy"]["interface"]["Рюкзак"], "ui:inventory"))
        row((content["copy"]["interface"]["Подсказка"], "ui:hint"), (content["copy"]["interface"]["Ещё"], "ui:menu"))
    elif state.screen == "inspect":
        title, text = "🔍 " + scene["title"], scene["inspect"]
        if state.item_locations["lamp"] == state.scene:
            text += content["copy"]["interface"]["Лампу_можно_взять_с_собой"]
        back()
    elif state.screen == "inventory":
        title = content["copy"]["interface"]["Рюкзак"]
        parts = []
        if state.flags.get("seed_sample_taken") and not state.flags.get("episode11_complete"):
            parts.append(content["copy"]["interface"]["Пробная_порция_семян"])
        if state.flags.get("striker_taken"):
            parts.append(content["scenes"]["stone_bells"]["buttons"]["take_striker"].removeprefix("Взять ").capitalize() + " с длинной рукоятью")
        if state.item_locations["lamp"] == "inventory":
            parts.append(content["copy"]["interface"]["Старая_лампа"] + (content["copy"]["interface"]["Горит"] if state.item_states["lamp"]["power"] else content["copy"]["interface"]["Выключена"]))
            row((content["copy"]["interface"]["Старая_лампа_2"], "ui:item"))
        if state.item_locations["keys"] == "inventory":
            parts.append(content["copy"]["keys"]["title"])
            row((content["copy"]["keys"]["title"], "ui:keys"))
        if state.item_locations["cage"] == "inventory":
            cage_title = content["copy"]["cage"]["title_full" if state.item_locations["bird"] == "cage" else "title"]
            parts.append(cage_title)
            row((cage_title, "ui:cage"))
        text = "\n\n".join(parts) or content["copy"]["interface"]["Рюкзак_пуст"]
        if state.item_locations["silver"] == "inventory":
            parts.append(content["copy"]["silver"]["title"])
            text = "\n\n".join(parts)
            row((content["copy"]["silver"]["title"], "ui:silver"))
        back()
    elif state.screen == "silver":
        title, text = content["copy"]["silver"]["title"], content["copy"]["silver"]["description"]
        row((content["copy"]["interface"]["Оставить_здесь"], "drop_silver"))
        back("ui:inventory", content["copy"]["interface"]["Рюкзак_2"])
    elif state.screen == "cage":
        cage_copy = content["copy"]["cage"]
        full = state.item_locations["bird"] == "cage"
        title = cage_copy["title_full" if full else "title"]
        text = cage_copy["description_full" if full else "description"]
        row((content["copy"]["interface"]["Оставить_здесь"], "drop_cage"))
        back("ui:inventory", content["copy"]["interface"]["Рюкзак_2"])
    elif state.screen == "keys":
        title, text = content["copy"]["keys"]["title"], content["copy"]["keys"]["description"]
        row((content["copy"]["interface"]["Оставить_здесь"], "drop_keys"))
        back("ui:inventory", content["copy"]["interface"]["Рюкзак_2"])
    elif state.screen == "item":
        title = content["copy"]["interface"]["Старая_лампа_2"]
        power = state.item_states["lamp"]["power"]
        text = content["copy"]["interface"]["Потёртый_металлический_корпус_и_прочная_ручка_Такая"] + (content["copy"]["interface"]["горит"] if power else content["copy"]["interface"]["выключена"])
        row((content["copy"]["interface"]["Погасить_лампу"], "lamp_off") if power else (content["copy"]["interface"]["Зажечь_лампу"], "lamp_on"))
        row((content["copy"]["interface"]["Оставить_здесь"], "drop_lamp"))
        back("ui:inventory", content["copy"]["interface"]["Рюкзак_2"])
    elif state.screen == "hint":
        title = content["copy"]["interface"]["Подсказка"]
        if scene["step"] >= 15:
            hints = scene["hints"] if not scene.get("dark") or condition(state, {"op": "light_here"}) else content["scenes"]["cave_entrance"]["hints"]
        elif state.flags.get("episode5_complete"):
            hints = [content["copy"]["interface"]["Пятая_цель_выполнена"]]
        elif state.flags.get("episode4_complete"):
            hints = content["copy"]["silver"]["stored_hints"]
        elif state.flags.get("silver_found"):
            hints = content["copy"]["silver"]["carried_hints" if state.item_locations["silver"] == "inventory" else "dropped_hints"]
        elif state.scene in {"calcite_passage", "silver_grotto", "water_gallery", "echo_hall", "underground_lake"}:
            hints = scene["hints"] if condition(state, {"op": "light_here"}) else content["scenes"]["cave_entrance"]["hints"]
        elif state.flags.get("episode3_complete"):
            hints = content["copy"]["silver"]["next_hints"]
        elif state.flags.get("episode2_complete"):
            hints = [content["copy"]["interface"]["Путь_к_третьему_эпизоду"]]
        elif state.scene in {"debris_grotto", "bird_grotto", "king_hall"} or state.flags.get("chapter_complete"):
            if not condition(state, {"op": "light_here"}):
                hints = content["scenes"]["cave_entrance"]["hints"]
            elif state.flags.get("snake_gone"):
                hints = content["copy"]["cage"]["released_hints"]
            elif state.item_locations["bird"] == "cage":
                hints = content["copy"]["cage"]["caught_hints"]
            elif state.scene in {"debris_grotto", "bird_grotto", "king_hall"}:
                hints = content["scenes"][state.scene]["hints"]
            else:
                hints = [content["copy"]["interface"]["Следующая_цель"]]
        elif state.scene == "first_hall":
            hints = content["scenes"]["first_hall"]["hints"]
            if not condition(state, {"op": "light_here"}):
                hints = content["scenes"]["cave_entrance"]["hints"]
        elif state.scene == "cave_entrance":
            hints = content["scenes"]["cave_entrance"]["hints"]
        elif state.scene == "grate" and state.flags.get("grate_open"):
            hints = [content["copy"]["interface"]["Подсказка_после_решётки"]]
        elif not state.flags.get("grate_open") and state.item_locations["keys"] != "inventory":
            hints = content["copy"]["keys"]["missing_hints"]
        elif state.scene == "grate":
            hints = content["scenes"]["grate"]["hints"]
        elif not condition(state, {"op": "carried_light"}):
            hints = content["scenes"]["cave_entrance"]["hints"]
        else:
            hints = [content["copy"]["interface"]["Подсказка_готовность"]]
        def place(item):
            location = state.item_locations[item]
            return content["copy"]["interface"]["В_рюкзаке"] if location == "inventory" else content["scenes"][location]["title"]
        silver_location = state.item_locations["silver"]
        silver_place = content["copy"]["silver"]["stored_place"] if silver_location == "treasury" else place("silver")
        text = hints[min(state.hint_level, len(hints)-1)].format(keys_location=place("keys"), lamp_location=place("lamp"), cage_location=place("cage"), silver_location=silver_place)
        if state.hint_level < len(hints)-1:
            row((content["copy"]["interface"]["Более_точная_подсказка"] if state.hint_level == 0 else content["copy"]["interface"]["Показать_решение"], "hint_more"))
        back()
    elif state.screen == "menu":
        title, text = content["copy"]["interface"]["Привал"], content["copy"]["interface"]["Можно_свериться_с_дневником_или_посмотреть_сколько"]
        row((content["copy"]["interface"]["Дневник"], "ui:journal"), (content["copy"]["interface"]["Прогресс"], "ui:progress"))
        row((content["copy"]["interface"]["Начать_заново"], "ui:confirm"))
        back()
    elif state.screen == "journal":
        title = content["copy"]["interface"]["Дневник"]
        entries = []
        size = 0
        for entry in reversed(state.journal[-8:]):
            line = "• " + entry
            if size + len(line) > 750:
                break
            entries.insert(0, line)
            size += len(line) + 1
        text = "\n".join(entries) or content["copy"]["interface"]["Пока_нет_записей"]
        back("ui:menu", content["copy"]["interface"]["Меню"])
    elif state.screen == "progress":
        title = content["copy"]["interface"]["Прогресс"]
        text = content["copy"]["interface"]["Исследовано_мест_value_0_value_1_Ходов"].format(value_0=len(state.visited), value_1=len(content['scenes']), value_2=state.turns) + (content["copy"]["interface"]["да"] if state.item_locations["lamp"] == "inventory" else content["copy"]["interface"]["нет"])
        goal = "Третья_цель_выполнена" if state.flags.get("episode3_complete") else ("Третья_цель" if state.flags.get("episode2_complete") else ("Вторая_цель" if state.flags.get("chapter_complete") else "Цель_осталась"))
        if state.flags.get("episode4_complete"):
            goal = "Пятая_цель_выполнена" if state.flags.get("episode5_complete") else "Пятая_цель"
        elif state.flags.get("episode3_complete"):
            goal = "Четвёртая_цель"
        if state.flags.get("episode5_complete"):
            goal = "Шестая_цель_выполнена" if state.flags.get("episode6_complete") else "Шестая_цель"
        if state.flags.get("episode6_complete"):
            goal = "Седьмая_цель_выполнена" if state.flags.get("episode7_complete") else "Седьмая_цель"
        if state.flags.get("episode7_complete"):
            goal = "Восьмая_цель_выполнена" if state.flags.get("episode8_complete") else "Восьмая_цель"
        if state.flags.get("episode8_complete"):
            goal = "Девятая_цель_выполнена" if state.flags.get("episode9_complete") else "Девятая_цель"
        if state.flags.get("episode9_complete"):
            goal = "Десятая_цель_выполнена" if state.flags.get("episode10_complete") else "Десятая_цель"
        if state.flags.get("episode10_complete"):
            goal = "Одиннадцатая_цель_выполнена" if state.flags.get("episode11_complete") else "Одиннадцатая_цель"
        if state.flags.get("episode11_complete"):
            goal = "Двенадцатая_цель_выполнена" if state.flags.get("episode12_complete") else "Двенадцатая_цель"
        if state.flags.get("episode12_complete"):
            goal = "Тринадцатая_цель_выполнена" if state.flags.get("episode13_complete") else "Тринадцатая_цель"
        text += "\n\n" + content["copy"]["interface"][goal]
        text += "\n\n" + content["copy"]["silver"]["progress"].format(found=int(bool(state.flags.get("silver_found"))), stored=int(bool(state.flags.get("episode4_complete"))))
        back("ui:menu", content["copy"]["interface"]["Меню"])
    elif state.screen == "confirm":
        title, text = content["copy"]["interface"]["Начать_заново_2"], content["copy"]["interface"]["Текущий_прогресс_будет_заменён_новой_игрой"]
        row((content["copy"]["interface"]["Да_начать_заново"], "reset"))
        back("ui:start", content["copy"]["interface"]["Отмена"])
    else:
        raise ValueError("Unknown screen")
    if state.notice and state.notice != text:
        notice_only = state.screen == "scene" and any(
            action.get("notice_only")
            and scene.get("messages", {}).get(action.get("message")) == state.notice
            for action in scene["actions"]
        )
        text = state.notice if notice_only else state.notice + "\n\n" + text
    caption = "<b>" + escape(title) + "</b>\n\n" + escape(text)
    asset = content["scenes"][content["start_scene"]]["media"] if state.screen in {"start", "help"} else scene["media"]
    return Card(asset, caption, InlineKeyboardMarkup(inline_keyboard=rows))
