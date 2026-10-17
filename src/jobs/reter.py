import logging
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from apscheduler.triggers.cron import CronTrigger

# Permite executar o modulo de qualquer pasta: coloca a raiz do projeto no sys.path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.utils import config
from src.utils.db import conexao, criar_schema
from src.utils.logger import reabrir_log_do_dia
from src.utils.settings import RAIZ_PROJETO, carregar_env

logger = logging.getLogger("reter")

_JOB_ID = "reter"


def _remover_logs_antigos(dias):
    """Remove logs antigos por idade (mtime) e apaga pastas mensais vazias.

    Estrutura de logs: ``logs/AAAAMM/<modulo>_AAAAMMDD.log``. A varredura
    percorre as subpastas mensais (``logs/202610`` etc.) removendo ``*.log``
    com mtime anterior ao limite. Arquivos ``*.log`` soltos diretamente em
    ``logs/`` (legados do formato anterior) também são removidos por idade,
    mas a pasta ``logs/`` em si nunca é removida. Ao final, cada subpasta que
    ficou vazia é apagada com ``os.rmdir`` (uma pasta com arquivo recente
    permanece).

    Args:
        dias: Idade mínima, em dias, para remover o arquivo.

    Returns:
        int com a quantidade de arquivos removidos (pastas não são contadas).
    """
    pasta_logs = RAIZ_PROJETO / "logs"
    if not pasta_logs.exists():
        return 0

    limite = time.time() - dias * 86400
    removidos = 0

    subpastas = [p for p in pasta_logs.iterdir() if p.is_dir()]

    for subpasta in subpastas:
        for arquivo in subpasta.glob("*.log"):
            try:
                if arquivo.stat().st_mtime < limite:
                    arquivo.unlink()
                    removidos += 1
            except OSError as exc:
                logger.warning("Falha ao remover log %s: %s", arquivo.name, exc)

    # Legados: arquivos .log soltos na raiz de logs/ (formato anterior).
    for arquivo in pasta_logs.glob("*.log"):
        try:
            if arquivo.stat().st_mtime < limite:
                arquivo.unlink()
                removidos += 1
        except OSError as exc:
            logger.warning("Falha ao remover log %s: %s", arquivo.name, exc)

    # Remove subpastas mensais que ficaram vazias (nunca a propria pasta logs/).
    for subpasta in subpastas:
        try:
            os.rmdir(subpasta)
        except OSError as exc:
            logger.debug("Pasta de logs %s mantida: %s", subpasta.name, exc)

    return removidos


def executar_retencao():
    """Aplica a retenção de leituras e de arquivos de log.

    As retenções vêm do ``config.json`` (carregado em memória) a cada execução.
    As leituras
    mais antigas que ``retencao_dados_dias`` são apagadas e os logs com mtime
    anterior a ``retencao_logs_dias`` são removidos (incluindo pastas mensais
    vazias). Por fim, o handler de arquivo do logger é reaberto para o dia/mês
    corrente, garantindo que a virada de dia/mês não exija reiniciar o processo.

    Returns:
        dict com ``leituras_removidas`` e ``logs_removidos``.
    """
    dias_dados = config.retencao_dados_dias()
    dias_logs = config.retencao_logs_dias()

    with conexao() as conn:
        # Corte calculado em Python (ISO UTC): a string ISO é lexicograficamente
        # comparável ao formato gravado pelo coletor. Evita o bug de fronteira do
        # datetime('now') do SQLite, que deixava linhas ~1 dia além do limite.
        corte = (datetime.now(timezone.utc) - timedelta(days=dias_dados)).isoformat()
        cursor = conn.execute(
            "DELETE FROM leituras WHERE coletado_em < ?",
            (corte,),
        )
        leituras_removidas = cursor.rowcount

    logs_removidos = _remover_logs_antigos(dias_logs)

    # Reabre o handler do dia APOS a limpeza: o processo passa a escrever no
    # arquivo do novo dia (e nova pasta, na virada de mes) sem reiniciar.
    reabrir_log_do_dia()

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
    """Registra o job diário de retenção no APScheduler (03:00 Brasília).

    O scheduler roda em UTC, então o disparo ocorre às 06:00 UTC, equivalente
    a 03:00 no horário de Brasília (UTC−3, sem DST no Brasil).

    Args:
        scheduler: Instância de ``BackgroundScheduler``.

    Returns:
        str com o identificador do job.
    """
    scheduler.add_job(
        executar_retencao,
        # 03:00 no horário de Brasília (UTC−3, sem DST).
        trigger=CronTrigger(hour=6),
        id=_JOB_ID,
        replace_existing=True,
    )
    logger.info("Job de retenção agendado para diariamente às 03:00 (horário de Brasília).")
    return _JOB_ID


if __name__ == "__main__":
    from src.utils.logger import configurar_logger

    carregar_env()
    configurar_logger("reter")
    with conexao() as conn:
        criar_schema(conn)
    print(f"Resumo da retenção: {executar_retencao()}")
