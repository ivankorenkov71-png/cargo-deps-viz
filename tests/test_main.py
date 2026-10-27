"""Тесты визуализатора графа зависимостей."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import main  # noqa: E402


class CheckArgsTest(unittest.TestCase):
    """Проверка обработки ошибок в параметрах."""

    def test_good_crate_name(self):
        """Правильное имя пакета не вызывает ошибку."""
        main.check_package("serde_json", test_mode=False)

    def test_bad_crate_name(self):
        """Имя с недопустимыми символами отклоняется."""
        with self.assertRaises(ValueError):
            main.check_package("serde json!", test_mode=False)

    def test_test_mode_name(self):
        """В тестовом режиме разрешены только большие буквы."""
        main.check_package("A", test_mode=True)
        with self.assertRaises(ValueError):
            main.check_package("a1", test_mode=True)

    def test_repo_url(self):
        """URL без http:// или https:// отклоняется."""
        main.check_repo("https://index.crates.io", test_mode=False)
        with self.assertRaises(ValueError):
            main.check_repo("index.crates.io", test_mode=False)

    def test_missing_test_file(self):
        """Несуществующий тестовый файл отклоняется."""
        with self.assertRaises(ValueError):
            main.check_repo("no_such_file.txt", test_mode=True)

    def test_output_extension(self):
        """Файл изображения должен иметь расширение .svg."""
        main.check_output("graph.svg")
        with self.assertRaises(ValueError):
            main.check_output("graph.png")

    def test_filter(self):
        """Фильтр с пробелом или совпадающий с пакетом отклоняется."""
        main.check_filter("derive", "serde_json")
        with self.assertRaises(ValueError):
            main.check_filter("a b", "serde_json")
        with self.assertRaises(ValueError):
            main.check_filter("json", "serde_json")


SAMPLE_INDEX = "\n".join([
    '{"name": "demo", "vers": "1.0.0", "yanked": false, "deps": []}',
    '{"name": "demo", "vers": "1.2.0", "yanked": false, "deps": ['
    '{"name": "itoa", "kind": "normal", "optional": false},'
    '{"name": "rand", "kind": "dev", "optional": false},'
    '{"name": "indexmap", "kind": "normal", "optional": true},'
    '{"name": "my_log", "package": "log", "kind": "normal",'
    ' "optional": false}]}',
    '{"name": "demo", "vers": "1.3.0", "yanked": true, "deps": []}',
    '{"name": "demo", "vers": "2.0.0-beta", "yanked": false, "deps": []}',
])


class CollectDataTest(unittest.TestCase):
    """Проверка этапа 2: разбор индекса crates.io."""

    def test_index_path(self):
        """Путь к файлу пакета зависит от длины имени."""
        self.assertEqual(main.index_path("a"), "1/a")
        self.assertEqual(main.index_path("ab"), "2/ab")
        self.assertEqual(main.index_path("syn"), "3/s/syn")
        self.assertEqual(main.index_path("Serde"), "se/rd/serde")

    def test_choose_version(self):
        """Берётся самая новая не отозванная и не beta-версия."""
        version = main.choose_version(SAMPLE_INDEX)
        self.assertEqual(version["vers"], "1.2.0")

    def test_direct_deps(self):
        """Dev и optional пропускаются, переименование учитывается."""
        version = main.choose_version(SAMPLE_INDEX)
        self.assertEqual(main.direct_deps(version), ["itoa", "log"])

    def test_not_index(self):
        """Ответ, который не является индексом, даёт понятную ошибку."""
        with self.assertRaises(ValueError):
            main.choose_version("<html>Not found</html>")


if __name__ == "__main__":
    unittest.main()
