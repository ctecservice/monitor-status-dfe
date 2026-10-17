import hashlib
import hmac
import logging
import re
import secrets
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from apscheduler.schedulers.background import BackgroundScheduler
from flask import (
    Flask,
    Response,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

# Permite executar o modulo de qualquer pasta: coloca a raiz do projeto no sys.path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.jobs import coletar, reter
from src.services import classificar
from src.utils import config, segredos
from src.utils.db import conexao, criar_schema
from src.utils.settings import RAIZ_PROJETO, Settings, carregar_env

logger = logging.getLogger("app")

# Ambientes exibidos no dashboard (rótulos exatos consumidos pelo template).
_AMBIENTES = [
    {"tp_amb": 1, "rotulo": "Producao"},
    {"tp_amb": 2, "rotulo": "Homologacao"},
]

# Referência ao scheduler em execução. Fica None quando a app é apenas
# importada (ex.: testes); o /health então reporta "inativo".
_scheduler = None

# Filtros editáveis na página /config (tabela configuracoes).
_CHAVES_FILTROS = (
    "ufs_monitoradas",
    "modelos_ativos",
    "intervalo_min",
    "timeout_s",
    "retencao_dados_dias",
    "retencao_logs_dias",
)

# Listas de filtros: apenas letras, vírgulas e espaços, até 200 caracteres.
_RE_LISTA = re.compile(r"^[A-Za-z,\s]{0,200}$")

# Rate limit de login em memória, por IP: no máximo _LIMITE_LOGIN tentativas em
# uma janela de _JANELA_LOGIN_S segundos. Serve para 1 worker gunicorn; o
# limit_req do nginx (M5) atua como defesa em profundidade, mas o bucket por IP
# aqui é necessário para o rate limit funcionar corretamente atrás do proxy.
_LIMITE_LOGIN = 5
_JANELA_LOGIN_S = 60
_tentativas_login = {}


def scheduler_ativo():
    """Indica se há um scheduler em execução neste processo.

    Returns:
        True se o scheduler existir e estiver rodando; False caso contrário.
    """
    return bool(_scheduler is not None and getattr(_scheduler, "running", False))


def _autenticado():
    """Informa se a sessão atual está autenticada como admin.

    Returns:
        True quando a flag de sessão estiver presente; False caso contrário.
    """
    return bool(session.get("admin_autenticado"))


def _csrf_atual():
    """Garante e devolve o token CSRF da sessão.

    O token é criado na primeira necessidade (ex.: render do formulário) e
    reutilizado nas requisições seguintes da mesma sessão.

    Returns:
        str com o token CSRF.
    """
    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_urlsafe(16)
    return session["csrf_token"]


def _csrf_valido():
    """Confere o token CSRF enviado no formulário contra o da sessão.

    Returns:
        True se ambos existirem e coincidirem; False caso contrário.
    """
    enviado = request.form.get("csrf_token", "")
    esperado = session.get("csrf_token", "")
    # compare_digest evita ataques de temporização na comparação.
    return bool(esperado) and hmac.compare_digest(enviado, esperado)


def _ip_cliente():
    """Resolve o IP do cliente, respeitando o proxy local (nginx/gunicorn).

    Atrás do nginx, o gunicorn binda em 127.0.0.1 e todas as requisições chegam
    com ``remote_addr`` local; nesse caso usamos o ``X-Real-IP`` encaminhado pelo
    proxy. Só confiamos no header quando o cliente direto é de fato o proxy local
    (127.0.0.1), evitando spoofing por clientes externos.

    Returns:
        str com o IP do cliente (ou "desconhecido" se indisponível).
    """
    remote = request.remote_addr
    if remote == "127.0.0.1":
        return request.headers.get("X-Real-IP") or remote or "desconhecido"
    return remote or "desconhecido"


def _login_permitido(ip):
    """Verifica se o IP ainda pode tentar login na janela corrente.

    Descarta as tentativas mais antigas que a janela e informa se o limite foi
    atingido.

    Args:
        ip: Endereço de origem da requisição.

    Returns:
        True se ainda houver tentativas disponíveis; False se excedeu o limite.
    """
    agora = time.monotonic()
    marcas = [
        marca
        for marca in _tentativas_login.get(ip, [])
        if agora - marca < _JANELA_LOGIN_S
    ]
    if marcas:
        _tentativas_login[ip] = marcas
    else:
        # Sem tentativas válidas na janela: remove a chave para o dicionário não
        # crescer sem limite com IPs rotativos (CWE-770).
        _tentativas_login.pop(ip, None)
    return len(marcas) < _LIMITE_LOGIN


def _registrar_tentativa(ip):
    """Registra uma tentativa de login para o IP informado.

    Args:
        ip: Endereço de origem da requisição.

    Returns:
        None.
    """
    _tentativas_login.setdefault(ip, []).append(time.monotonic())


def _validar_filtros(dados_form):
    """Valida os filtros do painel antes de gravá-los.

    Barra números fora das faixas permitidas e listas com caracteres inválidos,
    normalizando UFs para maiúsculas e modelos para minúsculas.

    Args:
        dados_form: Formulário (``request.form``) com os filtros.

    Returns:
        Tupla ``(valores, None)`` quando tudo é válido, ou ``(None, mensagem)``
        com a descrição do primeiro erro encontrado.
    """
    valores = {}
    limites = (
        ("intervalo_min", 1, 1440),
        ("timeout_s", 1, 120),
        ("retencao_dados_dias", 1, None),
        ("retencao_logs_dias", 1, None),
    )
    for chave, minimo, maximo in limites:
        bruto = (dados_form.get(chave) or "").strip()
        try:
            numero = int(bruto)
        except (TypeError, ValueError):
            return None, f"Valor inválido para {chave}: informe um número inteiro."
        if numero < minimo or (maximo is not None and numero > maximo):
            if maximo is not None:
                return None, f"{chave} deve estar entre {minimo} e {maximo}."
            return None, f"{chave} deve ser maior ou igual a {minimo}."
        valores[chave] = str(numero)

    for chave, transformar, rotulo in (
        ("ufs_monitoradas", str.upper, "UFs monitoradas"),
        ("modelos_ativos", str.lower, "Modelos ativos"),
    ):
        bruto = (dados_form.get(chave) or "").strip()
        if not _RE_LISTA.match(bruto):
            return None, (
                f"{rotulo}: use apenas letras, vírgulas e espaços "
                "(máximo de 200 caracteres)."
            )
        valores[chave] = transformar(bruto)
    return valores, None


def _filtros_atuais():
    """Lê os filtros operacionais atuais do banco.

    Returns:
        dict chave -> valor (str) para os filtros de ``_CHAVES_FILTROS``.
    """
    return {
        chave: (config.buscar_configuracao(chave) or "") for chave in _CHAVES_FILTROS
    }


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
        ``cor``, ``cstat``, ``t_med``, ``response_time``, ``coletado_em`` e
        ``erro``.
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
    """Cria a aplicação Flask com /health e a área /config protegida.

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

    # Cabeçalhos de segurança básicos em TODAS as respostas. Não adicionamos CSP
    # porque os templates injetam JSON inline (__INITIAL_DATA__ etc.); uma CSP
    # sem 'unsafe-inline' quebraria o painel — fica como pendência.
    @app.after_request
    def _security_headers(resposta):
        """Aplica cabeçalhos de segurança a toda resposta."""
        resposta.headers.setdefault("X-Content-Type-Options", "nosniff")
        resposta.headers.setdefault(
            "Referrer-Policy", "strict-origin-when-cross-origin"
        )
        resposta.headers.setdefault("X-Frame-Options", "DENY")
        return resposta

    def _render(autenticado, **extra):
        """Renderiza o template passando o token CSRF da sessão."""
        contexto = {"autenticado": autenticado, "csrf_token": _csrf_atual()}
        contexto.update(extra)
        return render_template("config.html", **contexto)

    @app.get("/health")
    def health():
        """Reporta a saúde do monitor: banco, scheduler e última coleta."""
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

        return jsonify(
            {
                "status": "ok",
                "banco": banco,
                "scheduler": "ativo" if scheduler_ativo() else "inativo",
                "ultima_coleta": ultima_coleta,
                "leituras_total": leituras_total,
            }
        )

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

    @app.get("/api/status")
    def api_status():
        """Devolve o estado atual das células para o polling do dashboard."""
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
        )

    @app.get("/api/uf/<uf>/historico")
    def api_uf_historico(uf):
        """Devolve a série histórica de uma UF (uptime e sparkline)."""
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
        documento = (
            request.args.get("documento")
            or (modelos[0]["codigo"] if modelos else "")
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

    @app.get("/config")
    def config_pagina():
        """Mostra o formulário de login ou o painel de configurações."""
        if not _autenticado():
            return _render(False)
        return _render(True, filtros=_filtros_atuais())

    @app.post("/config/login")
    def config_login():
        """Valida o CSRF, o rate limit e a senha; abre a sessão em caso de sucesso."""
        if not _csrf_valido():
            logger.warning(
                "POST /config/login sem CSRF válido (ip=%s).", request.remote_addr
            )
            return _render(False, erro="Requisição inválida."), 400

        ip = _ip_cliente()
        if not _login_permitido(ip):
            logger.warning("Rate limit de login excedido (ip=%s).", ip)
            return _render(
                False, erro="Muitas tentativas. Tente novamente em instantes."
            ), 429

        # Contabiliza ANTES de verificar a senha: assim tentativas repetidas não
        # forçam derivação PBKDF2 (custo alto) além do limite.
        _registrar_tentativa(ip)

        senha = request.form.get("senha", "")
        hash_armazenado = config.buscar_configuracao("admin_senha_hash")
        if not hash_armazenado:
            logger.warning(
                "Login sem admin_senha_hash; rode src/scripts/configurar.py."
            )
            return _render(False, erro="Acesso indisponível."), 400
        if segredos.verificar_senha(senha, hash_armazenado):
            session["admin_autenticado"] = True
            return redirect(url_for("config_pagina"))
        return _render(False, erro="Senha inválida."), 401

    @app.post("/config/logout")
    def config_logout():
        """Encerra a sessão do admin (somente POST)."""
        session.clear()
        return redirect(url_for("config_pagina"))

    @app.post("/config/salvar")
    def config_salvar():
        """Valida e grava os filtros operacionais enviados pelo painel."""
        if not _csrf_valido():
            logger.warning(
                "POST /config/salvar sem CSRF válido (ip=%s).", request.remote_addr
            )
            return _render(False, erro="Requisição inválida."), 400
        if not _autenticado():
            return redirect(url_for("config_pagina"))

        valores, erro_validacao = _validar_filtros(request.form)
        if erro_validacao:
            flash(erro_validacao, "erro")
            return redirect(url_for("config_pagina"))

        for chave, valor in (valores or {}).items():
            config.definir_configuracao(chave, valor)
        flash("Configurações salvas.", "sucesso")
        return redirect(url_for("config_pagina"))

    return app


if __name__ == "__main__":
    from src.utils.logger import configurar_logger

    carregar_env()
    configurar_logger("app")
    with conexao() as conn:
        criar_schema(conn)

    app = create_app()
    scheduler = BackgroundScheduler(timezone=timezone.utc)
    coletar.agendar(scheduler)
    reter.agendar(scheduler)
    scheduler.start()
    _scheduler = scheduler

    # use_reloader=False: o reloader do Flask sobe o processo duas vezes; com
    # ele ligado o APScheduler dispararia cada job em duplicidade.
    app.run(debug=False, use_reloader=False)
