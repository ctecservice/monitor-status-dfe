import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# Permite executar o modulo de qualquer pasta: coloca a raiz do projeto no sys.path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.services import api_dadosjah, classificar
from src.utils import config
from src.utils.db import conexao, criar_schema
from src.utils.settings import Settings, carregar_env

logger = logging.getLogger("coletar")

# Identificador do job no APScheduler (usado para reschedule_job).
_JOB_ID = "coletar"


def _int_ou_none(valor):
    """Converte um valor da API para int, devolvendo None quando não aplicável.

    Args:
        valor: Valor bruto (str, int, float ou None).

    Returns:
        int ou None.
    """
    if valor is None or valor == "":
        return None
    try:
        return int(valor)
    except (TypeError, ValueError):
        return None


def _coletar_uma(conn, modelo, uf, tp_amb, timeout_s):
    """Executa uma consulta e grava a leitura correspondente.

    A falha da API não levanta exceção: a leitura é gravada com o campo
    ``erro`` preenchido e o ciclo continua.

    Args:
        conn: Conexão SQLite reutilizada pelo ciclo.
        modelo: Dicionário do modelo (``codigo``, ``nome``, ``endpoint``).
        uf: Sigla da UF.
        tp_amb: Ambiente (1 = produção, 2 = homologação).
        timeout_s: Timeout da requisição, em segundos.

    Returns:
        True se a consulta teve sucesso, False caso contrário.
    """
    resultado = api_dadosjah.consultar_status(
        uf, modelo["endpoint"], tp_amb, timeout_s
    )
    dados = resultado["dados"] or {}
    erro = resultado["erro"]

    # A classificação alimenta o resumo/log do ciclo (a tabela leituras guarda
    # o cStat bruto + erro; o estado é derivado na camada de apresentação).
    classificar.classificar(dados.get("cStat"), erro=erro)

    conn.execute(
        """
        INSERT INTO leituras (
          uf, documento, tp_amb, coletado_em, dh_recebto, cstat, msg, x_motivo,
          t_med, response_time, versao, ver_aplic, erro
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            uf,
            modelo["codigo"],
            tp_amb,
            datetime.now(timezone.utc).isoformat(),
            dados.get("dhRecbto"),
            None if dados.get("cStat") is None else str(dados.get("cStat")),
            dados.get("Msg"),
            dados.get("xMotivo"),
            _int_ou_none(dados.get("TMed")),
            _int_ou_none(dados.get("response_time") or dados.get("responseTime")),
            dados.get("versao"),
            dados.get("verAplic"),
            erro,
        ),
    )
    return erro is None


def executar_ciclo():
    """Roda um ciclo de coleta completo, relendo as configurações do banco.

    Itera sequencialmente modelos ativos × UFs × ambientes e grava uma leitura
    por consulta. Uma única conexão SQLite é aberta por ciclo e reutilizada
    (a concorrência do SQLite é limitada; abrir/fechar por leitura seria mais
    lento e arriscaria contenção de escrita).

    Returns:
        dict com ``total``, ``sucessos``, ``falhas`` e ``duracao_s``.
    """
    inicio = time.perf_counter()

    ufs = config.ufs_monitoradas()
    modelos = config.modelos_ativos_dfe()
    tp_ambs = Settings.lista_tp_ambs()
    timeout_s = config.timeout_s()

    logger.info(
        "Iniciando ciclo: %s modelo(s) × %s UF(s) × %s ambiente(s).",
        len(modelos),
        len(ufs),
        len(tp_ambs),
    )

    total = sucessos = falhas = 0
    with conexao() as conn:
        for modelo in modelos:
            for uf in ufs:
                for tp_amb in tp_ambs:
                    total += 1
                    if _coletar_uma(conn, modelo, uf, tp_amb, timeout_s):
                        sucessos += 1
                    else:
                        falhas += 1

    duracao_s = time.perf_counter() - inicio
    logger.info(
        "Ciclo concluído: total=%s sucessos=%s falhas=%s duração=%.1fs.",
        total,
        sucessos,
        falhas,
        duracao_s,
    )
    return {
        "total": total,
        "sucessos": sucessos,
        "falhas": falhas,
        "duracao_s": duracao_s,
    }


def _executar_e_reaplicar(scheduler):
    """Executa o ciclo e reaplica o intervalo caso tenha mudado no banco.

    O APScheduler fixa o intervalo no momento do agendamento. Para suportar
    mudança de ``intervalo_min`` sem reiniciar o processo (aceite do M1),
    comparamos o intervalo atual do job com o valor configurado e, se mudou,
    chamamos ``reschedule_job``.

    Args:
        scheduler: Instância de ``BackgroundScheduler`` já iniciada.

    Returns:
        None.
    """
    executar_ciclo()

    novo = config.intervalo_min()
    job = scheduler.get_job(_JOB_ID)
    if job is None:
        return
    minutos_atuais = job.trigger.interval.total_seconds() / 60
    if abs(minutos_atuais - novo) >= 0.001:
        # reschedule_job recria o trigger 'interval' com o novo intervalo.
        scheduler.reschedule_job(_JOB_ID, trigger="interval", minutes=novo)
        logger.info(
            "Intervalo de coleta alterado: %.1f → %s min (sem restart).",
            minutos_atuais,
            novo,
        )


def agendar(scheduler):
    """Registra o job de coleta no APScheduler.

    Args:
        scheduler: Instância de ``BackgroundScheduler``.

    Returns:
        str com o identificador do job.
    """
    intervalo = config.intervalo_min()
    scheduler.add_job(
        _executar_e_reaplicar,
        trigger="interval",
        minutes=intervalo,
        args=[scheduler],
        id=_JOB_ID,
        replace_existing=True,
    )
    logger.info("Job de coleta agendado a cada %s min.", intervalo)
    return _JOB_ID


if __name__ == "__main__":
    from src.utils.logger import configurar_logger

    carregar_env()
    configurar_logger("coletar")
    with conexao() as conn:
        criar_schema(conn)
    resumo = executar_ciclo()
    print(f"Resumo do ciclo: {resumo}")
