# Hospedagem (deploy)

Guia para publicar o Monitor Status DFe em um servidor Linux (VPS) ou em um container.

O caminho **simples** — recomendado para começar — roda o próprio servidor do Flask, sem nginx. Ele já é adequado para uso leve (um monitor interno, uma equipe pequena). Se você precisar de mais robustez, o caminho **avançado** com gunicorn + nginx fica no fim do documento.

> As configurações operacionais (UFs monitoradas, modelos, intervalo entre coletas, retenções, motor de coleta e links do rodapé) ficam no `config.json` da raiz do projeto, copiado de `config.example.json`. A porta HTTP também está lá (`web.porta`, padrão **5628**). Alterações no `config.json` exigem restart do processo.

## Requisitos

- Um servidor Linux (VPS ou container) com **Python 3.12** instalado.
- Acesso SSH com um usuário (nos exemplos, `statusdfe`).
- Credenciais de login da API DadosJah (`API_LOGIN_USUARIO` e `API_LOGIN_SENHA`).

---

## Caminho simples (recomendado para começar)

### 1. Obter o código e criar o ambiente

```bash
sudo mkdir -p /opt/statusdfe
sudo chown statusdfe:statusdfe /opt/statusdfe
cd /opt/statusdfe
git clone <URL_DO_REPOSITORIO> .
python3.12 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

### 2. Preparar as configurações

Copie os arquivos de exemplo e ajuste os valores:

```bash
cp config.example.json config.json
cp .env.example .env
```

No `config.json`, ajuste o que fizer sentido para a sua instalação (UFs, modelos, intervalo, retenção e a porta em `web.porta`). No `.env`, preencha as credenciais da API DadosJah (`API_LOGIN_USUARIO` e `API_LOGIN_SENHA`). Proteja o arquivo:

```bash
chmod 600 .env
```

### 3. Primeiro boot

Rode o script de primeiro boot para gerar a chave mestra e criar o banco:

```bash
python src/scripts/configurar.py
```

### 4. Iniciar o monitor

```bash
python src/app.py
```

O serviço sobe em `http://IP_DO_SERVIDOR:5628` (ou a porta que você definiu em `config.json`). O host já é `0.0.0.0`, então ele expõe a porta para a rede automaticamente. Ajuste o firewall se necessário:

```bash
sudo ufw allow 5628
```

> Aviso: aqui usamos o servidor de desenvolvimento do Flask (werkzeug). Ele é suficiente para uso leve, mas não é otimizado para alta carga. Para cargas maiores, use o caminho avançado abaixo.

### 5. Rodar em segundo plano (systemd)

Para manter o monitor rodando após fechar o SSH, crie `/etc/systemd/system/statusdfe.service`:

```ini
[Unit]
Description=Monitor Status DFe
After=network.target

[Service]
User=statusdfe
Group=statusdfe
WorkingDirectory=/opt/statusdfe
Environment="PATH=/opt/statusdfe/.venv/bin"
ExecStart=/opt/statusdfe/.venv/bin/python src/app.py
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

> Repare que **não há gunicorn** neste caminho: o `ExecStart` chama o `python src/app.py` diretamente.

---

## Alternativa com container (Docker)

O repositório traz um `Dockerfile`. Prepare `config.json` e `.env` **antes do build**, porque o Dockerfile faz `COPY . .` e leva esses arquivos para dentro da imagem:

```bash
cp config.example.json config.json   # ajuste a secao "web" (porta, etc.)
cp .env.example .env                 # preencha as credenciais da API
python src/scripts/configurar.py     # gere a master key no .env
```

Depois, faça o build e suba o container:

```bash
docker build -t monitor-status-dfe .
docker run -d -p 5628:5628 \
  -v $(pwd)/data:/app/data \
  -v $(pwd)/logs:/app/logs \
  monitor-status-dfe
