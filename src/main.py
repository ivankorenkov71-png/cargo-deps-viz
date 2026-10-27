"""Визуализатор графа зависимостей пакетов Rust (Cargo)."""

import argparse
import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

DEFAULT_REPO = "https://index.crates.io"
CRATE_NAME_RE = re.compile(r"[A-Za-z][A-Za-z0-9_-]*")
TEST_NAME_RE = re.compile(r"[A-Z]+")
MAX_CRATE_NAME_LEN = 64
SHORT_NAME_LEN = 2   # имена из 1-2 букв лежат в папках "1/" и "2/"
MIDDLE_NAME_LEN = 3  # имена из 3 букв лежат в папке "3/<первая буква>/"
TIMEOUT = 15         # сколько секунд ждать ответа от репозитория


def parse_args(argv):
    """Разбирает опции командной строки и возвращает их."""
    parser = argparse.ArgumentParser(
        description="Граф зависимостей пакетов Rust (Cargo)")
    parser.add_argument("-p", "--package", required=True,
                        help="имя анализируемого пакета")
    parser.add_argument("-r", "--repo", default=DEFAULT_REPO,
                        help="URL репозитория или путь к тестовому файлу")
    parser.add_argument("-t", "--test-mode", action="store_true",
                        help="работать с тестовым репозиторием (файлом)")
    parser.add_argument("-o", "--output", default="graph.svg",
                        help="имя файла с изображением графа (.svg)")
    parser.add_argument("-f", "--filter", default="",
                        help="пропускать пакеты, имя которых содержит "
                             "эту подстроку")
    return parser.parse_args(argv)


def check_package(name, test_mode):
    """Проверяет имя пакета; при ошибке выбрасывает ValueError."""
    if test_mode:
        if not TEST_NAME_RE.fullmatch(name):
            raise ValueError(
                f"в тестовом режиме имя пакета пишется большими "
                f"латинскими буквами (например, A), а не '{name}'")
        return
    if not CRATE_NAME_RE.fullmatch(name):
        raise ValueError(
            f"недопустимое имя пакета '{name}': разрешены латинские "
            f"буквы, цифры, '-' и '_', первым символом — буква")
    if len(name) > MAX_CRATE_NAME_LEN:
        raise ValueError(
            f"имя пакета длиннее {MAX_CRATE_NAME_LEN} символов")


def check_repo(repo, test_mode):
    """Проверяет URL репозитория или путь к тестовому файлу."""
    if test_mode:
        if not Path(repo).is_file():
            raise ValueError(
                f"файл тестового репозитория не найден: {repo}")
        return
    if not repo.startswith(("http://", "https://")):
        raise ValueError(
            f"URL репозитория должен начинаться с http:// или "
            f"https://, а получено '{repo}' (для тестового файла "
            f"добавьте опцию --test-mode)")


def check_output(output):
    """Проверяет имя файла, в который будет сохранено изображение."""
    path = Path(output)
    if path.suffix.lower() != ".svg":
        raise ValueError(
            f"файл изображения должен иметь расширение .svg, "
            f"а получено '{output}'")
    if not path.parent.is_dir():
        raise ValueError(
            f"папка для изображения не существует: {path.parent}")


def check_filter(text, package):
    """Проверяет подстроку для фильтрации пакетов."""
    if any(char.isspace() for char in text):
        raise ValueError("подстрока фильтра не должна содержать пробелов")
    if text and text in package:
        raise ValueError(
            f"анализируемый пакет '{package}' сам содержит "
            f"подстроку фильтра '{text}'")


def validate_args(args):
    """Проверяет все параметры по очереди."""
    check_package(args.package, args.test_mode)
    check_repo(args.repo, args.test_mode)
    check_output(args.output)
    check_filter(args.filter, args.package)


def index_path(name):
    """Возвращает путь к файлу пакета внутри индекса crates.io.

    Индекс раскладывает пакеты по папкам в зависимости от длины имени:
    a -> 1/a, ab -> 2/ab, abc -> 3/a/abc, serde -> se/rd/serde.
    """
    name = name.lower()
    if len(name) <= SHORT_NAME_LEN:
        return f"{len(name)}/{name}"
    if len(name) == MIDDLE_NAME_LEN:
        return f"3/{name[0]}/{name}"
    return f"{name[:2]}/{name[2:4]}/{name}"


def download_index(name, repo):
    """Скачивает файл пакета из репозитория и возвращает его текст."""
    url = f"{repo.rstrip('/')}/{index_path(name)}"
    request = urllib.request.Request(
        url, headers={"User-Agent": "cargo-deps-viz (student project)"})
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as answer:
            return answer.read().decode("utf-8")
    except urllib.error.HTTPError as error:
        raise ValueError(
            f"репозиторий ответил ошибкой {error.code} на {url} "
            f"(скорее всего, пакета '{name}' не существует)") from error
    except OSError as error:
        raise ValueError(
            f"не удалось подключиться к {url}: {error}") from error


