import hashlib
import logging
import secrets
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from apscheduler.schedulers.background import BackgroundScheduler
from flask import Flask, Response, jsonify, render_template, request

# Permite executar o modulo de qualquer pasta: coloca a raiz do projeto no sys.path
# (app.py esta em src/ — um nivel abaixo da raiz — por isso parents[1])
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.jobs import backup, coletar, reter
from src.services import classificar
from src.utils import config, turnstile
from src.utils.db import conexao, criar_schema
from src.utils.rate_limit import RateLimiter
from src.utils.settings import RAIZ_PROJETO, Settings, carregar_env

logger = logging.getLogger("app")

# Ambientes exibidos no dashboard (rótulos exatos consumidos pelo template).
_AMBIENTES = [
    {"tp_amb": 1, "rotulo": "Producao"},
    {"tp_amb": 2, "rotulo": "Homologacao"},
]

# Rate limit das APIs públicas JSON: limite por IP por minuto, em memória —
# suficiente para 1 worker; o caminho avançado (gunicorn + nginx) pode somar
# limit_req no proxy. O limite vem de config.json (rate_limit).
_RL_API = RateLimiter(config.rate_limit_api_min(), 60)

# Referência ao scheduler em execução. Fica None quando a app é apenas
# importada (ex.: testes); o /health então reporta "inativo".
_scheduler = None


def scheduler_ativo():
    """Indica se há um scheduler em execução neste processo.

    Returns:
        True se o scheduler existir e estiver rodando; False caso contrário.
    """
    return bool(_scheduler is not None and getattr(_scheduler, "running", False))


def _ip_cliente():
    """Resolve o IP do cliente, respeitando o proxy local (nginx/gunicorn).

    Atrás do nginx, o gunicorn binda em 127.0.0.1 e todas as requisições chegam
    com ``remote_addr`` local; nesse caso usamos o ``X-Real-IP`` encaminhado pelo
    proxy. Só confiamos no header quando o cliente direto é de fato o proxy local
    (loopback: ``127.0.0.1`` ou ``::1``), evitando spoofing por clientes externos.

    Returns:
        str com o IP do cliente (ou "desconhecido" se indisponível).
    """
    remote = request.remote_addr
    if remote in ("127.0.0.1", "::1"):
        return request.headers.get("X-Real-IP") or remote or "desconhecido"
    return remote or "desconhecido"


def _turnstile_ok():
    """Verifica a proteção anti-bot (Turnstile) da requisição atual.

    Quando a proteção está desligada (sem chaves no .env), libera sempre. Com
    a proteção ligada, exige o header ``CF-Turnstile-Token`` e o valida no
    servidor via :func:`src.utils.turnstile.verificar_token`.

    Returns:
        Tupla ``(ok, mensagem)``: ``ok`` True quando a requisição pode seguir;
        em caso de bloqueio, ``mensagem`` descreve o motivo.
    """
    if not turnstile.turnstile_habilitado():
        return True, None
    token = request.headers.get("CF-Turnstile-Token")
    if not token:
        return False, "Verificação anti-bot ausente."
    if not turnstile.verificar_token(token, _ip_cliente()):
        return False, "Verificação anti-bot falhou."
    return True, None


def _ultimas_leituras():
    """Busca a leitura mais recente de cada combinação UF × documento × ambiente.

    Usa uma única query (evita N+1 por célula), apoiada no índice
    ``idx_leituras_lookup`` (uf, documento, tp_amb, coletado_em): o subselect
    agrupa por essas três colunas e pega o ``MAX(coletado_em)``.

    Returns:
        Lista de ``sqlite3.Row`` com a última leitura por combinação.
    """
    with conexao() as conn:
        return conn.execute(
            """
            SELECT uf, documento, tp_amb, coletado_em, cstat, msg, x_motivo,
                   t_med, response_time, versao, ver_aplic, erro
            FROM leituras
            WHERE (uf, documento, tp_amb, coletado_em) IN (
                SELECT uf, documento, tp_amb, MAX(coletado_em)
                FROM leituras
                GROUP BY uf, documento, tp_amb
            )
            ORDER BY uf, documento, tp_amb
            """
        ).fetchall()


