"""Testes de fumaça das rotas Flask e de módulos utilitários.

Não acessam a rede: cobrem rotas de leitura, validação de parâmetros, o
``/health`` (com e sem scheduler) e funções puras (rate limit e classificação).
"""

import sys
from pathlib import Path

import pytest

# Coloca a raiz do projeto no sys.path (tests/ -> raiz).
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.app import create_app, iniciar_scheduler
from src.services import classificar
from src.utils.rate_limit import RateLimiter

_RAIZ_PROJETO = Path(__file__).resolve().parents[1]
_TEMPLATE_FAQ = _RAIZ_PROJETO / "src" / "web" / "templates" / "faq.html"


@pytest.fixture()
def client():
    """Cliente de teste do Flask com a app recém-criada."""
    app = create_app()
    app.config.update(TESTING=True)
    return app.test_client()


def test_index_200_com_csp(client):
    resposta = client.get("/")
    assert resposta.status_code == 200
    assert "Content-Security-Policy" in resposta.headers


def test_uf_detalhe_200(client):
    resposta = client.get("/uf/MG?documento=nfe&tp_amb=1")
    assert resposta.status_code == 200


def test_uf_invalida_404(client):
    resposta = client.get("/uf/xx")
    assert resposta.status_code == 404


def test_termos_200(client):
    assert client.get("/termos").status_code == 200


@pytest.mark.skipif(
    not _TEMPLATE_FAQ.exists(),
    reason="faq.html ainda não criado pela lane de design",
)
def test_faq_200(client):
    assert client.get("/faq").status_code == 200


def test_api_status(client):
    resposta = client.get("/api/status")
    assert resposta.status_code == 200
    dados = resposta.get_json()
    assert isinstance(dados["celulas"], list)
    for celula in dados["celulas"]:
        assert "rotulo" in celula


def test_api_uf_historico(client):
    resposta = client.get("/api/uf/MG/historico?horas=24&documento=nfe&tp_amb=1")
    assert resposta.status_code == 200
    dados = resposta.get_json()
    assert "pontos" in dados
    assert "uptime_pct" in dados
    assert "ultimo" in dados


def test_api_historico_tp_amb_invalido(client):
    resposta = client.get("/api/uf/MG/historico?horas=24&tp_amb=99")
    assert resposta.status_code == 400


def test_api_historico_horas_invalido(client):
    resposta = client.get("/api/uf/MG/historico?horas=0&tp_amb=1")
    assert resposta.status_code == 400


def test_api_historico_documento_invalido(client):
    resposta = client.get(
        "/api/uf/MG/historico?horas=24&documento=inexistente&tp_amb=1"
    )
    assert resposta.status_code == 400


def test_health_sem_e_com_scheduler():
    app = create_app()
    app.config.update(TESTING=True)
    cliente = app.test_client()

    # Sem scheduler: banco acessível, scheduler inativo -> 503 "erro".
    resposta = cliente.get("/health")
    assert resposta.status_code == 503
    assert resposta.get_json()["status"] == "erro"

    scheduler = iniciar_scheduler()
    try:
        resposta = cliente.get("/health")
        assert resposta.status_code == 200
        assert resposta.get_json()["status"] == "ok"
    finally:
        scheduler.shutdown(wait=False)


def test_rate_limiter_janela():
    limiter = RateLimiter(2, 60)
    assert limiter.consome("ip-teste") is True
    assert limiter.consome("ip-teste") is True
    assert limiter.consome("ip-teste") is False


def test_classificar_rotulos():
    assert classificar.rotulo_estado("operacional") == "Operacional"
    assert classificar.rotulo_estado(None) == "Sem dados"