def version_key(version):
    """Превращает строку версии '1.0.130' в (1, 0, 130) для сравнения."""
    numbers = version.split("+")[0].split("-")[0]
    return tuple(int(part) for part in numbers.split("."))


def choose_version(text):
    """Выбирает из текста индекса самую новую рабочую версию пакета.

    Каждая строка индекса - это JSON с одной версией пакета.
    Отозванные версии (yanked) пропускаются, предварительные
    (например, 2.0.0-beta) берутся, только если других нет.
    """
    try:
        versions = [json.loads(line) for line in text.splitlines()
                    if line.strip()]
    except json.JSONDecodeError as error:
        raise ValueError(
            "ответ репозитория не похож на индекс Cargo") from error
    alive = [ver for ver in versions if not ver.get("yanked")]
    stable = [ver for ver in alive if "-" not in ver["vers"]]
    candidates = stable or alive
    if not candidates:
        raise ValueError("у пакета нет ни одной доступной версии")
    return max(candidates, key=lambda ver: version_key(ver["vers"]))


def direct_deps(version):
    """Возвращает имена прямых зависимостей одной версии пакета.

    Пропускаются dev-зависимости (нужны только для тестов самого
    пакета) и необязательные (optional) - Cargo по умолчанию их
    не скачивает. Если зависимость переименована, у неё есть поле
    package с настоящим именем пакета.
    """
    names = []
    for dep in version["deps"]:
        if dep.get("kind") == "dev" or dep.get("optional"):
            continue
        name = dep.get("package") or dep["name"]
        if name not in names:
            names.append(name)
    return names


def fetch_deps(name, repo):
    """Получает прямые зависимости пакета из настоящего репозитория."""
    version = choose_version(download_index(name, repo))
    return direct_deps(version)


def read_test_repo(path):
    """Читает тестовый репозиторий из файла.

    Каждая строка файла: 'ПАКЕТ: ЗАВИСИМОСТЬ ЗАВИСИМОСТЬ ...',
    например 'A: B C'. Пустые строки и строки с # пропускаются.
    Возвращает словарь {'A': ['B', 'C'], ...}.
    """
    test_graph = {}
    lines = Path(path).read_text(encoding="utf-8").splitlines()
    for number, line in enumerate(lines, start=1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if ":" not in line:
            raise ValueError(f"{path}, строка {number}: нет двоеточия")
        name, deps = line.split(":", 1)
        names = [name.strip()] + deps.split()
        for item in names:
            if not TEST_NAME_RE.fullmatch(item):
                raise ValueError(
                    f"{path}, строка {number}: имя '{item}' должно "
                    f"состоять из больших латинских букв")
        test_graph[names[0]] = names[1:]
    return test_graph


def get_deps(name, args, test_graph):
    """Прямые зависимости пакета: из тестового файла или из сети."""
    if args.test_mode:
        return test_graph.get(name, [])
    return fetch_deps(name, args.repo)


def is_filtered(name, text):
    """Проверяет, нужно ли пропустить пакет (в имени есть подстрока)."""
    return bool(text) and text in name


def bfs(level, graph, args, test_graph):
    """Обход графа в ширину (BFS), записанный через рекурсию.

    level - пакеты текущего уровня (сначала только сам пакет).
    graph - словарь уже обработанных пакетов: {пакет: [зависимости]}.
    Один вызов функции обрабатывает один уровень и вызывает сам себя
    для следующего уровня. Пакет, который уже есть в graph, второй
    раз не обрабатывается - поэтому циклы A -> B -> A не зацикливают
    программу.
    """
    next_level = []
    for name in level:
        deps = [dep for dep in get_deps(name, args, test_graph)
                if not is_filtered(dep, args.filter)]
        graph[name] = deps
        for dep in deps:
            if dep not in graph and dep not in level + next_level:
                next_level.append(dep)
    if next_level:
        bfs(next_level, graph, args, test_graph)
    return graph


def build_graph(args):
    """Строит полный граф зависимостей пакета args.package."""
    test_graph = None
    if args.test_mode:
        test_graph = read_test_repo(args.repo)
        if args.package not in test_graph:
            raise ValueError(
                f"пакета {args.package} нет в тестовом репозитории")
    return bfs([args.package], {}, args, test_graph)


def print_graph(graph):
    """Выводит граф: каждая строка - пакет и его прямые зависимости."""
    for name, deps in graph.items():
        print(f"{name} -> {', '.join(deps) or '(нет зависимостей)'}")


def main(argv=None):
    """Точка входа: проверяет параметры и выводит граф зависимостей."""
    args = parse_args(argv)
    try:
        validate_args(args)
        graph = build_graph(args)
    except ValueError as error:
        print(f"Ошибка: {error}", file=sys.stderr)
        return 1
    print_graph(graph)
    return 0


if __name__ == "__main__":
    sys.exit(main())
