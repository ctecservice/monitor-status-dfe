"""Verificação rápida do Monitor Status DFe num servidor HTTP real.

Sobe a aplicação em uma porta efêmera local (127.0.0.1), dispara as checagens
HTTP — rotas, cabeçalhos de segurança, /health, FAQ, rótulos — e encerra
sozinho, sem deixar processos rodando. Complementa a suíte pytest (tests/),
que cobre as mesmas rotas via test_client.

Uso:
    python src/scripts/verificar.py

Retorna exit 0 quando todas as checagens passam e 1 em falha.
"""

import json
import sys
import threading
import urllib.error
import urllib.request
from pathlib import Path

# Permite executar o modulo de qualquer pasta: coloca a raiz do projeto no sys.path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from werkzeug.serving import make_server

from src.app import create_app, iniciar_scheduler
from src.utils import turnstile
from src.utils.db import conexao, criar_schema
from src.utils.logger import configurar_logger
from src.utils.settings import carregar_env

# Rotas com o status HTTP esperado (inclui erros propositais de validação).
_ROTAS = [
    ("/", 200),
    ("/uf/MG?documento=nfe&tp_amb=1", 200),
    ("/api/status", 200),
    ("/api/uf/MG/historico?horas=24&documento=nfe&tp_amb=1", 200),
    ("/health", 200),
    ("/termos", 200),
    ("/faq", 200),
    ("/api/openapi.yaml", 200),
    ("/llms.txt", 200),
    ("/robots.txt", 200),
    ("/sitemap.xml", 200),
    ("/uf/xx", 404),
    ("/config", 404),
    ("/api/uf/MG/historico?horas=24&documento=nfe&tp_amb=99", 400),
    ("/api/uf/MG/historico?horas=24&documento=inexistente&tp_amb=1", 400),
]


def _requisitar(base, caminho):
    """Executa um GET e devolve (status, headers, corpo em texto).

    Args:
        base: URL base do servidor (ex.: ``http://127.0.0.1:5628``).
        caminho: Caminho da rota (ex.: ``/health``).

    Returns:
        Tupla ``(status, headers, corpo)``.
    """
    with urllib.request.urlopen(base + caminho, timeout=10) as resposta:
        return resposta.status, dict(resposta.headers), resposta.read().decode("utf-8")


def _checagem(nome, condicao, detalhe=""):
    """Registra o resultado de uma checagem e devolve True quando passou.

    Args:
        nome: Descrição curta da checagem.
        condicao: Resultado booleano da verificação.
        detalhe: Informação extra impressa em caso de falha.

    Returns:
        True quando a checagem passou; False caso contrário.
    """
    if condicao:
        print(f"  [ok] {nome}")
    else:
        print(f"  [FALHOU] {nome} {detalhe}")
    return bool(condicao)


def main():
    """Sobe o servidor, executa as checagens HTTP e encerra tudo.

    Returns:
        None (usa ``sys.exit`` com 0 em sucesso e 1 em falha).
    """
    carregar_env()
    configurar_logger("verificar")
    with conexao() as conn:
        criar_schema(conn)

    scheduler = iniciar_scheduler()
    app = create_app()
    servidor = make_server("127.0.0.1", 0, app)
    porta = servidor.server_port
    base = f"http://127.0.0.1:{porta}"

    # serve_forever bloqueia: roda o servidor numa thread e encerra ao final.
    thread = threading.Thread(target=servidor.serve_forever, daemon=True)
    thread.start()

    anti_bot = turnstile.turnstile_habilitado()

    falhas = 0
    try:
        print(
            f"Verificação HTTP em {base} "
            f"(Turnstile {'habilitado' if anti_bot else 'desligado'}) ..."
        )

        # Com o Turnstile habilitado, as rotas protegidas DEVEM recusar
        # requisições sem o header CF-Turnstile-Token (403). Sem chaves
        # configuradas, elas respondem normalmente (200/400/404).
        rotas = [
            (caminho, 403 if anti_bot and caminho.startswith("/api/") else esperado)
            for caminho, esperado in _ROTAS
        ]

        for caminho, esperado in rotas:
            try:
                status, _, _ = _requisitar(base, caminho)
            except urllib.error.HTTPError as erro:
                status = erro.code
            if not _checagem(f"GET {caminho} -> {status}", status == esperado, f"(esperado {esperado})"):
                falhas += 1

        status, headers, corpo = _requisitar(base, "/")
        csp = headers.get("Content-Security-Policy", "")
        if not _checagem("CSP presente em /", csp.startswith("default-src 'self'")):
            falhas += 1
        if not _checagem("CSP libera Turnstile", "challenges.cloudflare.com" in csp):
            falhas += 1
        if not _checagem("Sem JSON inline em /", "__INITIAL_DATA__" not in corpo):
            falhas += 1
        # Créditos e links públicos vivem nas páginas estáticas.
        if not _checagem("Página com crédito CTEC", "ctec.com.br" in corpo):
            falhas += 1
        if not _checagem(
            "Página com link do GitHub",
            "github.com/ctecservice/monitor-status-dfe" in corpo,
        ):
            falhas += 1

        _, _, corpo = _requisitar(base, "/health")
        saude = json.loads(corpo)
        if not _checagem(
            "/health saudável com scheduler",
            saude.get("status") == "ok" and saude.get("scheduler") == "ativo",
        ):
            falhas += 1

        if not anti_bot:
            # Com o Turnstile ativo não há token para enviar (sem browser);
            # a presença dos rótulos é coberta pela suíte pytest via test_client.
            _, _, corpo = _requisitar(base, "/api/status")
            celulas = json.loads(corpo).get("celulas", [])
            if not _checagem(
                "Células com rótulos exibíveis",
                all(celula.get("rotulo") for celula in celulas),
            ):
                falhas += 1
        else:
            _checagem("APIs protegidas exigem token Turnstile", True)

        _, _, corpo = _requisitar(base, "/faq")
        if not _checagem("FAQ com acordeões", corpo.count("<details") >= 10):
            falhas += 1

        # A rota antiga /uf/<uf> redireciona (302) para a página estática
        # detalhe.html?uf=...&doc=...&amb=...; o urllib segue o redirect.
        _, _, corpo = _requisitar(base, "/uf/MG?documento=nfe&tp_amb=1")
        if not _checagem("Detalhe redireciona para a página estática", 'id="campo-cstat"' in corpo):
            falhas += 1

        # Verificação explícita do redirect (sem seguir): 302 + Location.
        import http.client as _http
        _conn = _http.HTTPConnection("127.0.0.1", porta, timeout=10)
        _conn.request("GET", "/uf/MG?documento=nfe&tp_amb=1")
        _resp = _conn.getresponse()
        _status_redir = _resp.status
        _location = _resp.getheader("Location", "")
        _conn.close()
        if not _checagem(
            "Redirect /uf/<uf> retorna 302 com Location",
            _status_redir == 302 and "/detalhe.html?uf=MG" in _location,
            f"(status={_status_redir}, Location={_location})",
        ):
            falhas += 1
    finally:
        servidor.shutdown()
        scheduler.shutdown(wait=False)

    if falhas:
        print(f"Verificação concluída com {falhas} falha(s).")
        sys.exit(1)
    print("Verificação concluída: todas as checagens passaram.")
    sys.exit(0)


if __name__ == "__main__":
    main()