```

Os volumes `data/` e `logs/` preservam o banco SQLite e os arquivos de log fora do container, para que sobrevivam a recriações. Ajuste a porta publicada se mudar `web.porta` no `config.json`.

---

## TLS (HTTPS) sem nginx

Para servir HTTPS de forma simples, sem instalar um proxy reverso na VPS, o caminho mais direto é colocar um serviço externo **em frente** à porta 5628 — por exemplo, o **Cloudflare** (proxy HTTPS gratuito apontando para o seu domínio). O Cloudflare termina o TLS e repassa a requisição para o servidor.

Se preferir TLS na própria VPS com certificado Let's Encrypt, o caminho natural exige nginx — veja a seção **Avançado (opcional)** abaixo, que já traz o `certbot` configurado.

> Ao usar HTTPS, mantenha `SESSION_COOKIE_SECURE=true` no `.env` e reinicie o serviço para que o cookie de sessão só trafegue sob HTTPS.

---

## Anti-robô das APIs públicas (opcional)

As APIs JSON já vêm com **rate limit por IP** (padrão 30 req/min, ajustável em `rate_limit.api_requisicoes_por_minuto` no `config.json`). Para reforçar a proteção contra abuso automatizado, é possível habilitar o **Cloudflare Turnstile**:

1. Crie um widget no painel da Cloudflare (Turnstile).
2. Preencha `TURNSTILE_SITE_KEY` e `TURNSTILE_SECRET_KEY` no `.env`.
3. Reinicie o serviço.

Com as duas chaves definidas, as rotas `/api/status` e `/api/uf/<uf>/historico` passam a exigir o cabeçalho `CF-Turnstile-Token` (ausente/inválido = `403`). Sem as chaves, a proteção fica **desligada**.

---

## Avançado (opcional): gunicorn + nginx

Use este caminho quando precisar de um servidor WSGI robusto e de um proxy reverso dedicado. O agendador de coleta roda dentro do processo da aplicação, por isso o gunicorn deve subir com **exatamente 1 worker**.

Instale os pacotes de sistema:

```bash
sudo apt update
sudo apt install -y nginx certbot python3-certbot-nginx
source /opt/statusdfe/.venv/bin/activate
pip install gunicorn
```

O arquivo `wsgi.py` **já vem pronto no repositório** (na raiz do projeto) e **não precisa ser criado**: ele carrega o `.env`, configura o logging, garante o schema do banco, cria a app Flask e inicia o agendador antes de expor `app` ao gunicorn.

Teste a execução antes de seguir:

```bash
gunicorn --workers 1 --bind 127.0.0.1:5628 wsgi:app
```

> **Use exatamente 1 worker.** Múltiplos workers causariam coletas duplicadas. Não use a opção `--preload`.

Serviço systemd (note o uso de `gunicorn` no `ExecStart`):

```ini
[Unit]
Description=Monitor Status DFe
After=network.target

[Service]
User=statusdfe
Group=statusdfe
WorkingDirectory=/opt/statusdfe
Environment="PATH=/opt/statusdfe/.venv/bin"
ExecStart=/opt/statusdfe/.venv/bin/gunicorn --workers 1 --bind 127.0.0.1:5628 wsgi:app
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

nginx como proxy reverso. Crie `/etc/nginx/sites-available/statusdfe`:

```nginx
server {
    listen 80;
    server_name monitor.exemplo.com;

    location / {
        proxy_pass http://127.0.0.1:5628;
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

TLS com Let's Encrypt:

```bash
sudo certbot --nginx -d monitor.exemplo.com
```

O certbot ajusta o nginx para HTTPS e cuida da renovação automática. Com o HTTPS ativo, mantenha `SESSION_COOKIE_SECURE=true` no `.env` e reinicie o serviço:

```bash
sudo systemctl restart statusdfe
```

---

## Verificação

Com o serviço no ar (em qualquer um dos caminhos), acesse:

- `http://SEU_IP:5628/` (ou `https://monitor.exemplo.com/` no caminho avançado) e confirme que a grade carrega.
- `http://SEU_IP:5628/health` — deve retornar `"status": "ok"` e `"scheduler": "ativo"`.

Acompanhe os logs:

```bash
sudo journalctl -u statusdfe -f
```

## Recursos e manutenção

- **Requisitos modestos.** A aplicação é leve: um único processo Python e um banco SQLite em arquivo. Uma VPS pequena (1 vCPU, 512 MB–1 GB de RAM) é suficiente para o monitoramento típico.
- **Disco.** O consumo cresce com o histórico de leituras. Ajuste a **retenção de dados** e de **logs** no `config.json` conforme o espaço disponível. Como o banco fica em `data/` e os logs em `logs/`, faça backup periódico da pasta do projeto.
- **Backup.** O monitor gera automaticamente, todos os dias às 02:00 (horário de Brasília), um backup compacto do banco em `data/backups/statusdfe-AAAAMMDD.db` (via `VACUUM INTO`). São mantidos apenas os **7 backups mais recentes**; ainda assim, para preservar o histórico, mantenha uma rotina própria de cópia da pasta do projeto (incluindo o `.env`, com cuidado por conter segredos).

## Veja também

- [Como executar](como-executar.md)
- [Configuração](configuracao.md)
- [Arquitetura](arquitetura.md)
