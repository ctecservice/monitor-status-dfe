import logging
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from src.utils.settings import RAIZ_PROJETO, Settings


def _fuso():
    """Retorna o fuso America/Sao_Paulo.

    Returns:
        ZoneInfo de America/Sao_Paulo; fallback UTC-3 fixo se a base IANA
        nao estiver disponivel (ex.: Windows sem o pacote tzdata).
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


def configurar_logger(nome_modulo, caminho_logs=None, nivel=None):
    """Configura o logger raiz uma unica vez: arquivo diario + console.

    O arquivo de log fica em logs/<modulo>_<AAAA-MM-DD>.log e todos os modulos
    que usam logging.getLogger propagam para a raiz, caindo no mesmo arquivo.

    Args:
        nome_modulo: Nome do modulo, usado no nome do arquivo de log.
        caminho_logs: Pasta de logs. Padrao: logs/ na raiz do projeto.
        nivel: Nivel de log (ex.: logging.INFO). Padrao: Settings.LOG_NIVEL.

    Returns:
        logging.Logger configurado para o modulo informado.
    """
    if not caminho_logs:
        caminho_logs = str(RAIZ_PROJETO / "logs")
    os.makedirs(caminho_logs, exist_ok=True)

    if nivel is None:
        nivel = getattr(logging, str(Settings.LOG_NIVEL).upper(), logging.INFO)

    data_atual = datetime.now(tz=_fuso()).strftime("%Y-%m-%d")
    arquivo_log = os.path.join(caminho_logs, f"{nome_modulo}_{data_atual}.log")

    formatter = FusoBrasiliaFormatter(
        "%(asctime)s %(levelname)s %(name)s %(message)s"
    )

    root = logging.getLogger()
    if not root.handlers:
        file_handler = logging.FileHandler(arquivo_log, encoding="utf-8")
        file_handler.setFormatter(formatter)
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        root.setLevel(nivel)
        root.addHandler(file_handler)
        root.addHandler(console_handler)

    return logging.getLogger(nome_modulo)