def _celulas_atuais():
    """Monta as células atuais do dashboard (última leitura por combinação).

    Returns:
        Lista de dicts com ``uf``, ``documento``, ``tp_amb``, ``estado``,
        ``rotulo``, ``cor``, ``cstat``, ``t_med``, ``response_time``,
        ``coletado_em`` e ``erro``.
    """
    celulas = []
    for row in _ultimas_leituras():
        estado_cor = classificar.classificar(row["cstat"], erro=row["erro"])
        celulas.append(
            {
                "uf": row["uf"],
                "documento": row["documento"],
                "tp_amb": row["tp_amb"],
                "estado": estado_cor["estado"],
                "rotulo": classificar.rotulo_estado(estado_cor["estado"]),
                "cor": estado_cor["cor"],
                "cstat": row["cstat"],
                "t_med": row["t_med"],
                "response_time": row["response_time"],
                "coletado_em": row["coletado_em"],
                "erro": row["erro"],
            }
        )
    return celulas


def _ultimo_status(uf, documento, tp_amb):
    """Busca o último status registrado de uma combinação UF × documento × ambiente.

    Args:
        uf: Sigla da UF (normalizada em maiúsculas).
        documento: Código do modelo (ex.: ``nfe``).
        tp_amb: Ambiente (1 = produção, 2 = homologação).

    Returns:
        dict no formato das células, acrescido de ``msg``, ``x_motivo``,
        ``ver_aplic`` e ``dh_recebto``; ou None se não houver leitura.
    """
    with conexao() as conn:
        row = conn.execute(
            """
            SELECT uf, documento, tp_amb, coletado_em, dh_recebto, cstat, msg,
                   x_motivo, t_med, response_time, versao, ver_aplic, erro
            FROM leituras
            WHERE uf = ? AND documento = ? AND tp_amb = ?
            ORDER BY coletado_em DESC
            LIMIT 1
            """,
            (uf, documento, tp_amb),
        ).fetchone()
    if row is None:
        return None
    estado_cor = classificar.classificar(row["cstat"], erro=row["erro"])
    return {
        "uf": row["uf"],
        "documento": row["documento"],
        "tp_amb": row["tp_amb"],
        "estado": estado_cor["estado"],
        "rotulo": classificar.rotulo_estado(estado_cor["estado"]),
        "cor": estado_cor["cor"],
        "cstat": row["cstat"],
        "t_med": row["t_med"],
        "response_time": row["response_time"],
        "coletado_em": row["coletado_em"],
        "erro": row["erro"],
        "msg": row["msg"],
        "x_motivo": row["x_motivo"],
        "ver_aplic": row["ver_aplic"],
        "dh_recebto": row["dh_recebto"],
    }


def _uptime_pct(pontos):
    """Calcula o percentual de pontos operacionais na janela.

    Args:
        pontos: Lista de pontos (cada um com a chave ``estado``).

    Returns:
        float com uma casa decimal (0.0 quando não há pontos).
    """
    if not pontos:
        return 0.0
    operacionais = sum(
        1 for ponto in pontos if ponto["estado"] == classificar.ESTADO_OPERACIONAL
    )
    return round(100.0 * operacionais / len(pontos), 1)


