import json
import logging
import os
import sys
from pathlib import Path

# Permite executar o modulo de qualquer pasta: coloca a raiz do projeto no sys.path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.utils.db import conexao
from src.utils.settings import RAIZ_PROJETO, Settings

logger = logging.getLogger("config")

# Fonte única das configurações operacionais: config.json na raiz do projeto.
# O arquivo é lido uma vez no import e mantido em memória; alterações exigem
# restart do processo (não há painel web nem recarga automática).
CAMINHO_CONFIG = RAIZ_PROJETO / "config.json"

# Defaults embutidos: valem quando o arquivo não existe ou traz valor inválido.
_PADROES = {
    "coleta": {
        "ufs_monitoradas": (
            "AC,AL,AP,AM,BA,CE,DF,ES,GO,MA,MT,MS,MG,PA,PB,PR,PE,PI,RJ,RN,RS,RO,"
            "RR,SC,SP,SE,TO"
        ),
        "modelos_ativos": "nfe",
        "intervalo_min": 5,
        "timeout_s": 20,
        "motor": "dadosjah",
    },
    "retencao": {
        "dados_dias": 30,
        "logs_dias": 7,
    },
    "web": {
        "porta": 5628,
    },
    "rate_limit": {
        "api_requisicoes_por_minuto": 30,
    },
    "links": {
        "github": "https://github.com/ctecservice/monitor-status-dfe",
        "ctec": "https://ctec.com.br/",
    },
}

_config = {}


def recarregar():
    """Carrega ``config.json`` para a memória do processo.

    É chamada automaticamente no import do módulo e pode ser reutilizada por
    scripts/testes. Alterações no arquivo **não** são aplicadas em execução:
    a configuração é lida uma vez e exige restart do processo para valer.
    Quando o arquivo não existe ou é inválido, os defaults internos assumem e
    um warning é registrado.

    Returns:
        None.
    """
    global _config
    try:
        conteudo = json.loads(CAMINHO_CONFIG.read_text(encoding="utf-8"))
    except FileNotFoundError:
        logger.warning(
            "%s não encontrado; usando os padrões internos.", CAMINHO_CONFIG.name
        )
        _config = {}
        return
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning(
            "Falha ao ler %s (%s); usando os padrões internos.",
            CAMINHO_CONFIG.name,
            exc,
        )
        _config = {}
        return
    if not isinstance(conteudo, dict):
        logger.warning(
            "%s inválido (raiz não é um objeto); usando os padrões internos.",
            CAMINHO_CONFIG.name,
        )
        _config = {}
        return
    _config = conteudo


def _secao(nome):
    """Devolve uma seção do config.json como dict, ou vazio se ausente/inválida.

    Args:
        nome: Nome da seção (ex.: ``coleta``).

    Returns:
        dict com a seção (vazio quando não existe ou não é um objeto).
    """
    secao = _config.get(nome)
    return secao if isinstance(secao, dict) else {}


def _texto(secao, chave):
    """Lê um valor textual de uma seção, com fallback ao padrão.

    Args:
        secao: Nome da seção do config.json.
        chave: Nome da chave dentro da seção.

    Returns:
        str validada (sem espaços nas pontas) ou o padrão interno.
    """
    valor = _secao(secao).get(chave)
    padrao = _PADROES[secao][chave]
    if valor is None:
        return padrao
    if not isinstance(valor, str):
        logger.warning(
            "Configuração '%s.%s' inválida (%r); usando padrão %r.",
            secao,
            chave,
            valor,
            padrao,
        )
        return padrao
    return valor.strip()


def _lista(secao, chave):
    """Lê uma lista separada por vírgula, descartando itens vazios.

    Args:
        secao: Nome da seção do config.json.
        chave: Nome da chave cujo valor é uma lista separada por vírgula.

    Returns:
        Lista de strings (vazia quando o valor é nulo ou vazio).
    """
    valor = _texto(secao, chave)
    return [item.strip() for item in valor.split(",") if item.strip()]


def _inteiro(secao, chave):
    """Lê um valor inteiro positivo de uma seção, com fallback ao padrão.

    Args:
        secao: Nome da seção do config.json.
        chave: Nome da chave numérica.

    Returns:
        int validado ou o padrão interno em caso de valor ausente/inválido.
    """
    valor = _secao(secao).get(chave)
    padrao = _PADROES[secao][chave]
    if valor is None:
        return padrao
    if isinstance(valor, bool):
        logger.warning(
            "Configuração '%s.%s' inválida (%r); usando padrão %s.",
            secao,
            chave,
            valor,
            padrao,
        )
        return padrao
    try:
        numero = int(valor)
    except (TypeError, ValueError):
        logger.warning(
            "Configuração '%s.%s' inválida (%r); usando padrão %s.",
            secao,
            chave,
            valor,
            padrao,
        )
        return padrao
    if numero <= 0:
        logger.warning(
            "Configuração '%s.%s' deve ser positiva (%r); usando padrão %s.",
            secao,
            chave,
            valor,
            padrao,
        )
        return padrao
    return numero


