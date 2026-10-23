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

## Plataformas PaaS (ex.: botkeep.cloud)

Plataformas que alocam a porta HTTP via ambiente funcionam com o mesmo código: quando a variável `PORT` está definida no ambiente, ela **tem prioridade** sobre `web.porta` do `config.json`.

Procedimento típico (verifique os campos exatos no painel da plataforma):

1. **Fonte do código:** conecte o repositório GitHub (`ctecservice/monitor-status-dfe`) ou envie um ZIP da raiz do projeto (sem `.env`, sem `data/` e sem `logs/`).
2. **Runtime:** Python 3.12.
3. **Start command:** `python src/app.py` (caminho simples) ou `gunicorn --workers 1 --bind 0.0.0.0:$PORT wsgi:app` (mais robusto; use exatamente 1 worker).
4. **Dependências:** a plataforma instala via `requirements.txt` (já na raiz).
5. **Variáveis de ambiente (segredos no painel, nunca no ZIP):** `API_LOGIN_USUARIO`, `API_LOGIN_SENHA`, `MONITOR_MASTER_KEY` (gere uma com `python -c "import secrets; print(secrets.token_urlsafe(32))"`), e opcionalmente `TURNSTILE_SITE_KEY`/`TURNSTILE_SECRET_KEY` e `SESSION_COOKIE_SECURE=true`.
6. **Arquivos persistentes:** certifique-se de que `data/` (banco SQLite + backups) e `logs/` fiquem no **storage persistente** da plataforma; sem isso, o histórico é perdido a cada restart.

Confirme no painel que a plataforma expõe a porta HTTP publicamente (routing alocado) e acesse `https://SEU_DOMINIO/health` — deve retornar `"status": "ok"` e `"scheduler": "ativo"`.

> O agendador de coleta (APScheduler) roda dentro do processo da aplicação e não precisa de cron externo. Em plataformas com limite de memória pequeno (ex.: 512 MB), o caminho simples (`python src/app.py`) é suficiente; o gunicorn com 1 worker também cabe.

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

Com as duas chaves definidas, as rotas `/api/status`, `/api/historico` e `/api/uf/<uf>/historico` passam a exigir o cabeçalho `CF-Turnstile-Token` (ausente/inválido = `403`). Sem as chaves, a proteção fica **desligada**.

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

### Resetar o banco de dados (zerar o histórico)

O banco é um único arquivo SQLite em `data/statusdfe.db` (ou o caminho de `BANCO_CAMINHO` no `.env`). Para recomeçar do zero, **pare o monitor, apague o arquivo e suba de novo**: as tabelas e o modelo inicial (NF-e) são recriados automaticamente no boot.

1. Pare o serviço:

   ```bash
   sudo systemctl stop statusdfe
   ```

2. Apague o arquivo do banco (renomeie em vez de apagar se preferir poder restaurar):

   ```bash
   mv /opt/statusdfe/data/statusdfe.db /opt/statusdfe/data/statusdfe-antigo.db
   # limpe também os resíduos do modo WAL, se existirem
   rm -f /opt/statusdfe/data/statusdfe.db-wal /opt/statusdfe/data/statusdfe.db-shm
   ```

3. Suba o serviço novamente:

   ```bash
   sudo systemctl start statusdfe
   ```

O que acontece:

- O histórico de leituras (grade, uptime 24 h e gráfico de latência) **recomeça do zero**; o coletor volta a popular no próximo ciclo.
- **Nada muda** em `config.json` ou no `.env` — a chave mestra e as configurações continuam valendo (a tabela de segredos vazia é recriada sem problema).
- Os backups automáticos em `data/backups/` **não são removidos** por esse procedimento; apague a pasta manualmente se quiser zerar também as cópias.

Em container (Docker), o mesmo vale dentro do volume montado: pare o container e apague `data/statusdfe.db` no host. Em plataformas PaaS, o arquivo fica no **storage persistente** da plataforma (o arquivo local da sua máquina não afeta o site publicado).

---

## Frontend na Vercel

O frontend estático do monitor (o site público com o painel de grade/cards/gráfico de linha, os incidentes e o detalhe por UF) vive em `frontend/` e pode ser publicado de forma independente do backend, usando a Vercel como CDN/edge.

### Estrutura

A Vercel é configurada para servir **apenas** o conteúdo de `frontend/` como diretório de saída, via o arquivo `vercel.json` na raiz do repositório:

```json
{
  "outputDirectory": "frontend"
}
```

Isso significa que a URL pública da Vercel (ex.: `https://monitor-status-dfe.vercel.app`) entrega diretamente o `index.html`, os CSS, os JS e os logos de `frontend/assets/logos/`.

### Configurar `frontend/js/config.js`

Antes de fazer o deploy (ou logo em seguida), edite `frontend/js/config.js` e preencha os dois campos principais:

