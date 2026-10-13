"""Визуализатор графа зависимостей пакетов Rust (Cargo)."""

import argparse
import re
import sys
from pathlib import Path

DEFAULT_REPO = "https://index.crates.io"
CRATE_NAME_RE = re.compile(r"[A-Za-z][A-Za-z0-9_-]*")
TEST_NAME_RE = re.compile(r"[A-Z]+")
MAX_CRATE_NAME_LEN = 64


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


def print_config(args):
    """Выводит все параметры в формате «ключ = значение»."""
    for key, value in vars(args).items():
        print(f"{key} = {value}")


def main(argv=None):
    """Точка входа: разбирает и проверяет параметры."""
    args = parse_args(argv)
    try:
        validate_args(args)
    except ValueError as error:
        print(f"Ошибка: {error}", file=sys.stderr)
        return 1
    print_config(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