def ufs_monitoradas():
    """Lista as UFs a consultar, conforme ``coleta.ufs_monitoradas``.

    Quando a lista está vazia no config.json, cai no padrão do ``.env``.

    Returns:
        Lista de siglas de UF em maiúsculas.
    """
    ufs = [uf.upper() for uf in _lista("coleta", "ufs_monitoradas")]
    return ufs if ufs else Settings.lista_ufs()


def modelos_ativos():
    """Lista os códigos de modelos de DFe a consultar.

    Considera apenas modelos com ``ativo=1`` em ``modelos_dfe``. Quando
    ``coleta.modelos_ativos`` está vazio, retorna todos os ativos.

    Returns:
        Lista de códigos de modelo (ex.: ``["nfe"]``).
    """
    with conexao() as conn:
        rows = conn.execute(
            "SELECT codigo FROM modelos_dfe WHERE ativo = 1 ORDER BY codigo"
        ).fetchall()
    ativos = [row["codigo"] for row in rows]

    selecionados = [codigo.lower() for codigo in _lista("coleta", "modelos_ativos")]
    if not selecionados:
        return ativos
    # Interseção: só devolve o que foi configurado E existe como ativo.
    return [codigo for codigo in ativos if codigo in selecionados]


def modelos_ativos_dfe():
    """Lista os modelos ativos com seus metadados de endpoint.

    Returns:
        Lista de dicionários ``{"codigo", "nome", "endpoint"}`` na ordem dos
        códigos retornados por :func:`modelos_ativos`.
    """
    codigos = modelos_ativos()
    if not codigos:
        return []
    marcadores = ",".join("?" for _ in codigos)
    with conexao() as conn:
        rows = conn.execute(
            f"SELECT codigo, nome, endpoint FROM modelos_dfe "
            f"WHERE ativo = 1 AND codigo IN ({marcadores})",
            codigos,
        ).fetchall()
    por_codigo = {row["codigo"]: dict(row) for row in rows}
    return [por_codigo[codigo] for codigo in codigos if codigo in por_codigo]


def intervalo_min():
    """Intervalo entre ciclos de coleta, em minutos.

    Returns:
        int (padrão 5).
    """
    return _inteiro("coleta", "intervalo_min")


def timeout_s():
    """Timeout das requisições à API, em segundos.

    Returns:
        int (padrão 20).
    """
    return _inteiro("coleta", "timeout_s")


def retencao_dados_dias():
    """Dias de retenção do histórico de leituras.

    Returns:
        int (padrão 30).
    """
    return _inteiro("retencao", "dados_dias")


def retencao_logs_dias():
    """Dias de retenção dos arquivos de log.

    Returns:
        int (padrão 7).
    """
    return _inteiro("retencao", "logs_dias")


def motor_ativo():
    """Motor de coleta configurado em ``coleta.motor``.

    Returns:
        str com o identificador do motor (padrão ``dadosjah``).
    """
    return _texto("coleta", "motor")


def porta_web():
    """Porta HTTP do servidor web.

    A variável de ambiente ``PORT`` tem prioridade sobre ``web.porta`` do
    ``config.json``: plataformas PaaS (ex.: botkeep.cloud) alocam a porta via
    ambiente e ignorariam um valor fixo em arquivo.

    Returns:
        int com a porta (padrão 5628).
    """
    porta_env = os.environ.get("PORT")
    if porta_env:
        try:
            return int(porta_env)
        except ValueError:
            logger.warning("PORT do ambiente é inválido (%r); usando config.json", porta_env)
    return _inteiro("web", "porta")


def rate_limit_api_min():
    """Limite de requisições por minuto da API pública.

    Returns:
        int (padrão 30).
    """
    return _inteiro("rate_limit", "api_requisicoes_por_minuto")


def link_github():
    """URL do repositório do projeto exibida nas páginas.

    Returns:
        str (padrão: repositório oficial no GitHub).
    """
    return _texto("links", "github")


def link_ctec():
    """URL do site da CTEC exibida nas páginas.

    Returns:
        str (padrão: ``https://ctec.com.br/``).
    """
    return _texto("links", "ctec")


recarregar()


if __name__ == "__main__":
    from src.utils.settings import carregar_env
    from src.utils.db import criar_schema

    carregar_env()
    with conexao() as conn:
        criar_schema(conn)
    print("ufs_monitoradas:", ufs_monitoradas()[:5], "...")
    print("modelos_ativos:", modelos_ativos())
    print("modelos_ativos_dfe:", modelos_ativos_dfe())
    print("intervalo_min:", intervalo_min())
    print("timeout_s:", timeout_s())
    print("retencao_dados_dias:", retencao_dados_dias())
    print("retencao_logs_dias:", retencao_logs_dias())
    print("motor_ativo:", motor_ativo())
    print("porta_web:", porta_web())
    print("rate_limit_api_min:", rate_limit_api_min())
    print("link_github:", link_github())
    print("link_ctec:", link_ctec())
