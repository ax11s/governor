def load(name):
    with open("prompts/" + name + ".txt", encoding="utf-8") as f:
        return f.read().strip()


def fill(name, blanks):
    text = load(name)
    for blank in blanks:
        text = text.replace("{" + blank + "}", str(blanks[blank]))
    return text


def choices(name):
    result = {}
    for line in load(name).splitlines():
        if ":" in line:
            key, text = line.split(":", 1)
            result[key.strip()] = text.strip()
    return result