```js
window.MONITOR_CONFIG = {
  // URL pública do backend (API Flask). Ex.: "https://monitor.exemplo.com"
  // Deixe vazio se o próprio Flask estiver servindo o frontend.
  apiBaseUrl: "https://monitor.exemplo.com",

  // Site key do Cloudflare Turnstile (opcional).
  // Deixe vazio se o backend não estiver com Turnstile ativo.
  turnstileSiteKey: "0x4AAAAAAA..."
};
```

- **`apiBaseUrl`** aponta para onde o backend Flask está rodando. Quando o frontend é servido pelo próprio Flask (caminho simples), deixe vazio para usar URLs relativas. Na Vercel, é **obrigatório** apontar para a URL pública da API.
- **`turnstileSiteKey`** só deve ser preenchida quando o backend estiver com o Turnstile habilitado (`TURNSTILE_SITE_KEY` e `TURNSTILE_SECRET_KEY` no `.env`). Com a chave vazia, o widget não é carregado e os `fetch`es são comuns.

### Publicando na Vercel

1. No painel da Vercel, clique em **Import Project** e aponte para o repositório GitHub (`ctecservice/monitor-status-dfe`).
2. O framework preset pode ficar como **Other** (é um site estático multipágina, sem build).
3. A Vercel lê automaticamente o `vercel.json` e identifica `frontend/` como o diretório de saída.
4. Clique em **Deploy**. As próximas alterações na branch `main` (ou `master`) disparam deploys automáticos.

### Turnstile e domínio da Vercel

Se o backend estiver com o Turnstile ativo, a proteção exige que o domínio da Vercel esteja cadastrado no widget da Cloudflare. Após o primeiro deploy:

1. Copie o domínio atribuído pela Vercel (ex.: `monitor-status-dfe.vercel.app`) ou o domínio customizado que você configurou.
2. No painel da Cloudflare → **Turnstile** → edite o widget e adicione o domínio na lista de **Hostname Management**.
3. Sem esse passo, o backend retorna `403` e o frontend exibe o aviso de erro de anti-bot.

### Fonte única do frontend

O Flask serve **a mesma pasta `frontend/`**: a rota `/` entrega o `index.html` e os demais arquivos (páginas, CSS, JS e logos) são servidos direto de `frontend/`. A rota antiga `/uf/<UF>` agora redireciona (302) para `/detalhe.html?uf=<UF>&doc=..&amb=..`, preservando links e favoritos antigos. Assim, **uma única fonte de verdade** para o frontend: você desenvolve e ajusta em `frontend/`, e tanto a Vercel quanto o Flask (caminho simples `python src/app.py`) servem o mesmo conteúdo — sem duplicar arquivos.

### Headers CSP (opcional via `vercel.json`)

Se quiser reforçar a segurança com uma Content Security Policy estrita na Vercel, adicione um bloco `headers` ao `vercel.json`:

```json
{
  "outputDirectory": "frontend",
  "headers": [
    {
      "source": "/(.*)",
      "headers": [
        { "key": "Content-Security-Policy", "value": "default-src 'self'; script-src 'self' https://challenges.cloudflare.com; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self' https://monitor.exemplo.com https://challenges.cloudflare.com" },
        { "key": "X-Content-Type-Options", "value": "nosniff" },
        { "key": "Referrer-Policy", "value": "strict-origin-when-cross-origin" }
      ]
    }
  ]
}
```

Ajuste os domínios em `connect-src` conforme a URL pública da sua API.

---

## Frontend na Cloudflare Pages (alternativa gratuita à Vercel)

Como o frontend é 100% estático, qualquer serviço de hospedagem de sites estáticos funciona. Na **Cloudflare Pages**:

1. Painel da Cloudflare → **Workers & Pages** → **Create** → **Pages** → conecte o repositório.
2. **Build command:** deixe vazio. **Build output directory:** `frontend`.
3. Deploy. O domínio padrão será `https://<projeto>.pages.dev` (dá para anexar um domínio próprio).

Os mesmos passos da Vercel valem aqui: preencher `frontend/js/config.js` com `apiBaseUrl` (URL pública do backend) e `turnstileSiteKey` (quando o backend estiver com Turnstile — adicione o domínio `*.pages.dev` no widget da Cloudflare).

> **Sobre Cloudflare Workers (Python):** o backend **não** roda em Workers. O Workers executa código Python via WebAssembly (Pyodide), sem processos longos, sem socket convencional e sem arquivo SQLite local — este monitor precisa de um processo contínuo (agendador APScheduler), de um banco em disco e de chamadas HTTP de saída a cada ciclo. Use Workers/Pages apenas para o **frontend estático**; o backend fica num container/VPS (Coolify, abaixo, ou o caminho simples).

---

## Backend no Coolify (container)

O repositório já traz um `Dockerfile` na raiz (Python 3.12, `python src/app.py`, porta 5628, volumes em `/app/data` e `/app/logs`). Para publicar no Coolify:

