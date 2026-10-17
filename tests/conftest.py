"""Configuração comum dos testes (carrega .env, logging e schema do banco)."""

import sys
from pathlib import Path

# Coloca a raiz do projeto no sys.path (tests/ -> raiz).
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.utils.db import conexao, criar_schema
from src.utils.logger import configurar_logger
from src.utils.settings import carregar_env

# Executado uma vez na importação do conftest, antes da coleta dos testes.
carregar_env()
configurar_logger("testes")

with conexao() as _conn:
    criar_schema(_conn)
