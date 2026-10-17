import logging
import sys
import time
from pathlib import Path

from apscheduler.triggers.cron import CronTrigger

# Permite executar o modulo de qualquer pasta: coloca a raiz do projeto no sys.path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.utils import config
from src.utils.db import conexao, criar_schema
from src.utils.settings import RAIZ_PROJETO, carregar_env

logger = logging.getLogger("reter")

_JOB_ID = "reter"


def _remover_logs_antigos(dias):
    """Remove arquivos ``logs/*.log`` mais antigos que ``dias``.

    Usa o mtime (data de modificação) do arquivo como referência.

    Args:
        dias: Idade mínima, em dias, para remover o arquivo.

    Returns:
        int com a quantidade de arquivos removidos.
    """
    pasta_logs = RAIZ_PROJETO / "logs"
    if not pasta_logs.exists():
        return 0

    limite = time.time() - dias * 86400
    removidos = 0
    for arquivo in pasta_logs.glob("*.log"):
        try:
            if arquivo.stat().st_mtime < limite:
                arquivo.unlink()
                removidos += 1
        except OSError as exc:
            logger.warning("Falha ao remover log %s: %s", arquivo.name, exc)
    return removidos


def executar_retencao():
    """Aplica a retenção de leituras e de arquivos de log.

    As retenções vêm da tabela ``configuracoes`` a cada execução. As leituras
    mais antigas que ``retencao_dados_dias`` são apagadas e os logs com mtime
    anterior a ``retencao_logs_dias`` são removidos.

    Returns:
        dict com ``leituras_removidas`` e ``logs_removidos``.
    """
    dias_dados = config.retencao_dados_dias()
    dias_logs = config.retencao_logs_dias()

    with conexao() as conn:
        cursor = conn.execute(
            "DELETE FROM leituras WHERE coletado_em < datetime('now', ?)",
            (f"-{dias_dados} days",),
        )
        leituras_removidas = cursor.rowcount

    logs_removidos = _remover_logs_antigos(dias_logs)

    logger.info(
        "Retenção aplicada: %s leitura(s) removida(s) (> %s dias) e "
        "%s log(s) removido(s) (> %s dias).",
        leituras_removidas,
        dias_dados,
        logs_removidos,
        dias_logs,
    )
    return {
        "leituras_removidas": leituras_removidas,
        "logs_removidos": logs_removidos,
    }


def agendar(scheduler):
    """Registra o job diário de retenção no APScheduler (03:00).

    Args:
        scheduler: Instância de ``BackgroundScheduler``.

    Returns:
        str com o identificador do job.
    """
    scheduler.add_job(
        executar_retencao,
        trigger=CronTrigger(hour=3),
        id=_JOB_ID,
        replace_existing=True,
    )
    logger.info("Job de retenção agendado para diariamente às 03:00.")
    return _JOB_ID


if __name__ == "__main__":
    from src.utils.logger import configurar_logger

    carregar_env()
    configurar_logger("reter")
    with conexao() as conn:
        criar_schema(conn)
    print(f"Resumo da retenção: {executar_retencao()}")
