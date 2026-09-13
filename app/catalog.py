"""Generate the editor's scene map from the content used by the bot."""
from .content import ROOT, load_content


def describe_condition(spec, content):
    if not spec:
        return "—"
    if "all" in spec:
        return " и ".join(describe_condition(c, content) for c in spec["all"])
    if "not" in spec:
        return "Не выполнено: " + describe_condition(spec["not"], content)
    names = {"lamp": "лампа", "keys": "ключи", "cage": "клетка", "bird": "птица", "silver": "серебряный слиток"}
    flags = {"grate_open": "решётка открыта", "chapter_complete": "первый спуск завершён",
             "snake_gone": "змея ушла", "episode2_complete": "второй эпизод завершён",
             "bird_caught": "птица поймана", "water_path_known": "найден сухой обход потока", "episode3_complete": "берег озера изучен", "silver_found": "слиток найден", "episode4_complete": "слиток доставлен на хранение в дом"}
    flags.update(tower_signs_read="схема противовеса изучена", tower_weight_ready="противовес опущен", tower_eye_open="Око открыто", episode8_complete="долина изучена")
    flags.update(valley_signs_read="знаки путников изучены", valley_path_found="спуск к дороге найден", episode9_complete="история путников изучена")
    flags.update(ferry_brake_seen="стопор цепи обнаружен", ferry_released="береговое крепление парома отпущено", episode10_complete="запись о первом посеве изучена")
    flags.update(seed_instructions_read="указание о пробном посеве изучено", seed_sample_taken="пробная порция семян взята", episode11_complete="пробный посев сделан")
    flags.update(watcher_notes_read="запись смотрителя изучена", seedlings_ready="прошло несколько дней ухода", seedlings_verified="всходы осмотрены", return_path_known="метки к перевалу найдены", episode12_complete="проба проверена и путь из долины изучен")
    op = spec["op"]
    flags.update(root_signs_read="надпись у чаши росы изучена", root_beam="луч направлен к корням", garden_gate_open="проход в сад открыт", episode7_complete="история сада изучена")
    flags.update(striker_taken="ударник взят", water_signs_read="схема водяных часов изучена", water_diverted="вода отведена в боковой жёлоб", archive_shortcut="дверь между архивом и озером открыта", episode6_complete="летопись хранителей изучена")
    flags.update(bell_signs_read="знаки колоколов прочитаны", bell_lock_released="запор ворот отпущен", resonance_gate_open="каменные ворота открыты", wind_shortcut="лестница между галереей и балконом изучена", episode5_complete="карта Звёздного свода изучена")
    if op == "has_item":
        return names[spec["item"]] + " в рюкзаке"
    if op == "item_at":
        place = spec["location"]
        destination = content["scenes"][place]["title"] if place in content["scenes"] else {"cage": "внутри клетки", "inventory": "рюкзак", "gone": "покинула сцену", "treasury": "на хранении в доме"}[place]
        return names[spec["item"]] + ": " + destination
    if op in {"flag_set", "flag_not_set"}:
        text = flags.get(spec["flag"], spec["flag"])
        return text if op == "flag_set" else "Ещё не выполнено: " + text
    return {"carried_light": "зажжённая лампа с собой", "light_here": "свет лампы в комнате",
            "no_light_here": "нет света лампы",
            "light_or_known_path": "для первого входа нужна лампа; знакомый путь доступен без света"}[op]


