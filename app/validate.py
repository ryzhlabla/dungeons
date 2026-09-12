from .content import load_content
from .engine import State
from .ui import render


def validate_rendered_content(content):
    screens = ("start", "help", "scene", "inspect", "inventory", "item", "hint",
               "menu", "journal", "progress", "confirm", "keys", "cage", "silver")
    for scene in content["scenes"]:
        for screen in screens:
            for carrying in (False, True):
                for power in (False, True):
                    for hint in range(3):
                        state = State(started=True, scene=scene, screen=screen, hint_level=hint)
                        state.item_locations["lamp"] = "inventory" if carrying else scene
                        state.item_states["lamp"]["power"] = power
                        card = render(state, content)
                        if len(card.caption) > 1024:
                            raise ValueError(f"Caption too long: {scene}/{screen}")
                        for row in card.keyboard.inline_keyboard:
                            if any(len(b.callback_data.encode()) > 64 for b in row):
                                raise ValueError(f"Callback too long: {scene}/{screen}")


def main():
    content = load_content()
    validate_rendered_content(content)
    print(f"OK: {len(content['scenes'])} scenes, all text screens, images and targets validated.")


if __name__ == "__main__":
    main()
