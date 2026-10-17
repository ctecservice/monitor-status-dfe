import logging
import sys
from pathlib import Path

# Permite executar o modulo de qualquer pasta: coloca a raiz do projeto no sys.path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.motores.dadosjah import MotorDadosJah

logger = logging.getLogger("motores")

# Registro dos motores disponíveis (chave = valor aceito em ``motor_ativo``).
# Para suportar uma nova API: crie ``src/motores/<api>.py`` com uma subclasse
# de ``MotorBase`` e adicione a classe neste dicionário.
_MOTORES = {
    "dadosjah": MotorDadosJah,
}


def criar_motor(nome):
    """Cria a instância do motor de consulta correspondente ao nome.

    Cada chamada devolve uma instância nova (sem estado compartilhado entre
    ciclos de coleta).

    Args:
        nome: Identificador do motor, conforme ``configuracoes.motor_ativo``
            (ex.: ``"dadosjah"``).

    Returns:
        MotorBase: instância concreta do motor solicitado.

    Raises:
        ValueError: quando o nome é vazio ou não está registrado em ``_MOTORES``.
    """
    chave = str(nome or "").strip().lower()
    classe = _MOTORES.get(chave)
    if classe is None:
        disponiveis = ", ".join(sorted(_MOTORES))
        raise ValueError(
            f"Motor de consulta desconhecido: {nome!r}. Disponíveis: {disponiveis}."
        )
    logger.debug("Motor de consulta criado: %s", chave)
    return classe()


if __name__ == "__main__":
    from src.utils.logger import configurar_logger
    from src.utils.settings import carregar_env

    carregar_env()
    configurar_logger("motores")
    for nome_motor in _MOTORES:
        print(nome_motor, "->", criar_motor(nome_motor).nome)
