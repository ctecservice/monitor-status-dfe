import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# Permite executar o modulo de qualquer pasta: coloca a raiz do projeto no sys.path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.motores import criar_motor
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


def _tmed_para_ms(valor):
    """Converte o TMed da SEFAZ (segundos) para milissegundos inteiros.

    A SEFAZ informa o tempo médio de resposta do serviço em **segundos**
    (ex.: ``"1"`` ou ``0.432``); o projeto armazena e exibe em ms.

    Args:
        valor: Valor bruto da API (str, int, float ou None).

    Returns:
        int (ms) ou None quando ausente/incapaz de converter.
    """
    if valor is None or valor == "":
        return None
    try:
        return int(round(float(valor) * 1000))
    except (TypeError, ValueError):
        return None


def _coletar_uma(conn, motor, modelo, uf, tp_amb, timeout_s, token):
    """Executa uma consulta pelo motor e grava a leitura correspondente.

    A falha da API não levanta exceção: a leitura é gravada com o campo
    ``erro`` preenchido e o ciclo continua.

    Args:
        conn: Conexão SQLite reutilizada pelo ciclo.
        motor: Motor de consulta criado no início do ciclo.
        modelo: Dicionário do modelo (``codigo``, ``nome``, ``endpoint``).
        uf: Sigla da UF.
        tp_amb: Ambiente (1 = produção, 2 = homologação).
        timeout_s: Timeout da requisição, em segundos.
        token: Credencial obtida pelo motor no início do ciclo.

    Returns:
        True se a consulta teve sucesso, False caso contrário.
    """
    resultado = motor.consultar_status(
        uf, modelo["endpoint"], tp_amb, timeout_s, token
    )
    dados = resultado["dados"] or {}
    erro = resultado["erro"]

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
            _tmed_para_ms(dados.get("TMed")),
            _int_ou_none(dados.get("response_time") or dados.get("responseTime")),
            dados.get("versao"),
            dados.get("verAplic"),
            erro,
        ),
    )
    return erro is None


def executar_ciclo():
    """Roda um ciclo de coleta completo, usando as configurações em memória.

    O ciclo autentica no motor configurado (``config.motor_ativo()``) antes das
    consultas e encerra a sessão no final, mesmo em caso de erro. O token fica
    em memória apenas durante o ciclo: todas as consultas usam a mesma
    credencial e o logout é garantido no ``finally``. Se a autenticação falhar,
    nenhuma consulta é feita e o resumo volta zerado.

    Itera sequencialmente modelos ativos × UFs × ambientes e grava uma leitura
    por consulta, com uma pequena pausa entre consultas
    (``Settings.DELAY_ENTRE_CONSULTAS_S``, configurável no .env) para respeitar
    o rate limit global da API DadosJah (10 req/s e 150 req/min). Uma única
    conexão SQLite é aberta por ciclo e reutilizada (a concorrência do SQLite
    é limitada; abrir/fechar por leitura seria mais lento e arriscaria
    contenção de escrita).

    Returns:
        dict com ``total``, ``sucessos``, ``falhas`` e ``duracao_s``.
    """
    inicio = time.perf_counter()

    ufs = config.ufs_monitoradas()
    modelos = config.modelos_ativos_dfe()
    tp_ambs = Settings.lista_tp_ambs()
    timeout_s = config.timeout_s()

    motor_nome = config.motor_ativo()
    motor = criar_motor(motor_nome)

    try:
        token = motor.autenticar()
    except Exception as exc:
        duracao_s = time.perf_counter() - inicio
        logger.error("Falha ao autenticar no motor '%s': %s", motor_nome, exc)
        return {"total": 0, "sucessos": 0, "falhas": 0, "duracao_s": duracao_s}

    logger.info(
        "Iniciando ciclo (motor=%s): %s modelo(s) × %s UF(s) × %s ambiente(s).",
        motor_nome,
        len(modelos),
        len(ufs),
        len(tp_ambs),
    )

    total = sucessos = falhas = 0
    try:
        with conexao() as conn:
            for modelo in modelos:
                for uf in ufs:
                    for tp_amb in tp_ambs:
                        total += 1
                        if _coletar_uma(
                            conn, motor, modelo, uf, tp_amb, timeout_s, token
                        ):
                            sucessos += 1
                        else:
                            falhas += 1
                        # Commit por leitura: em WAL, gravar cada INSERT de
                        # imediato evita que uma exceção no meio do ciclo
                        # descarte (rollback do context manager) as leituras
                        # já coletadas.
                        conn.commit()
                        # Pausa entre consultas para respeitar o rate limit
                        # global da API (10 req/s; 150 req/min). Configurável
                        # no .env via DELAY_ENTRE_CONSULTAS_S.
                        time.sleep(Settings.DELAY_ENTRE_CONSULTAS_S)
    finally:
        # Logout sempre executado; falha no encerramento não interrompe o job.
        try:
            motor.encerrar(token)
        except Exception as exc:
            logger.warning(
                "Falha ao encerrar sessão do motor '%s': %s", motor_nome, exc
            )

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