def _historico_uf(uf, documento, tp_amb, horas):
    """Série histórica de uma combinação UF × documento × ambiente.

    O corte de data é calculado em Python (ISO UTC) e passado como parâmetro:
    comparar com ``datetime('now')`` do SQLite quebraria, pois os formatos ISO
    com offset e o formato interno do SQLite não são equivalentes
    lexicograficamente.

    Args:
        uf: Sigla da UF (normalizada em maiúsculas).
        documento: Código do modelo.
        tp_amb: Ambiente (1 = produção, 2 = homologação).
        horas: Tamanho da janela em horas.

    Returns:
        dict ``{"pontos": [...], "uptime_pct": float, "ultimo": dict}``.
        ``pontos`` traz ``coletado_em``, ``cstat``, ``estado``, ``cor``,
        ``t_med``, ``response_time`` e ``erro``. ``ultimo`` nunca é None: sem
        leitura, vem um dict neutro (estado ``sem_dados``).
    """
    corte = (datetime.now(timezone.utc) - timedelta(hours=horas)).isoformat()
    with conexao() as conn:
        rows = conn.execute(
            """
            SELECT coletado_em, cstat, t_med, response_time, erro
            FROM leituras
            WHERE uf = ? AND documento = ? AND tp_amb = ? AND coletado_em >= ?
            ORDER BY coletado_em
            """,
            (uf, documento, tp_amb, corte),
        ).fetchall()

    pontos = []
    for row in rows:
        estado_cor = classificar.classificar(row["cstat"], erro=row["erro"])
        pontos.append(
            {
                "coletado_em": row["coletado_em"],
                "cstat": row["cstat"],
                "estado": estado_cor["estado"],
                "cor": estado_cor["cor"],
                "t_med": row["t_med"],
                "response_time": row["response_time"],
                "erro": row["erro"],
            }
        )

    return {
        "pontos": pontos,
        "uptime_pct": _uptime_pct(pontos),
        "ultimo": _ultimo_status(uf, documento, tp_amb)
        or _ultimo_vazio(uf, documento, tp_amb),
    }


def _ultimo_vazio(uf, documento, tp_amb):
    """'Último status' neutro (sem_dados) quando não há leitura na combinação.

    Mantém as mesmas chaves das células para o template acessar ``ultimo.*``
    diretamente sem risco de quebra.

    Args:
        uf: Sigla da UF.
        documento: Código do modelo.
        tp_amb: Ambiente (1 = produção, 2 = homologação).

    Returns:
        dict com todas as chaves, valores None exceto ``estado`` e ``cor``.
    """
    return {
        "uf": uf,
        "documento": documento,
        "tp_amb": tp_amb,
        "estado": classificar.ESTADO_SEM_DADOS,
        "rotulo": classificar.rotulo_estado(classificar.ESTADO_SEM_DADOS),
        "cor": classificar.COR_SEM_DADOS,
        "cstat": None,
        "t_med": None,
        "response_time": None,
        "coletado_em": None,
        "erro": None,
        "msg": None,
        "x_motivo": None,
        "ver_aplic": None,
        "dh_recebto": None,
    }


def _ler_arquivo_raiz(nome):
    """Lê um arquivo de texto da raiz do projeto.

    Args:
        nome: Nome do arquivo (ex.: ``llms.txt``).

    Returns:
        Conteúdo em texto, ou None se o arquivo não existir/for ilegível.
    """
    try:
        return (Path(RAIZ_PROJETO) / nome).read_text(encoding="utf-8")
    except OSError:
        return None


