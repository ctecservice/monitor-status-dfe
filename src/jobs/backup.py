import logging
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from apscheduler.triggers.cron import CronTrigger

# Permite executar o modulo de qualquer pasta: coloca a raiz do projeto no sys.path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.utils.db import conexao
from src.utils.settings import RAIZ_PROJETO, carregar_env

logger = logging.getLogger("backup")

_JOB_ID = "backup"

# Quantidade de backups diários mantidos em data/backups/.
_MANTER = 7


def _fuso():
    """Retorna o fuso America/Sao_Paulo.

    Returns:
        ZoneInfo de America/Sao_Paulo; fallback UTC-3 fixo se a base IANA não
        estiver disponível (ex.: Windows sem o pacote tzdata).
    """
    try:
        return ZoneInfo("America/Sao_Paulo")
    except Exception:
        return timezone(timedelta(hours=-3))


def _pasta_backups():
    """Caminho da pasta de backups (``data/backups`` na raiz do projeto).

    Returns:
        pathlib.Path apontando para a pasta de backups.
    """
    return RAIZ_PROJETO / "data" / "backups"


def _manter_mais_recentes(pasta, maximo):
    """Remove backups antigos, mantendo apenas os ``maximo`` mais recentes.

    A ordenação usa o ``mtime`` (data de modificação) de cada ``*.db``.

    Args:
        pasta: Pasta onde os backups são armazenados.
        maximo: Quantidade de arquivos a manter.

    Returns:
        int com a quantidade de arquivos removidos.
    """
    arquivos = sorted(
        pasta.glob("*.db"),
        key=lambda caminho: caminho.stat().st_mtime,
        reverse=True,
    )
    removidos = 0
    for arquivo in arquivos[maximo:]:
        try:
            arquivo.unlink()
            removidos += 1
        except OSError as exc:
            logger.warning("Falha ao remover backup %s: %s", arquivo.name, exc)
    return removidos


def executar_backup():
    """Gera um backup diário do banco com ``VACUUM INTO`` e poda os antigos.

    O destino é ``data/backups/statusdfe-<AAAAMMDD>.db`` (data no fuso de
    Brasília). ``VACUUM INTO`` produz uma cópia compacta e consistente do
    banco sem bloquear leituras. Ao final, apenas os 7 backups mais recentes
    são mantidos (os demais são removidos por mtime). Falhas são registradas e
    não propagam.

    Returns:
        dict com ``caminho`` (destino do backup) e ``removidos`` (quantidade de
        arquivos antigos excluídos).
    """
    pasta = _pasta_backups()
    os.makedirs(pasta, exist_ok=True)

    data = datetime.now(_fuso()).strftime("%Y%m%d")
    destino = pasta / f"statusdfe-{data}.db"

    try:
        with conexao() as conn:
            # VACUUM INTO aceita a expressão parametrizada e gera uma cópia
            # consistente do banco (não pode rodar dentro de uma transação).
            conn.execute("VACUUM INTO ?", (str(destino),))
        logger.info("Backup do banco gerado em %s.", destino)
    except Exception as exc:
        logger.error("Falha ao gerar backup do banco (%s): %s", destino, exc)

    removidos = _manter_mais_recentes(pasta, _MANTER)
    if removidos:
        logger.info(
            "Backup: %s arquivo(s) antigo(s) removido(s) (mantidos os %s mais "
            "recentes).",
            removidos,
            _MANTER,
        )
    return {"caminho": str(destino), "removidos": removidos}


def agendar(scheduler):
    """Registra o job diário de backup no APScheduler (02:00 Brasília).

    O scheduler roda em UTC, então o disparo ocorre às 05:00 UTC, equivalente
    a 02:00 no horário de Brasília (UTC−3, sem DST no Brasil). Roda **antes**
    da retenção (03:00 BSB, 06:00 UTC) para o backup diário conter o dia
    anterior íntegro, antes de qualquer exclusão por retenção.

    Args:
        scheduler: Instância de ``BackgroundScheduler``.

    Returns:
        str com o identificador do job.
    """
    scheduler.add_job(
        executar_backup,
        # 02:00 no horário de Brasília (UTC−3, sem DST) = 05:00 UTC. Antes da
        # retenção (03:00 BSB) para o backup preservar o dia anterior inteiro.
        trigger=CronTrigger(hour=5),
        id=_JOB_ID,
        replace_existing=True,
    )
    logger.info(
        "Job de backup agendado para diariamente às 02:00 (horário de Brasília)."
    )
    return _JOB_ID


if __name__ == "__main__":
    from src.utils.db import criar_schema
    from src.utils.logger import configurar_logger

    carregar_env()
    configurar_logger("backup")
    with conexao() as conn:
        criar_schema(conn)
    print(f"Resumo do backup: {executar_backup()}")
