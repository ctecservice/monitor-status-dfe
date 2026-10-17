import sys
from pathlib import Path

# Permite executar o modulo de qualquer pasta: coloca a raiz do projeto no sys.path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

# Estados possíveis e suas cores do design system (seção 8 do plano).
ESTADO_OPERACIONAL = "operacional"
ESTADO_INSTAVEL = "instavel"
ESTADO_INDISPONIVEL = "indisponivel"
ESTADO_SEM_DADOS = "sem_dados"

COR_OPERACIONAL = "#22C55E"    # verde
COR_INSTAVEL = "#F59E0B"       # amarelo
COR_INDISPONIVEL = "#EF4444"   # vermelho
COR_SEM_DADOS = "#8A8585"      # cinza

# Mapa cStat -> (estado, cor). Fonte: API DadosJah (portal nacional DF-e).
_POR_CSTAT = {
    "107": (ESTADO_OPERACIONAL, COR_OPERACIONAL),
    "108": (ESTADO_INSTAVEL, COR_INSTAVEL),
    "109": (ESTADO_INDISPONIVEL, COR_INDISPONIVEL),
}


def classificar(cstat, erro=None):
    """Traduz o ``cStat`` da SEFAZ no estado do semáforo do monitor.

    Regras (seção 6 da especificação): ``107`` operacional, ``108`` instável,
    ``109`` indisponível. Qualquer outro valor de ``cStat`` — ou a presença de
    ``erro`` (timeout, rede, HTTP ≠ 200) — resulta em ``sem_dados``.

    Args:
        cstat: Código de status da SEFAZ (str ou int). Pode ser None.
        erro: Mensagem de erro da coleta, quando houver.

    Returns:
        dict ``{"estado": str, "cor": str}``.
    """
    if erro:
        return {"estado": ESTADO_SEM_DADOS, "cor": COR_SEM_DADOS}

    chave = str(cstat).strip() if cstat is not None else ""
    estado, cor = _POR_CSTAT.get(chave, (ESTADO_SEM_DADOS, COR_SEM_DADOS))
    return {"estado": estado, "cor": cor}


if __name__ == "__main__":
    for codigo in ("107", "108", "109", "999", None):
        print(codigo, "->", classificar(codigo))
    print("erro ->", classificar("107", erro="timeout"))