def create_app():
    """Cria a aplicação Flask com o dashboard, as páginas públicas e /health.

    A ``SECRET_KEY`` das sessões é derivada da master key (domínio de chave
    distinto), nunca a própria master key; sem master key, usa uma chave
    efêmera (sessões caem no restart) até rodar ``configurar.py``.

    Returns:
        Instância de ``flask.Flask``.
    """
    app = Flask(
        __name__,
        template_folder="web/templates",
        static_folder="web/static",
    )

    if Settings.MONITOR_MASTER_KEY:
        # Separação de domínios de chave: deriva uma chave dedicada à sessão
        # Flask em vez de reutilizar a master key (que cifra segredos). Assim,
        # comprometer uma não expõe a outra.
        app.secret_key = hashlib.sha256(
            ("flask-session:" + Settings.MONITOR_MASTER_KEY).encode("utf-8")
        ).hexdigest()
    else:
        app.secret_key = secrets.token_urlsafe(32)
        logger.warning(
            "MONITOR_MASTER_KEY ausente: usando SECRET_KEY efêmera; as sessões "
            "caem no restart até rodar src/scripts/configurar.py."
        )

    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    # Cookie só trafega sob HTTPS: vazio/False no dev local; ligue
    # SESSION_COOKIE_SECURE no .env em produção.
    app.config["SESSION_COOKIE_SECURE"] = (
        Settings.SESSION_COOKIE_SECURE.strip().lower() in ("1", "true", "yes")
    )

    # Cabeçalhos de segurança básicos em TODAS as respostas. A CSP usa
    # script-src 'self' (sem 'unsafe-inline'): todo o JS é externo, os templates
    # não injetam mais <script> inline. O domínio do Cloudflare Turnstile é
    # liberado em script-src e frame-src (o widget roda em iframe da Cloudflare).
    # Mantemos 'unsafe-inline' em style-src porque os templates usam atributos
    # style dinâmicos (cores das células/badges) — style não executa código.
    @app.after_request
    def _security_headers(resposta):
        """Aplica cabeçalhos de segurança a toda resposta."""
        resposta.headers.setdefault("X-Content-Type-Options", "nosniff")
        resposta.headers.setdefault(
            "Referrer-Policy", "strict-origin-when-cross-origin"
        )
        resposta.headers.setdefault("X-Frame-Options", "DENY")
        resposta.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; script-src 'self' https://challenges.cloudflare.com; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; font-src 'self'; frame-src https://challenges.cloudflare.com; object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'",
        )
        return resposta

    @app.get("/health")
    def health():
        """Reporta a saúde do monitor e devolve 503 quando há falha crítica.

        O status é ``ok`` (HTTP 200) somente com banco acessível E scheduler
        ativo; qualquer um dos dois em falha resulta em ``erro`` (HTTP 503).

        Returns:
            Resposta JSON com ``status``, ``banco``, ``scheduler``,
            ``ultima_coleta`` e ``leituras_total``, com o código HTTP
            correspondente ao estado.
        """
        banco = "ok"
        leituras_total = 0
        ultima_coleta = None
        try:
            with conexao() as conn:
                row = conn.execute(
                    "SELECT COUNT(*) AS total, MAX(coletado_em) AS ultima FROM leituras"
                ).fetchone()
                leituras_total = row["total"] or 0
                ultima_coleta = row["ultima"]
        except Exception as exc:
            banco = "erro"
            logger.error("Falha ao consultar o banco em /health: %s", exc)

        ativo = scheduler_ativo()
        # 503 com scheduler inativo é intencional: em produção via wsgi o
        # scheduler é obrigatório; em testes/import sem bootstrap o endpoint
        # reporta erro para um monitor de disponibilidade detectar.
        saudavel = banco == "ok" and ativo
        return jsonify(
            {
                "status": "ok" if saudavel else "erro",
                "banco": banco,
                "scheduler": "ativo" if ativo else "inativo",
                "ultima_coleta": ultima_coleta,
                "leituras_total": leituras_total,
            }
        ), (200 if saudavel else 503)

    @app.get("/")
    def index():
        """Renderiza o dashboard (grade UF × modelo × ambiente)."""
        modelos = config.modelos_ativos_dfe()
        return render_template(
            "index.html",
            celulas=_celulas_atuais(),
            ufs=config.ufs_monitoradas(),
            modelos=[{"codigo": m["codigo"], "nome": m["nome"]} for m in modelos],
            ambientes=_AMBIENTES,
            gerado_em=datetime.now(timezone.utc).isoformat(),
            turnstile_site_key=Settings.TURNSTILE_SITE_KEY,
        )

    @app.get("/llms.txt")
    def llms_txt():
        """Serve o guia llms.txt (arquivo da raiz) para agentes de IA."""
        conteudo = _ler_arquivo_raiz("llms.txt")
        if conteudo is None:
            return "Arquivo não encontrado.", 404
        return Response(conteudo, content_type="text/plain; charset=utf-8")

    @app.get("/robots.txt")
    def robots_txt():
        """Serve a política de crawlers (arquivo da raiz)."""
        conteudo = _ler_arquivo_raiz("robots.txt")
        if conteudo is None:
            return "Arquivo não encontrado.", 404
        return Response(conteudo, content_type="text/plain; charset=utf-8")

    @app.get("/sitemap.xml")
    def sitemap_xml():
        """Serve o sitemap XML (arquivo da raiz)."""
        conteudo = _ler_arquivo_raiz("sitemap.xml")
        if conteudo is None:
            return "Arquivo não encontrado.", 404
        return Response(conteudo, content_type="application/xml; charset=utf-8")

    @app.get("/termos")
    def termos():
        """Renderiza a página de termos de uso."""
        return render_template("termos.html")

    @app.get("/faq")
    def faq():
        """Renderiza a página de perguntas frequentes (FAQ)."""
        return render_template("faq.html")

    @app.get("/api/status")
    def api_status():
        """Devolve o estado atual das células para o polling do dashboard."""
        ip = _ip_cliente()
        if not _RL_API.consome(ip):
            resposta = jsonify(
                {"erro": "Limite de requisições excedido. Tente novamente em instantes."}
            )
            resposta.headers["Retry-After"] = "60"
            return resposta, 429
        ok, msg = _turnstile_ok()
        if not ok:
            return jsonify({"erro": msg}), 403
        return jsonify(
            {
                "gerado_em": datetime.now(timezone.utc).isoformat(),
                "ambientes": _AMBIENTES,
                "celulas": _celulas_atuais(),
            }
        )

    @app.get("/uf/<uf>")
    def uf_detalhe(uf):
        """Renderiza a página de detalhe de uma UF.

        Lê ``documento`` e ``tp_amb`` da query string com validação defensiva:
        documento inexistente cai no primeiro modelo ativo; tp_amb fora de 1/2
        cai em 1.
        """
        uf_norm = (uf or "").strip().upper()
        if uf_norm not in Settings.lista_ufs():
            return "UF inválida.", 404

        modelos = config.modelos_ativos_dfe()
        codigos = [m["codigo"] for m in modelos]

        # Mesma validação defensiva da rota /api/uf/<uf>/historico: usa o
        # documento informado (minúsculo) e só cai no primeiro ativo quando
        # ausente. Assim, um modelo sem dados ainda exibe "sem dados" em vez de
        # trocar de modelo silenciosamente.
        documento = (
            request.args.get("documento") or (codigos[0] if codigos else "")
        ).strip().lower()
        modelo_nome = next(
            (m["nome"] for m in modelos if m["codigo"] == documento),
            documento.upper() if documento else "",
        )

        try:
            tp_amb = int(request.args.get("tp_amb", "1"))
        except (TypeError, ValueError):
            tp_amb = 1
        if tp_amb not in (1, 2):
            tp_amb = 1

        historico = _historico_uf(uf_norm, documento, tp_amb, 24)
        return render_template(
            "detalhe.html",
            uf=uf_norm,
            documento=documento,
            tp_amb=tp_amb,
            modelo_nome=modelo_nome,
            ultimo=historico["ultimo"],
            pontos=historico["pontos"],
            uptime_pct=historico["uptime_pct"],
            documentos=[{"codigo": m["codigo"], "nome": m["nome"]} for m in modelos],
            ambientes=_AMBIENTES,
            turnstile_site_key=Settings.TURNSTILE_SITE_KEY,
        )

    @app.get("/api/uf/<uf>/historico")
    def api_uf_historico(uf):
        """Devolve a série histórica de uma UF (uptime e sparkline)."""
        ip = _ip_cliente()
        if not _RL_API.consome(ip):
            resposta = jsonify(
                {"erro": "Limite de requisições excedido. Tente novamente em instantes."}
            )
            resposta.headers["Retry-After"] = "60"
            return resposta, 429
        ok, msg = _turnstile_ok()
        if not ok:
            return jsonify({"erro": msg}), 403

        uf_norm = (uf or "").strip().upper()
        if uf_norm not in Settings.lista_ufs():
            return jsonify({"erro": "UF inválida."}), 404

        bruto_horas = request.args.get("horas", "24")
        try:
            horas = int(bruto_horas)
        except (TypeError, ValueError):
            return jsonify({"erro": "Parâmetro 'horas' inválido."}), 400
        if horas < 1 or horas > 720:
            return jsonify({"erro": "Parâmetro 'horas' deve estar entre 1 e 720."}), 400

        modelos = config.modelos_ativos_dfe()
        codigos = [m["codigo"] for m in modelos]
        informado = request.args.get("documento")
        # Quando o documento é INFORMADO na query, exige que seja um modelo
        # ativo conhecido (400 se não for); ausente continua caindo no
        # primeiro modelo ativo.
        if informado and informado.strip().lower() not in codigos:
            return jsonify({"erro": "Documento inválido."}), 400
        documento = (
            informado or (modelos[0]["codigo"] if modelos else "")
        ).strip().lower()

        bruto_amb = request.args.get("tp_amb", "1")
        try:
            tp_amb = int(bruto_amb)
        except (TypeError, ValueError):
            return jsonify({"erro": "Parâmetro 'tp_amb' inválido."}), 400
        if tp_amb not in (1, 2):
            return jsonify({"erro": "Parâmetro 'tp_amb' deve ser 1 ou 2."}), 400

        historico = _historico_uf(uf_norm, documento, tp_amb, horas)
        return jsonify(
            {
                "uf": uf_norm,
                "horas": horas,
                "documento": documento,
                "tp_amb": tp_amb,
                "pontos": historico["pontos"],
                "uptime_pct": historico["uptime_pct"],
                "ultimo": historico["ultimo"],
            }
        )

    return app


