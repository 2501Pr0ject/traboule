"""Configuration du modèle de génération (configs/llm.yaml)."""

import pytest

from traboule.generation.llm_config import LlmConfigError, load_llm_config

VALID = """\
url: http://localhost:11434
model: qwen3:8b
tokenizer: Qwen/Qwen3-8B
think: false
keep_alive: 30m
options:
  temperature: 0
  seed: 1
  num_predict: 256
num_ctx:
  rag: 1024
  kag: 1024
  cag: 2048
"""


def _write(tmp_path, text):
    path = tmp_path / "llm.yaml"
    path.write_text(text, encoding="utf-8")
    return path


def test_repository_config_matches_the_owner_decision():
    config = load_llm_config()
    assert config.model == "qwen3:8b"
    assert config.think is False
    assert config.keep_alive == "30m"
    assert config.options.temperature == 0
    assert config.options.seed == 20261102
    assert config.options.num_predict == 1024
    assert config.tokenizer == "Qwen/Qwen3-8B"
    assert (config.num_ctx.rag, config.num_ctx.kag, config.num_ctx.cag) == (16384, 16384, 22528)


def test_ollama_request_uses_the_window_of_each_strategy():
    config = load_llm_config()
    rag, cag = config.ollama_request("rag"), config.ollama_request("cag")
    assert rag["model"] == "qwen3:8b"
    assert rag["think"] is False
    assert rag["options"] == {
        "temperature": 0,
        "seed": 20261102,
        "num_predict": 1024,
        "num_ctx": 16384,
    }
    assert cag["options"]["num_ctx"] == 22528
    assert config.ollama_request("kag")["options"]["num_ctx"] == 16384


def test_valid_file_is_loaded(tmp_path):
    config = load_llm_config(_write(tmp_path, VALID))
    options = config.ollama_request("cag")["options"]
    assert options == {"temperature": 0, "seed": 1, "num_predict": 256, "num_ctx": 2048}


def test_input_budget_reserves_the_answer():
    config = load_llm_config()
    assert config.input_budget("cag") == 22528 - 1024
    assert config.input_budget("rag") == 16384 - 1024


@pytest.mark.parametrize(
    ("old", "new"),
    [
        ("  seed: 1\n", "  seed: 1\n  temprature: 0\n"),  # option mal orthographiée
        ("  seed: 1\n", "  seed: 1\n  num_ctx: 4096\n"),  # fenêtre hors de num_ctx
        ("  cag: 2048\n", ""),  # stratégie sans fenêtre
        ("  rag: 1024\n", "  rag: 0\n"),  # fenêtre nulle
        ("  temperature: 0\n", "  temperature: -1\n"),
        ("think: false\n", ""),  # mode réflexion non précisé
        ("  num_predict: 256\n", ""),  # réponse sans plafond
        ("url: http://localhost:11434\n", "url: localhost:11434\n"),
    ],
)
def test_invalid_file_is_refused(tmp_path, old, new):
    assert old in VALID
    with pytest.raises(LlmConfigError):
        load_llm_config(_write(tmp_path, VALID.replace(old, new)))
