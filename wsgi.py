"""Ponto de entrada do gunicorn para o Monitor Status DFe.

Executado a partir da raiz do projeto com::

    gunicorn --workers 1 wsgi:app

O scheduler de coleta/retensão roda **dentro deste processo**, então o serviço
deve subir com exatamente 1 worker (múltiplos workers duplicariam as coletas) e
SEM ``--preload`` (o pré-carregamento não dispara o bootstrap do scheduler no
worker correto). A raiz do projeto já está no ``sys.path`` quando o gunicorn é
invocado daqui — não é preciso bootstrap adicional.
"""

from src.app import create_app, iniciar_scheduler
from src.utils.db import conexao, criar_schema
from src.utils.logger import configurar_logger
from src.utils.settings import carregar_env

carregar_env()
configurar_logger("app")
with conexao() as conn:
    criar_schema(conn)

app = create_app()
iniciar_scheduler()