def build_catalog(content):
    def cell(value):
        return str(value).replace("|", "／").replace("\n", " ")
    scenes = content["scenes"]
    lines = [
        "# Карта шагов", "",
        "Номер — постоянный номер сцены, а не ход игрока. Старые номера не меняются.",
        "Правьте тексты в JSON: при DEV_TEXT_RELOAD=true достаточно /refresh или нажатия кнопки; иначе нужен перезапуск. Замена существующего JPG подхватывается при обновлении карточки; назначение нового пути в game.json требует перезапуска.",
        "Карта обновляется командой python -m app.catalog, а в режиме разработки — автоматически при успешной загрузке правок. Правки карты не меняют игру.",
        "При возвращении описание выбирается по текущему состоянию мира так же, как при первом входе. Уже пойманная или улетевшая птица не возвращается из-за перехода между сценами.", "",
        "| Шаг | Место | Описание | Текст | Картинка |",
        "| --- | --- | --- | --- | --- |"]
    ordered = sorted(scenes.items(), key=lambda p: p[1]["step"])
    for sid, scene in ordered:
        image = content["media"][scene["media"]]
        lines.append(f"| {scene['step']:03d} | {cell(scene['title'])} | {cell(scene['text'])} | [Редактировать]({scene['text_file']}) | [Открыть]({image}) |")
    lines += ["", "## Действия и переходы", "",
              "| Шаг | Действие | Результат | Условие успеха | ID |",
              "| --- | --- | --- | --- | --- |"]
    for sid, scene in ordered:
        discovery = scene.get("inspect_discovery")
        if discovery:
            result = scene["messages"][discovery["message"]]
            light = "Свет лампы" if scene.get("dark") else "Дневной свет"
            requirement = describe_condition(discovery.get("requires"), content)
            lines.append(f"| {scene['step']:03d} | Осмотреться | {cell(result)} | {light}; {cell(requirement)}; запись в дневник только при первом подходящем осмотре | ui:inspect |")
        for action in scene["actions"]:
            if action.get("type") == "event":
                result = scene["messages"][action["message"]]
            else:
                target = scenes[action["target"]]
                result = f"{target['step']:03d} · {target['title']}"
            requirement = describe_condition(action.get("requires"), content)
            lines.append(f"| {scene['step']:03d} | {cell(action['label'])} | {cell(result)} | {cell(requirement)} | {action['id']} |")
    lines += ["", "## Картинки состояний и возвращений", "",
              "Настройки: [games/colossal_cave/game.json](games/colossal_cave/game.json). У каждой сцены и каждого варианта есть media и return_media. Значения — ключи из верхнего раздела media, где хранятся пути к файлам.",
              "return_media: null означает ту же картинку, что обычно. У варианта media: null сохраняет картинку предыдущего подходящего варианта или базовой сцены. Это сохраняет уже готовые картинки открытой решётки, пустого грота и темноты.",
              "Возвращение — повторный вход в уже посещённую сцену. Осмотр, меню и /refresh сохраняют этот признак. Для старых сохранений он определится при следующем переходе.",
              "Порядок: базовая media → её return_media при возвращении → подходящие варианты сверху вниз (media, затем return_media при возвращении). Последняя заданная картинка побеждает; темнота последняя.",
              "Названия новых файлов: номер сценария и понятное описание, например media/scenes/007.04_Грот_после_отлёта_птицы.jpg и media/scenes/007.04_Возвращение_после_отлёта_птицы.jpg. Пока отдельной иллюстрации нет, оставляйте null; копировать базовый JPG не нужно.", "",
              "| Сценарий | Где в scenes | Условие | media | return_media |",
              "| --- | --- | --- | --- | --- |"]
    def media_cell(asset):
        return f"[{asset}]({content['media'][asset]})" if asset else "null — наследуется"
    for sid, scene in ordered:
        lines.append(f"| {scene['step']:03d}.01 | {sid} | Базовая сцена | {media_cell(scene['media'])} | {media_cell(scene.get('return_media'))} |")
        for index, variant in enumerate(scene.get("variants", [])):
            lines.append(f"| {variant['id']} | {sid}.variants[{index}] | {cell(describe_condition(variant['when'], content))} | {media_cell(variant.get('media'))} | {media_cell(variant.get('return_media'))} |")
    lines += ["", "## Предметы и общие экраны", "",
              "- 002: лампа и ключи. 007: клетка. 008: птица, которую можно поймать в клетку.",
              "- Лампу, ключи и клетку можно оставлять и подбирать в любой сцене. Птица перемещается вместе с клеткой.",
              "- 014: серебряный слиток. Взять — take_silver (на месте, при свете в пещере); карточка — ui:silver; оставить — drop_silver. Повторный подбор не увеличивает число находок. В 002 сдача на хранение завершает четвёртый эпизод и убирает слиток из рюкзака.",
              "- В Зале Горного Короля птицу можно выпустить из переносимой клетки при свете лампы.",
              "- 000 — общий интерфейс, а не сцена. Рюкзак и меню показывают текущее место.", "",
              "## Варианты сцен", "",
              "Применяются сверху вниз. Вариант меняет только указанные поля; темнота применяется последней.", "",
              "| Сценарий | Когда | Изображение | Поля текста |", "| --- | --- | --- | --- |"]
    for sid, scene in ordered:
        for variant in scene.get("variants", []):
            image = content["media"].get(variant.get("media"))
            when = describe_condition(variant["when"], content)
            media_link = f"[Открыть]({image})" if image else "Без изменения"
            fields = ", ".join(variant[k] for k in ("text_key", "inspect_key", "buttons_key", "hints_key") if k in variant)
            scenario = variant.get("id", f"{scene['step']:03d}")
            lines.append(f"| {scenario} | {cell(when)} | {media_link} | {fields} |")
    lines += ["", "## Полные тексты сцен и сценариев возвращения", "",
              "Ниже перечислены все поля текстовых JSON. Описание, осмотр, причины отказа, подсказки и подписи кнопок можно найти по имени поля.",
              "Если подходят несколько вариантов, они применяются по порядку: каждый меняет только свои поля. Например, 007.04 меняет текст после отлёта птицы, сохраняя картинку клетки от предыдущего варианта.", ""]

    def text_rows(value, prefix=""):
        if isinstance(value, dict):
            for key, child in value.items():
                yield from text_rows(child, f"{prefix}.{key}" if prefix else key)
        elif isinstance(value, list):
            for index, child in enumerate(value):
                yield from text_rows(child, f"{prefix}[{index}]")
        else:
            # Preserve paragraph boundaries in long editable text.
            text = str(value).replace("|", "&#124;").replace("\n", "<br>")
            yield f"| {prefix} | {text} |"

    for sid, scene in ordered:
        path = scene["text_file"]
        lines += [f"### {scene['step']:03d} · {scene['title']}", "",
                  f"Источник: [редактировать JSON]({path}).", "",
                  "Базовое описание: text; осмотр: inspect. При возвращении используются эти же поля, если их не изменил подходящий вариант.", ""]
        for index, variant in enumerate(scene.get("variants", []), 1):
            scenario = variant.get("id", f"{scene['step']:03d}.V{index:02d}")
            fields = ", ".join(f"{k.removesuffix('_key')} → {variant[k]}" for k in ("text_key", "inspect_key", "buttons_key", "hints_key") if k in variant)
            lines.append(f"- **{scenario}** — {describe_condition(variant['when'], content)}. {fields or 'Меняется только изображение'}. Применяется и при возвращении.")
        lines += ["", "| Поле JSON | Полный текст |", "| --- | --- |"]
        lines.extend(text_rows(content["_text_sources"][path]))
        lines.append("")

    lines += ["", "## Полные тексты общих экранов, предметов и событий", "",
              "Эти строки добавляются к сценам по состоянию инвентаря, используются в рюкзаке, подсказках и дневнике. Значения в фигурных скобках подставляет бот; их имена нужно сохранять.", ""]
    for name, path in content["copy_files"].items():
        lines += [f"### {path.rsplit('/', 1)[-1]}", "", f"[Редактировать JSON]({path})", "",
                  "| Поле JSON | Полный текст |", "| --- | --- |"]
        lines.extend(text_rows(content["_text_sources"][path]))
        lines.append("")
    lines += ["", "[Стиль иллюстраций](media/СТИЛЬ.md).",
              "Шаги 007–009 — эпизод по мотивам Adventure, адаптированный для нашего бота. Шаги 010–062 — авторское продолжение. Четвёртый эпизод заканчивается сдачей слитка в доме 002. Затем в 013 доступна боковая галерея: 015–020 — загадка колоколов, ворота, короткий путь и Звёздный свод. После изучения карты на балконе 019 открывается маршрут 021–026: водосброс и архив хранителей. После чтения летописи у озера 012 доступен маршрут 027–032: каменные корни, зеркало и закрытый сад. Промпты: media/PROMPTS_021_026.md и media/PROMPTS_027_032.md. После осмотра павильона в саду 031 доступна лестница в башню: 033–038 — противовес, Око и терраса над долиной. Промпты: media/PROMPTS_033_038.md. После осмотра долины на кольце 037 доступен спуск: 039–044 — тропы, старая дорога и дом путников. Промпты: media/PROMPTS_039_044.md. После чтения записи в доме на дороге 043 доступен спуск к реке: 045–050 — цепной паром, две башни и семенной двор. Промпты: media/PROMPTS_045_050.md. После изучения семенного двора у башен 049 доступна боковая тропа: 051–056 — служебный спуск, запас семян и пробный посев. Промпты: media/PROMPTS_051_056.md. После посева на тропе 051 доступен дом смотрителя: 057–062 — уход за всходами и путь к перевалу. Промпты: media/PROMPTS_057_062.md. Всего 62 сцены и 12 эпизодов. Карта описывает реализованную часть нашей игры.", ""]
    return "\n".join(lines)


def write_catalog(content, path=None):
    target = path or (ROOT / "КАРТА_ШАГОВ.md")
    result = build_catalog(content)
    if target.exists() and target.read_text(encoding="utf-8") == result:
        return
    temporary = target.with_suffix(".md.tmp")
    temporary.write_text(result, encoding="utf-8")
    temporary.replace(target)


if __name__ == "__main__":
    write_catalog(load_content())
    print("Scene map updated.")