def iniciar_scheduler():
    """Cria, agenda e inicia o scheduler de coleta/retensão (idempotente).

    O scheduler roda **dentro do processo** da aplicação — por isso o gunicorn
    deve subir com exatamente 1 worker (múltiplos workers disparariam coletas
    duplicadas). O endpoint ``/health`` depende dele estar ativo para reportar
    ``status: ok``.

    Returns:
        Instância de ``BackgroundScheduler`` em execução; se já houver uma ativa
        neste processo, devolve a existente sem criar outra.
    """
    global _scheduler
    if _scheduler is not None and getattr(_scheduler, "running", False):
        return _scheduler
    scheduler = BackgroundScheduler(timezone=timezone.utc)
    coletar.agendar(scheduler)
    reter.agendar(scheduler)
    backup.agendar(scheduler)
    scheduler.start()
    _scheduler = scheduler
    return scheduler


if __name__ == "__main__":
    from src.utils.logger import configurar_logger

    carregar_env()
    configurar_logger("app")
    with conexao() as conn:
        criar_schema(conn)

    app = create_app()
    iniciar_scheduler()

    # host 0.0.0.0 permite servir direto numa VPS/container, sem proxy reverso;
    # a porta vem de config.json (default 5628). O aviso do werkzeug (dev server)
    # é aceitável para uso leve; produção maior deve usar o caminho avançado
    # (gunicorn + nginx, em public/docs/deploy.md).
    # use_reloader=False: o reloader do Flask sobe o processo duas vezes; com
    # ele ligado o APScheduler dispararia cada job em duplicidade.
    app.run(
        host="0.0.0.0",
        port=config.porta_web(),
        debug=False,
        use_reloader=False,
    )
