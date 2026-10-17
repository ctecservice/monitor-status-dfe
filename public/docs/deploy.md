# Hospedagem (deploy)

Guia para publicar o Monitor Status DFe em um servidor Linux (VPS) com **gunicorn** atrás de um **nginx** com TLS.

> Exemplo em Debian/Ubuntu. Ajuste usuários, caminhos e domínio à sua realidade.

## Requisitos

- Uma VPS Linux com Python 3.12 instalado.
- Acesso SSH com um usuário (nos exemplos, `statusdfe`).
- Um domínio apontando para o IP do servidor (nos exemplos, `monitor.exemplo.com`).

Instale os pacotes de sistema:

```bash
sudo apt update
sudo apt install -y python3.12 python3.12-venv python3-pip nginx certbot python3-certbot-nginx
```

## 1. Obter o código e criar o ambiente

```bash
sudo mkdir -p /opt/statusdfe
sudo chown statusdfe:statusdfe /opt/statusdfe
cd /opt/statusdfe
git clone <URL_DO_REPOSITORIO> .
python3.12 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
pip install gunicorn
```

## 2. Configurar o `.env`

```bash
cp .env.example .env
```

Edite o `.env` e preencha as credenciais da API DadosJah (`API_LOGIN_USUARIO` e `API_LOGIN_SENHA`). Em produção com HTTPS, defina também:

```
SESSION_COOKIE_SECURE=true
```

Proteja o arquivo:

```bash
chmod 600 .env
```

## 3. Primeiro boot

Rode o script de primeiro boot para gerar a chave mestra, criar o banco e definir a senha do painel:

```bash
python src/scripts/configurar.py
```

## 4. Ponto de entrada do gunicorn

O agendador de coleta roda dentro do processo da aplicação. Crie um arquivo `wsgi.py` na raiz do projeto com um ponto de entrada que inicializa banco, logging e agendador antes de expor a aplicação:

```python
from datetime import timezone

from apscheduler.schedulers.background import BackgroundScheduler

from src.app import create_app
from src.jobs import coletar, reter
from src.utils.db import conexao, criar_schema
from src.utils.logger import configurar_logger
from src.utils.settings import carregar_env

carregar_env()
configurar_logger("app")
with conexao() as conn:
    criar_schema(conn)

app = create_app()

scheduler = BackgroundScheduler(timezone=timezone.utc)
coletar.agendar(scheduler)
reter.agendar(scheduler)
scheduler.start()
```

Teste a execução antes de seguir:

```bash
gunicorn --workers 1 --bind 127.0.0.1:8000 wsgi:app
```

> **Use exatamente 1 worker.** O agendador roda dentro do processo; múltiplos workers causariam coletas duplicadas. Não use a opção `--preload` do gunicorn.

## 5. Serviço systemd

Crie `/etc/systemd/system/statusdfe.service`:

```ini
[Unit]
Description=Monitor Status DFe
After=network.target

[Service]
User=statusdfe
Group=statusdfe
WorkingDirectory=/opt/statusdfe
Environment="PATH=/opt/statusdfe/.venv/bin"
ExecStart=/opt/statusdfe/.venv/bin/gunicorn --workers 1 --bind 127.0.0.1:8000 wsgi:app
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

Ative e inicie:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now statusdfe
sudo systemctl status statusdfe
```

## 6. nginx como proxy reverso

Crie `/etc/nginx/sites-available/statusdfe`:

```nginx
server {
    listen 80;
    server_name monitor.exemplo.com;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

Ative o site e recarregue:

```bash
sudo ln -s /etc/nginx/sites-available/statusdfe /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

## 7. TLS com Let's Encrypt

```bash
sudo certbot --nginx -d monitor.exemplo.com
```

O certbot ajusta o nginx para HTTPS e cuida da renovação automática. Com o HTTPS ativo, mantenha `SESSION_COOKIE_SECURE=true` no `.env` e reinicie o serviço:

```bash
sudo systemctl restart statusdfe
```

## 8. Verificação

- Acesse `https://monitor.exemplo.com/` e confirme que a grade carrega.
- Verifique `https://monitor.exemplo.com/health` (deve retornar `status: ok` e `scheduler: ativo`).
- Acompanhe os logs:

```bash
sudo journalctl -u statusdfe -f
```

## Recursos e manutenção

- **Requisitos modestos.** A aplicação é leve: um único processo Python e um banco SQLite em arquivo. Uma VPS pequena (1 vCPU, 512 MB–1 GB de RAM) é suficiente para o monitoramento típico.
- **Disco.** O consumo cresce com o histórico de leituras. Ajuste a **retenção de dados** e de **logs** pelo painel `/config` conforme o espaço disponível. Como o banco fica em `data/` e os logs em `logs/`, faça backup periódico da pasta do projeto.
- **Backup.** Para preservar o histórico, copie o arquivo do banco (e o `.env`, com cuidado por conter segredos) em uma rotina própria.

## Veja também

- [Configuração](configuracao.md)
- [Arquitetura](arquitetura.md)
