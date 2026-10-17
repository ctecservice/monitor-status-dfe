import logging
import os
import secrets
import sys
from pathlib import Path

# Permite executar o modulo de qualquer pasta: coloca a raiz do projeto no sys.path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.utils import settings as settings_mod
from src.utils.db import conexao, criar_schema
from src.utils.settings import Settings, carregar_env

logger = logging.getLogger("configurar")

# Caminho do .env. Mantido como global de módulo para permitir testes que
# apontam para uma cópia temporária sem tocar no arquivo real.
CAMINHO_ENV = settings_mod.CAMINHO_ENV


def _tem_chave(caminho, chave):
    """Verifica se uma chave já existe no arquivo .env.

    Args:
        caminho: Path do arquivo .env.
        chave: Nome da chave a procurar.

    Returns:
        True se a chave estiver presente; False caso contrário.
    """
    if not caminho.exists():
        return False
    for linha in caminho.read_text(encoding="utf-8").splitlines():
        if linha.strip().startswith(f"{chave}="):
            return True
    return False


def anexar_master_key(master_key, caminho_env=None):
    """Acrescenta ``MONITOR_MASTER_KEY`` ao final do .env, se ainda não existir.

    Preserva todo o conteúdo atual e grava em UTF-8 sem BOM. Nunca usa
    PowerShell nem sobrescreve um valor já presente.

    Args:
        master_key: Valor da chave mestra a anexar.
        caminho_env: Path opcional do .env. Padrão: ``CAMINHO_ENV``.

    Returns:
        True se a chave foi anexada; False se já existia.
    """
    caminho = Path(caminho_env) if caminho_env else CAMINHO_ENV
    if _tem_chave(caminho, "MONITOR_MASTER_KEY"):
        return False
    conteudo = caminho.read_text(encoding="utf-8") if caminho.exists() else ""
    if conteudo and not conteudo.endswith("\n"):
        conteudo += "\n"
    conteudo += "\n# --- Seguranca ---\nMONITOR_MASTER_KEY=" + master_key + "\n"
    caminho.write_text(conteudo, encoding="utf-8")
    return True


def main():
    """Executa o preparo de primeiro boot (idempotente).

    Garante a master key no .env e cria/atualiza o schema do banco. As demais
    configurações operacionais ficam em ``config.json`` (raiz do projeto) e as
    credenciais da API permanecem no .env.

    Returns:
        None.
    """
    carregar_env(CAMINHO_ENV)

    master_key = Settings.MONITOR_MASTER_KEY
    if not master_key:
        nova = secrets.token_urlsafe(32)
        if anexar_master_key(nova, CAMINHO_ENV):
            print("Master key gerada e gravada no .env.")
            # Restringe o .env a leitura/escrita do dono. No Windows é no-op
            # (as permissões POSIX não se aplicam); na VPS Linux protege o arquivo.
            try:
                os.chmod(CAMINHO_ENV, 0o600)
            except OSError as exc:
                logger.warning("Não foi possível ajustar permissões do .env: %s", exc)
        # Disponibiliza a chave na memória para o restante da execução.
        os.environ["MONITOR_MASTER_KEY"] = nova
        setattr(Settings, "MONITOR_MASTER_KEY", nova)
    else:
        print("Master key já presente no .env (nada a fazer).")

    with conexao() as conn:
        criar_schema(conn)

    print(
        "Preparo concluído. Ajustes operacionais ficam em config.json; "
        "credenciais da API permanecem no .env."
    )


if __name__ == "__main__":
    from src.utils.logger import configurar_logger

    configurar_logger("configurar")
    main()
