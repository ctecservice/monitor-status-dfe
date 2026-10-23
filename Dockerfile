# Monitor Status DFe - imagem de execucao
# Build: docker build -t monitor-status-dfe .
# Run:   docker run -d -p 5628:5628 \
#          --env-file .env \
#          -v $(pwd)/data:/app/data -v $(pwd)/logs:/app/logs \
#          monitor-status-dfe
#
# As credenciais e a master key NAO entram na imagem: passe-as em runtime
# via --env-file .env (ou variaveis de ambiente do orquestrador). O
# .dockerignore exclui .env, config.json, data/, logs/ e docs/ do build.
# O config.json pode ser montado como volume ou substituido no deploy.

FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 5628

CMD ["python", "src/app.py"]
