"""Testes de fumaça das rotas Flask e de módulos utilitários.

Não acessam a rede: cobrem rotas de leitura, validação de parâmetros, o
``/health`` (com e sem scheduler) e funções puras (rate limit e classificação).
"""

import sys
from pathlib import Path

import pytest

# Coloca a raiz do projeto no sys.path (tests/ -> raiz).
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.app import (
    _historico_geral,
    _modelos_ativos,
    create_app,
    iniciar_scheduler,
)
from src.services import classificar
from src.utils.rate_limit import RateLimiter

_RAIZ_PROJETO = Path(__file__).resolve().parents[1]


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
    # Fonte única: a raiz serve o painel estático (frontend/index.html).
    assert 'data-page="index"' in resposta.get_data(as_text=True)


def test_uf_detalhe_redireciona_para_pagina_estatica(client):
    resposta = client.get("/uf/MG?documento=nfe&tp_amb=1")
    assert resposta.status_code == 302
    assert "/detalhe.html?uf=MG" in resposta.headers["Location"]
    assert "doc=nfe" in resposta.headers["Location"]
    assert "amb=1" in resposta.headers["Location"]


def test_frontend_assets_servidos(client):
    assert client.get("/css/style.css").status_code == 200
    assert client.get("/js/config.js").status_code == 200
    assert client.get("/js/app.js").status_code == 200
    assert client.get("/assets/logos/simbolo.ico").status_code == 200
    assert client.get("/detalhe.html").status_code == 200
    assert client.get("/faq.html").status_code == 200
    assert client.get("/termos.html").status_code == 200
    assert client.get("/arquivo-inexistente.txt").status_code == 404


def test_api_openapi_servida(client):
    resposta = client.get("/api/openapi.yaml")
    assert resposta.status_code == 200
    corpo = resposta.get_data(as_text=True)
    assert "openapi:" in corpo
    assert "/api/status" in corpo


def test_api_openapi_download(client):
    resposta = client.get("/api/openapi.yaml?download=1")
    assert resposta.status_code == 200
    assert "attachment" in resposta.headers.get("Content-Disposition", "")
    assert "openapi.yaml" in resposta.headers.get("Content-Disposition", "")


def test_modo_embed_libera_iframe(client):
    """GET /?embed=1 troca o bloqueio de frame pela lista EMBED_ORIGENS."""
    normal = client.get("/")
    assert normal.headers.get("X-Frame-Options") == "DENY"
    assert "frame-ancestors 'none'" in normal.headers.get(
        "Content-Security-Policy", ""
    )

    embed = client.get("/?embed=1")
    assert embed.status_code == 200
    assert "X-Frame-Options" not in embed.headers
    csp_embed = embed.headers.get("Content-Security-Policy", "")
    assert "frame-ancestors 'none'" not in csp_embed
    assert "dadosjah.com.br" in csp_embed


def test_uf_invalida_404(client):
    resposta = client.get("/uf/xx")
    assert resposta.status_code == 404


def test_termos_200(client):
    assert client.get("/termos").status_code == 200


@pytest.mark.skipif(
    not (_RAIZ_PROJETO / "frontend" / "faq.html").exists(),
    reason="faq.html ainda não criado no frontend",
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


def test_cors_headers_presentes(client):
    """O after_request aplica CORS em qualquer resposta (403, 200) e no OPTIONS."""
    resposta = client.get("/api/status")
    assert resposta.headers.get("Access-Control-Allow-Origin") == "*"
    assert "CF-Turnstile-Token" in resposta.headers.get(
        "Access-Control-Allow-Headers", ""
    )

    preflight = client.open("/api/status", method="OPTIONS")
    assert preflight.status_code == 200
    assert preflight.headers.get("Access-Control-Allow-Origin") == "*"
    assert "OPTIONS" in preflight.headers.get("Access-Control-Allow-Methods", "")


def test_api_historico_geral_estrutura():
    """A função interna devolve uma série por UF monitorada, mesmo sem dados."""
    dados = _historico_geral("nfe", 1, 24)
    assert isinstance(dados, dict)
    assert "ufs" in dados and "series" in dados
    assert isinstance(dados["ufs"], list) and dados["ufs"]
    assert isinstance(dados["series"], dict)
    assert set(dados["series"].keys()) == set(dados["ufs"])
    for uf in dados["ufs"]:
        assert isinstance(dados["series"][uf], list)


def test_api_status_tem_modelos():
    """O payload de /api/status expõe os modelos ativos via função interna."""
    modelos = _modelos_ativos()
    assert isinstance(modelos, list) and modelos
    for modelo in modelos:
        assert set(modelo.keys()) == {"codigo", "nome"}
        assert modelo["codigo"]
        assert modelo["nome"]