1. **Servidor:** instale o Coolify numa VPS (ou use o Coolify Cloud). Crie um **Project**.
2. **Origem do código:** **New Resource → Aplicação** → *Build Pack: Dockerfile* → conecte o repositório (via integração **GitHub App** do Coolify em Sources, ou *Deploy Key*).
3. **Variáveis de ambiente** (no Coolify, **não** commite o `.env` no repositório — o código lê do ambiente, e o `.env` é apenas um facilitador local):
   - `API_LOGIN_USUARIO` e `API_LOGIN_SENHA` — credenciais da API DadosJah;
   - `MONITOR_MASTER_KEY` — gere com `python -c "import secrets; print(secrets.token_urlsafe(32))"` e **mantenha sempre a mesma** entre deploys (ela cifra os segredos do banco);
   - `TURNSTILE_SITE_KEY` e `TURNSTILE_SECRET_KEY` — para ligar o anti-bot em produção;
   - `SESSION_COOKIE_SECURE=true` — obrigatório sob HTTPS;
   - opcional: `PORT` (o Coolify redireciona a porta exposta pelo container; o padrão do projeto é 5628).
4. **Porta exposta:** 5628 (o `EXPOSE` do Dockerfile). O proxy do Coolify gera o domínio HTTPS automaticamente.
5. **Volumes persistentes** (senão o histórico e os logs somem a cada deploy):
   - volume em **`/app/data`** (banco SQLite + backups diários);
   - volume em **`/app/logs`** (logs por dia).
6. **Health check:** aponte para `GET /health` (responde 200 quando banco e agendador estão saudáveis; 503 caso contrário).
7. **Réplicas:** mantenha **1** (o agendador de coleta roda dentro do processo; mais de uma réplica duplicaria coletas). O mesmo vale se trocar o comando por gunicorn: **1 worker**.
8. **Configurações operacionais** (UFs, modelos `nfe,nfce`, intervalo, retenções): ficam no `config.json` da raiz — pode versioná-lo normalmente (não contém segredos) e ele entra na imagem via `COPY . .`.

Depois de publicado, se o frontend estiver na Vercel/Pages, preencha o `apiBaseUrl` do `config.js` com o domínio HTTPS do Coolify e adicione esse domínio na lista de hostnames do widget Turnstile (Cloudflare).

---

## Incorporar o painel em outra página (iframe)

O painel pode ser incorporado em uma página existente (ex.: uma página "Monitor" dentro do site dadosjah.com.br) com um simples iframe:

```html
<iframe
  src="https://SEU_DOMINIO_DO_MONITOR/?embed=1"
  style="width: 100%; height: 90vh; border: 0;"
  title="Painel de status dos serviços SEFAZ"
  loading="lazy"></iframe>
```

O parâmetro `?embed=1` ativa o **modo embed**: o painel é servido sem a barra superior, sem o rodapé e sem os links de navegação — apenas o conteúdo (filtros, grade, cards e gráfico de linha). O painel embutido informa à página-pai a altura real do conteúdo via `postMessage` (a página ajusta a altura do iframe, sem barra de rolagem interna). A navegação interna (detalhe por UF) continua funcionando dentro do iframe.

**Protocolo de altura (postMessage):** o painel em modo embed envia, sempre que a altura muda, a mensagem `{ "type": "monitor-status-dfe:resize", "height": <px> }` para `window.parent`. A página-pai deve escutá-la e ajustar a altura do iframe:

```js
window.addEventListener('message', function (evento) {
  var dados = evento.data || {};
  if (dados.type !== 'monitor-status-dfe:resize') return;
  var iframe = document.getElementById('iframe-monitor');
  if (iframe && typeof dados.height === 'number' && dados.height > 0) {
    iframe.style.height = Math.ceil(dados.height) + 'px';
  }
});
```

No Flask, a liberação do iframe (`frame-ancestors` + ausência de `X-Frame-Options`) vale para `/` e `/detalhe.html` quando o parâmetro `embed=1` está presente — os links internos do painel já o propagam.

**Controle de quem pode incorporar:**

- **Servido pelo Flask:** a resposta de `/` com `?embed=1` troca o bloqueio de frame (`frame-ancestors 'none'` + `X-Frame-Options: DENY`) pela lista de origens da variável **`EMBED_ORIGENS`** do `.env` (separadas por espaço; padrão: `https://dadosjah.com.br https://www.dadosjah.com.br`). Adicione ali os domínios dos sites que podem embutir o painel.
- **Servido pela Vercel/Cloudflare Pages:** os estáticos não enviam `X-Frame-Options` nem CSP por padrão, então o iframe funciona sem configuração. Se você ativar a CSP estrita sugerida acima, **não inclua** `frame-ancestors 'none'` — use a lista dos domínios permitidos (ou omita a diretiva).

> Com o Turnstile ativo, o domínio que serve o painel embutido (o do iframe, não o da página pai) precisa estar na lista de hostnames do widget na Cloudflare.

---

## Veja também

- [Como executar](como-executar.md)
- [Configuração](configuracao.md)
- [Arquitetura](arquitetura.md)
