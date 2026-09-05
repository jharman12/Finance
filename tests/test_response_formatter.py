from __future__ import annotations

import unittest

from finance_app.models import AssistantResult
from finance_app.services.response_formatter import format_assistant_response


class ResponseFormatterTests(unittest.TestCase):
    def test_display_text_preserves_original_reply(self) -> None:
        reply = "## Summary\n- Spent **$25.50** on groceries"
        formatted = format_assistant_response(AssistantResult(reply=reply))

        self.assertEqual(formatted.display_text, reply)

    def test_audio_script_strips_markdown(self) -> None:
        reply = "## Summary\n- Spent money on **groceries**\n* Saved cash"
        formatted = format_assistant_response(AssistantResult(reply=reply))

        self.assertNotIn("#", formatted.audio_script)
        self.assertNotIn("*", formatted.audio_script)
        self.assertIn("Summary", formatted.audio_script)
        self.assertIn("groceries", formatted.audio_script)

    def test_audio_script_speaks_currency(self) -> None:
        formatted = format_assistant_response(AssistantResult(reply="You spent $1,250.75 this month"))

        self.assertIn("1250 dollars and 75 cents", formatted.audio_script)

    def test_audio_script_speaks_whole_dollars(self) -> None:
        formatted = format_assistant_response(AssistantResult(reply="Budget is $300"))

        self.assertIn("300 dollars", formatted.audio_script)
        self.assertNotIn("cents", formatted.audio_script)

    def test_table_rows_flattened_for_speech(self) -> None:
        reply = "| Category | Amount |\n| --- | --- |\n| Food | 100 |"
        formatted = format_assistant_response(AssistantResult(reply=reply))

        self.assertNotIn("|", formatted.audio_script)
        self.assertNotIn("---", formatted.audio_script)
        self.assertIn("Food", formatted.audio_script)

    def test_long_reply_is_truncated_for_speech(self) -> None:
        reply = " ".join(f"Sentence number {index}." for index in range(200))
        formatted = format_assistant_response(AssistantResult(reply=reply), max_audio_chars=100)

        self.assertTrue(formatted.truncated)
        self.assertLessEqual(len(formatted.audio_script), 100)

    def test_empty_reply_falls_back_to_action_summary(self) -> None:
        result = AssistantResult(reply="")
        result.applied_actions = ["Added expense 25 groceries"]
        formatted = format_assistant_response(result)

        self.assertEqual(formatted.display_text, "")
        self.assertIn("Added expense 25 groceries", formatted.audio_script)

    def test_multiple_actions_summarized(self) -> None:
        result = AssistantResult(reply="")
        result.applied_actions = ["one", "two", "three"]
        formatted = format_assistant_response(result)

        self.assertIn("3 updates", formatted.audio_script)


if __name__ == "__main__":
    unittest.main()
