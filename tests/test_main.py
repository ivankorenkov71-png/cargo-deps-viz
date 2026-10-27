"""Тесты визуализатора графа зависимостей."""

import importlib
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

main = importlib.import_module("main")

EXAMPLES = Path(__file__).resolve().parent.parent / "examples"


def graph_from_file(package, file_name, text=""):
    """Строит граф по тестовому репозиторию из папки examples."""
    argv = ["-p", package, "-r", str(EXAMPLES / file_name), "-t",
            "-f", text]
    return main.build_graph(main.parse_args(argv))


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


class GraphTest(unittest.TestCase):
    """Проверка этапа 3: BFS, фильтр, циклы, тестовый режим."""

    def test_simple(self):
        """Транзитивная зависимость C попадает в граф один раз."""
        graph = graph_from_file("A", "simple.txt")
        self.assertEqual(graph, {"A": ["B", "C"], "B": ["C"], "C": []})

    def test_bfs_order(self):
        """Пакеты обходятся по уровням: сначала B, C, D, потом E..."""
        graph = graph_from_file("A", "big.txt")
        self.assertEqual(list(graph), list("ABCDEFGHIJ"))

    def test_filter(self):
        """Пакет с подстрокой фильтра и всё, что только через него, - нет."""
        graph = graph_from_file("D", "big.txt", text="G")
        self.assertEqual(graph, {"D": ["H"], "H": []})

    def test_cycle(self):
        """Цикл A -> B -> C -> A не приводит к зависанию."""
        graph = graph_from_file("A", "cycle.txt")
        self.assertEqual(graph["C"], ["A", "D"])
        self.assertEqual(len(graph), 4)

    def test_unknown_package(self):
        """Пакета нет в тестовом файле - понятная ошибка."""
        with self.assertRaises(ValueError):
            graph_from_file("Z", "big.txt")

    def test_bad_file(self):
        """Маленькие буквы в тестовом файле - ошибка."""
        with self.assertRaises(ValueError):
            graph_from_file("A", "bad.txt")


class LoadOrderTest(unittest.TestCase):
    """Проверка этапа 4: порядок загрузки зависимостей."""

    def test_simple_order(self):
        """C ни от кого не зависит - он первый, A - последний."""
        graph = graph_from_file("A", "simple.txt")
        order, cycles = main.load_order(graph, "A")
        self.assertEqual(order, ["C", "B", "A"])
        self.assertEqual(cycles, [])

    def test_deps_before_package(self):
        """Каждый пакет стоит в списке позже всех своих зависимостей."""
        graph = graph_from_file("A", "big.txt")
        order, _ = main.load_order(graph, "A")
        for name, deps in graph.items():
            for dep in deps:
                self.assertLess(order.index(dep), order.index(name))

    def test_cycle_found(self):
        """Цикл A -> B -> C -> A находится и выводится."""
        graph = graph_from_file("A", "cycle.txt")
        order, cycles = main.load_order(graph, "A")
        self.assertEqual(cycles, [["A", "B", "C", "A"]])
        self.assertEqual(sorted(order), ["A", "B", "C", "D"])


class MermaidTest(unittest.TestCase):
    """Проверка этапа 5: текст диаграммы Mermaid."""

    def test_simple_mermaid(self):
        """Каждая зависимость - стрелка, пакет без зависимостей - узел."""
        graph = graph_from_file("A", "simple.txt")
        text = main.to_mermaid(graph)
        self.assertEqual(text, "graph TD\n"
                               "    A --> B\n"
                               "    A --> C\n"
                               "    B --> C\n"
                               "    C\n")

    def test_name_with_dash(self):
        """Дефис убирается из служебного имени, но остаётся в подписи."""
        text = main.to_mermaid({"proc-macro2": []})
        self.assertIn('proc_macro2["proc-macro2"]', text)


if __name__ == "__main__":
    unittest.main()
