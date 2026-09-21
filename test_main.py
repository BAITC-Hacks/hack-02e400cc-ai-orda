"""Behavior checks for the offline FAQ matcher and its terminal interface."""

import copy
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import main


PROJECT_DIR = Path(__file__).resolve().parent


class AnswerMatchingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.entries = main.load_faq()
        cls.answers = {entry.topic: entry.answer for entry in cls.entries}

    def assertTopic(self, question, topic):
        self.assertEqual(main.find_answer(question, self.entries), self.answers[topic])

    def test_all_five_canonical_questions(self):
        self.assertEqual(
            set(self.answers), {"time", "team", "track", "submission", "prizes"}
        )
        for entry in self.entries:
            with self.subTest(topic=entry.topic):
                self.assertTopic(entry.question, entry.topic)

    def test_russian_and_kazakh_paraphrases(self):
        questions = {
            "time": [
                "Во сколько начинается репетиция?",
                "Репетиция қашан басталады?",
                "Репетицияның уақыты қандай?",
            ],
            "team": [
                "Как называется наша команда?",
                "Біздің команданың аты қандай?",
                "Командаға қанша адам кіреді?",
            ],
            "track": [
                "Какой у нас трек?",
                "Қай тректі таңдадық?",
                "Нужно ли делать RAG?",
            ],
            "submission": [
                "Куда загрузить решение?",
                "Как сдать работу?",
                "Шешімді қайда тапсырамыз?",
                "Шешімді қалай тапсыру керек?",
            ],
            "prizes": [
                "Будут ли призы?",
                "Сыйлық бар ма?",
                "Жүлделер бар ма?",
            ],
        }
        for topic, variants in questions.items():
            for question in variants:
                with self.subTest(topic=topic, question=question):
                    self.assertTopic(question, topic)

    def test_deadlines_are_time_questions(self):
        for question in (
            "Когда сдавать решение?",
            "До какого числа сдать работу?",
            "До скольки загрузить решение?",
            "Шешімді қашан тапсырамыз?",
            "Шешімді қашан тапсыру керек?",
        ):
            with self.subTest(question=question):
                self.assertTopic(question, "time")

    def test_case_punctuation_and_unicode_normalization(self):
        for question in (
            "  ЖҮЛДЕЛЕР БАР МА?!  ",
            "Сыйлық\tбар\nма???",
            "ЕЩЁ ПРИЗЫ БУДУТ?",
        ):
            with self.subTest(question=question):
                self.assertTopic(question, "prizes")
        self.assertTopic("Нужен ＲＡＧ?", "track")

    def test_unknown_and_empty_questions(self):
        for question in (
            "Ауа райы қандай?",
            "Какая погода?",
            "Что такое Python?",
            "Когда?",
            "Қалай?",
            "",
            "   \n\t ",
            "...?! —",
        ):
            with self.subTest(question=question):
                self.assertEqual(main.find_answer(question, self.entries), "не знаю")

    def test_keywords_do_not_match_inside_unrelated_words(self):
        for question in (
            "командировка",
            "трекер",
            "призрак",
            "GitHubber",
            "ragtime",
        ):
            with self.subTest(question=question):
                self.assertEqual(main.find_answer(question, self.entries), "не знаю")

    def test_equal_topic_matches_are_ambiguous(self):
        for question in (
            "Призы и команда?",
            "Трек және сыйлық?",
            "Призы призы призы и команда?",
        ):
            with self.subTest(question=question):
                self.assertEqual(main.find_answer(question, self.entries), "не знаю")

    def test_specific_phrase_disambiguates_other_topic_keyword(self):
        self.assertTopic("Как сдать задание?", "submission")
        self.assertTopic("Команда шешімді қашан тапсыру керек?", "time")

    def test_phrase_must_be_contiguous(self):
        self.assertEqual(
            main.find_answer("во всем сколько угодно", self.entries), "не знаю"
        )


class FAQFileTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "faq.txt"
        self.data = json.loads(main.FAQ_PATH.read_text(encoding="utf-8"))

    def write_faq(self, data):
        self.path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    def test_answers_come_from_editable_faq_file(self):
        for record in self.data:
            record["answer"] = "Өзгертілген жауап: " + record["topic"]
        self.write_faq(self.data)
        entries = main.load_faq(self.path)
        for record in self.data:
            with self.subTest(topic=record["topic"]):
                self.assertEqual(
                    main.find_answer(record["question"], entries), record["answer"]
                )
        self.assertEqual(
            main.find_answer("Сыйлық бар ма?", entries), "Өзгертілген жауап: prizes"
        )

    def test_exact_question_works_without_matching_its_keywords(self):
        self.data[0]["question"] = "Репетицияға қатысты бірінші сұрақ?"
        self.data[0]["keywords"] = ["арнайыбелгі"]
        self.write_faq(self.data)
        self.assertEqual(
            main.find_answer(
                "РЕПЕТИЦИЯҒА ҚАТЫСТЫ БІРІНШІ СҰРАҚ!", main.load_faq(self.path)
            ),
            self.data[0]["answer"],
        )

    def test_rejects_wrong_record_count_or_root_shape(self):
        for data in ([], self.data[:4], self.data + [self.data[0]], {}):
            with self.subTest(data=data):
                self.write_faq(data)
                with self.assertRaises(ValueError):
                    main.load_faq(self.path)

    def test_rejects_duplicate_topic_or_normalized_question(self):
        for field in ("topic", "question"):
            with self.subTest(field=field):
                data = copy.deepcopy(self.data)
                data[1][field] = data[0][field]
                if field == "question":
                    data[1][field] = data[1][field].upper() + " !!!"
                self.write_faq(data)
                with self.assertRaises(ValueError):
                    main.load_faq(self.path)

    def test_rejects_invalid_required_fields(self):
        for field in ("topic", "question", "answer"):
            for invalid in ("", "   ", None, 12):
                with self.subTest(field=field, invalid=invalid):
                    data = copy.deepcopy(self.data)
                    data[0][field] = invalid
                    self.write_faq(data)
                    with self.assertRaises(ValueError):
                        main.load_faq(self.path)

    def test_rejects_invalid_keywords(self):
        for invalid in ([], "призы", [None], [""], ["?!"]):
            with self.subTest(invalid=invalid):
                data = copy.deepcopy(self.data)
                data[0]["keywords"] = invalid
                self.write_faq(data)
                with self.assertRaises(ValueError):
                    main.load_faq(self.path)


class TerminalTests(unittest.TestCase):
    def run_cli(self, script, cwd, input_text=""):
        return subprocess.run(
            [sys.executable, str(script)],
            input=input_text,
            text=True,
            encoding="utf-8",
            capture_output=True,
            cwd=cwd,
            timeout=10,
            check=False,
        )

    def test_cli_loads_faq_from_script_directory(self):
        with tempfile.TemporaryDirectory() as elsewhere:
            result = self.run_cli(
                PROJECT_DIR / "main.py", elsewhere,
                "Сыйлық бар ма?\nАуа райы қандай?\nшығу\n",
            )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "")
        self.assertIn("Бұл репетицияда сыйлықтар жоқ.", result.stdout)
        self.assertIn("не знаю", result.stdout)

    def test_eof_exits_cleanly(self):
        with tempfile.TemporaryDirectory() as elsewhere:
            result = self.run_cli(PROJECT_DIR / "main.py", elsewhere)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "")
        self.assertNotIn("не знаю", result.stdout)

    def test_all_exit_commands_stop_before_next_question(self):
        with tempfile.TemporaryDirectory() as elsewhere:
            for command in ("EXIT", "quit", "ШЫҒУ", "выход"):
                with self.subTest(command=command):
                    result = self.run_cli(
                        PROJECT_DIR / "main.py", elsewhere,
                        command + "\nСыйлық бар ма?\n",
                    )
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertEqual(result.stderr, "")
                    self.assertNotIn("Бұл репетицияда сыйлықтар жоқ.", result.stdout)

    def test_missing_or_invalid_faq_reports_error_without_traceback(self):
        for contents in (None, "not JSON", "[]", "{}"):
            with self.subTest(contents=contents):
                with tempfile.TemporaryDirectory() as directory:
                    temp_dir = Path(directory)
                    script = temp_dir / "main.py"
                    shutil.copyfile(PROJECT_DIR / "main.py", script)
                    if contents is not None:
                        (temp_dir / "faq.txt").write_text(contents, encoding="utf-8")
                    result = self.run_cli(script, directory)
                self.assertEqual(result.returncode, 1)
                self.assertIn("FAQ файлын оқу қатесі:", result.stderr)
                self.assertNotIn("Traceback", result.stderr)
                self.assertNotIn("AI ORDA FAQ:", result.stdout)


if __name__ == "__main__":
    unittest.main()
