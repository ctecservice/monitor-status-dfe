import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

# Permite executar o modulo de qualquer pasta: coloca a raiz do projeto no sys.path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.utils.db import conexao
from src.utils.settings import Settings

logger = logging.getLogger("config")

# Padrões defensivos usados quando a chave não existe no banco.
_PADROES = {
    "intervalo_min": 5,
    "timeout_s": 20,
    "retencao_dados_dias": 30,
    "retencao_logs_dias": 30,
}


def buscar_configuracao(chave):
    """Lê o valor de uma configuração no banco.

    Args:
        chave: Nome da configuração (ex.: ``intervalo_min``).

    Returns:
        Valor como str, ou None se a chave não existir.
    """
    with conexao() as conn:
        row = conn.execute(
            "SELECT valor FROM configuracoes WHERE chave = ?", (chave,)
        ).fetchone()
    return row["valor"] if row else None


def definir_configuracao(chave, valor):
    """Grava (insert ou update) uma configuração no banco.

    Args:
        chave: Nome da configuração.
        valor: Valor a persistir (será convertido para str).

    Returns:
        None.
    """
    agora = datetime.now(timezone.utc).isoformat()
    with conexao() as conn:
        conn.execute(
            "INSERT INTO configuracoes (chave, valor, atualizado_em) VALUES (?, ?, ?) "
            "ON CONFLICT(chave) DO UPDATE SET valor = excluded.valor, "
            "atualizado_em = excluded.atualizado_em",
            (chave, str(valor), agora),
        )
    logger.info("Configuração '%s' atualizada.", chave)


def _lista(chave):
    """Devolve o valor de uma configuração como lista de itens não vazios.

    Args:
        chave: Nome da configuração cujo valor é uma lista separada por vírgula.

    Returns:
        Lista de strings (vazia quando o valor é nulo ou vazio).
    """
    valor = buscar_configuracao(chave) or ""
    return [item.strip() for item in valor.split(",") if item.strip()]


def _inteiro(chave):
    """Devolve o valor de uma configuração como int, com fallback ao padrão.

    Args:
        chave: Nome da configuração numérica.

    Returns:
        int convertido do banco ou o padrão de ``_PADROES`` em caso de falha.
    """
    valor = buscar_configuracao(chave)
    padrao = _PADROES.get(chave)
    if valor is None:
        return padrao
    try:
        return int(valor)
    except (TypeError, ValueError):
        logger.warning("Configuração '%s' inválida (%r); usando padrão %s.", chave, valor, padrao)
        return padrao


def ufs_monitoradas():
    """Lista as UFs a consultar, relendo o banco a cada chamada.

    Quando ``ufs_monitoradas`` está vazio no banco, cai no padrão do ``.env``.

    Returns:
        Lista de siglas de UF em maiúsculas.
    """
    ufs = [uf.upper() for uf in _lista("ufs_monitoradas")]
    return ufs if ufs else Settings.lista_ufs()


def modelos_ativos():
    """Lista os códigos de modelos de DFe a consultar.

    Considera apenas modelos com ``ativo=1`` em ``modelos_dfe``. Quando a
    configuração ``modelos_ativos`` está vazia, retorna todos os ativos.

    Returns:
        Lista de códigos de modelo (ex.: ``["nfe"]``).
    """
    with conexao() as conn:
        rows = conn.execute(
            "SELECT codigo FROM modelos_dfe WHERE ativo = 1 ORDER BY codigo"
        ).fetchall()
    ativos = [row["codigo"] for row in rows]

    selecionados = [codigo.lower() for codigo in _lista("modelos_ativos")]
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
    return _inteiro("intervalo_min")


def timeout_s():
    """Timeout das requisições à API, em segundos.

    Returns:
        int (padrão 20).
    """
    return _inteiro("timeout_s")


def retencao_dados_dias():
    """Dias de retenção do histórico de leituras.

    Returns:
        int (padrão 30).
    """
    return _inteiro("retencao_dados_dias")


def retencao_logs_dias():
    """Dias de retenção dos arquivos de log.

    Returns:
        int (padrão 30).
    """
    return _inteiro("retencao_logs_dias")


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
