import logging
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from src.utils.settings import RAIZ_PROJETO, Settings

# Estado de módulo para permitir reabrir o handler de arquivo do dia/mês corrente
# sem reiniciar o processo (ver ``reabrir_log_do_dia``).
_PASTA_MES_ATUAL = None
_NOME_MODULO = None
_CAMINHO_LOGS = None
_file_handler = None


def _fuso():
    """Retorna o fuso America/Sao_Paulo.

    Returns:
        ZoneInfo de America/Sao_Paulo; fallback UTC-3 fixo se a base IANA
        não estiver disponível (ex.: Windows sem o pacote tzdata).
    """
    try:
        return ZoneInfo("America/Sao_Paulo")
    except Exception:
        return timezone(timedelta(hours=-3))


class FusoBrasiliaFormatter(logging.Formatter):
    """Formatter que exibe data/hora no fuso America/Sao_Paulo (UTC-3)."""

    def formatTime(self, record, datefmt=None):
        dt = datetime.fromtimestamp(record.created, tz=_fuso())
        return dt.strftime("%Y-%m-%d %H:%M:%S")


def _pasta_e_arquivo(nome_modulo, caminho_logs):
    """Calcula a pasta mensal e o arquivo do dia no fuso America/Sao_Paulo.

    Args:
        nome_modulo: Nome do módulo, usado como prefixo do arquivo.
        caminho_logs: Pasta raiz de logs.

    Returns:
        Tupla ``(pasta_mes, arquivo)`` com os caminhos correspondentes (ex.:
        ``logs/202610`` e ``logs/202610/app_20261017.log``).
    """
    agora = datetime.now(_fuso())
    pasta_mes = os.path.join(caminho_logs, agora.strftime("%Y%m"))
    arquivo = os.path.join(pasta_mes, f"{nome_modulo}_{agora.strftime('%Y%m%d')}.log")
    return pasta_mes, arquivo


def _criar_file_handler(nome_modulo, caminho_logs, formatter):
    """Cria o ``FileHandler`` do dia/mês corrente dentro da pasta mensal.

    Cria a pasta ``logs/AAAAMM`` quando necessário e atualiza o estado de
    módulo ``_PASTA_MES_ATUAL``.

    Args:
        nome_modulo: Nome do módulo, usado como prefixo do arquivo.
        caminho_logs: Pasta raiz de logs.
        formatter: Instância de ``logging.Formatter`` a aplicar ao handler.

    Returns:
        ``logging.FileHandler`` aberto no arquivo do dia atual.
    """
    global _PASTA_MES_ATUAL
    pasta_mes, arquivo = _pasta_e_arquivo(nome_modulo, caminho_logs)
    os.makedirs(pasta_mes, exist_ok=True)
    handler = logging.FileHandler(arquivo, encoding="utf-8")
    handler.setFormatter(formatter)
    _PASTA_MES_ATUAL = pasta_mes
    return handler


def configurar_logger(nome_modulo, caminho_logs=None, nivel=None):
    """Configura o logger raiz uma única vez: arquivo por dia + console.

    O arquivo fica em ``logs/AAAAMM/<nome_modulo>_AAAAMMDD.log`` (pasta mensal
    no fuso America/Sao_Paulo), sem rotação automática: um arquivo novo por
    dia. Todos os módulos que usam ``logging.getLogger`` propagam para a raiz,
    caindo no mesmo arquivo. A limpeza de arquivos antigos fica a cargo do job
    de retenção, que remove por idade (mtime) e apaga as pastas mensais vazias.

    Args:
        nome_modulo: Nome do módulo, usado no nome do arquivo de log.
        caminho_logs: Pasta de logs. Padrão: logs/ na raiz do projeto.
        nivel: Nível de log (ex.: logging.INFO). Padrão: Settings.LOG_NIVEL.

    Returns:
        logging.Logger configurado para o módulo informado.
    """
    global _NOME_MODULO, _CAMINHO_LOGS, _file_handler

    if not caminho_logs:
        caminho_logs = str(RAIZ_PROJETO / "logs")
    os.makedirs(caminho_logs, exist_ok=True)

    if nivel is None:
        nivel = getattr(logging, str(Settings.LOG_NIVEL).upper(), logging.INFO)

    _NOME_MODULO = nome_modulo
    _CAMINHO_LOGS = caminho_logs

    formatter = FusoBrasiliaFormatter(
        "%(asctime)s %(levelname)s %(name)s %(message)s"
    )

    root = logging.getLogger()
    if not root.handlers:
        _file_handler = _criar_file_handler(nome_modulo, caminho_logs, formatter)
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        root.setLevel(nivel)
        root.addHandler(_file_handler)
        root.addHandler(console_handler)

    return logging.getLogger(nome_modulo)


def reabrir_log_do_dia():
    """Reabre o handler de arquivo do logger raiz para o dia/mês corrente.

    Fecha e remove o handler de arquivo atual (se houver) e recria o
    ``FileHandler`` apontando para o arquivo do dia no fuso America/Sao_Paulo.
    Como o nome do arquivo inclui o dia, o arquivo do dia é sempre recriado;
    na virada de mês, a pasta mensal também muda. Chamada diariamente pelo job
    de retenção, permite que o processo passe a escrever no novo arquivo/pasta
    sem reiniciar. O console handler NÃO é duplicado nem afetado.

    Returns:
        None.
    """
    global _file_handler

    root = logging.getLogger()
    if not root.handlers or _NOME_MODULO is None:
        # Logger ainda não configurado: nada a reabrir.
        return

    formatter = FusoBrasiliaFormatter(
        "%(asctime)s %(levelname)s %(name)s %(message)s"
    )

    if _file_handler is not None:
        root.removeHandler(_file_handler)
        _file_handler.close()

    _file_handler = _criar_file_handler(_NOME_MODULO, _CAMINHO_LOGS, formatter)
    root.addHandler(_file_handler)
