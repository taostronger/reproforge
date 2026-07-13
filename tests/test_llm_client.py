import json
import re
from unittest.mock import patch, MagicMock
from llm.client import chat, chat_json

def test_chat_returns_content():
    with patch("llm.client.OpenAI") as MockOpenAI:
        mock_client = MockOpenAI.return_value
        mock_response = MagicMock(choices=[MagicMock(message=MagicMock(content="hello"))])
        mock_client.chat.completions.create.return_value = mock_response
        assert chat([{"role":"user","content":"hi"}]) == "hello"

def test_chat_json_parses_json():
    with patch("llm.client.OpenAI") as MockOpenAI:
        mock_client = MockOpenAI.return_value
        mock_response = MagicMock(choices=[MagicMock(message=MagicMock(content='{"a":1}'))])
        mock_client.chat.completions.create.return_value = mock_response
        assert chat_json([{"role":"user","content":"x"}]) == {"a":1}
