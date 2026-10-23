"""Testes da conversão de valores da API no ciclo de coleta."""

import sys
from pathlib import Path

# Coloca a raiz do projeto no sys.path (tests/ -> raiz).
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.jobs.coletar import _int_ou_none, _tmed_para_ms


def test_tmed_segundos_inteiro_vira_ms():
    assert _tmed_para_ms(1) == 1000


def test_tmed_string_vira_ms():
    assert _tmed_para_ms("1") == 1000


def test_tmed_fracionado_arredonda_ms():
    assert _tmed_para_ms(0.432) == 432


def test_tmed_zero():
    assert _tmed_para_ms("0") == 0


def test_tmed_ausente_ou_invalido():
    assert _tmed_para_ms(None) is None
    assert _tmed_para_ms("") is None
    assert _tmed_para_ms("abc") is None


def test_int_ou_none():
    assert _int_ou_none("115") == 115
    assert _int_ou_none(None) is None
    assert _int_ou_none("") is None
