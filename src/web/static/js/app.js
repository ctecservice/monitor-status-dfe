/* ============================================================================
   app.js — Monitor Status DFe
   - Dashboard (/): polling GET /api/status a cada 60s; toggle Produção/Homologação.
   - Detalhe (/uf/<uf>): gráfico de faixas em SVG (eixo Y semântico) + re-fetch
     de histórico ao trocar doc/amb.
   Tolerante a dados ausentes: não lança se pontos/células forem vazios.
   ============================================================================ */
(function () {
  'use strict';

  var INTERVALO_POLLING_MS = 60 * 1000;
  var CORES_ESTADO = {
    operacional: '#22C55E',
    instavel: '#F59E0B',
    indisponivel: '#EF4444',
    sem_dados: '#8A8585'
  };

  // ---------- Utilidades ----------
  function $(sel, ctx) { return (ctx || document).querySelector(sel); }
  function $$(sel, ctx) { return Array.prototype.slice.call((ctx || document).querySelectorAll(sel)); }

  function fmtMs(v) {
    if (v === null || v === undefined || v === '') return '—';
    var n = Number(v);
    return isNaN(n) ? '—' : n + ' ms';
  }

  // Latência exibida: prioriza o tempo de resposta medido pelo monitor
  // (response_time, ms) e usa o tempo médio informado pela SEFAZ (t_med, ms)
  // como alternativa quando a medição não existe.
  function latenciaDe(d) {
    if (!d) return null;
    var v = d.response_time;
    if (v === null || v === undefined || v === '') v = d.t_med;
    return (v === null || v === undefined || v === '') ? null : v;
  }

  function fmtDatetime(iso) {
    if (!iso) return '—';
    try {
      var d = new Date(iso);
      if (isNaN(d.getTime())) return iso;
      return d.toLocaleString('pt-BR', { dateStyle: 'short', timeStyle: 'short', timeZone: 'America/Sao_Paulo' });
    } catch (e) { return iso; }
  }

  function fmtHora(iso) {
    if (!iso) return '';
    try {
      var d = new Date(iso);
      if (isNaN(d.getTime())) return '';
      return d.toLocaleTimeString('pt-BR', {
        hour: '2-digit',
        minute: '2-digit',
        timeZone: 'America/Sao_Paulo'
      });
    } catch (e) { return ''; }
  }

  function joinUf(u, d) { return u + ':' + d; }

  // Lê o ambiente atualmente selecionado no toggle visível em tela.
  // Usado pelo dashboard (polling + heurística do banner) e pelo detalhe
  // sempre que for preciso saber "qual ambiente o usuário está vendo agora".
  function _tpAmbAtivo() {
    var btn = $('.ambiente-toggle__btn--ativo');
    return btn ? Number(btn.dataset.tpAmb) : 1;
  }

  // ---------- Anti-bot (Cloudflare Turnstile) ----------
  // Site key vem de uma meta tag, presente apenas quando o backend tem o
  // Turnstile configurado; sem ela, todo este bloco fica inerte e o fetch
  // funciona como um fetch comum.
  var turnstileSiteKey = (document.querySelector('meta[name="turnstile-site-key"]') || {}).content || '';
  var _ts = { widgetId: null, token: null, resetPromise: null };

  function _iniciarTurnstile() {
    if (!turnstileSiteKey || !window.turnstile) return;
    var div = document.createElement('div');
    div.style.display = 'none';
    document.body.appendChild(div);

    window.turnstile.ready(function () {
      _ts.widgetId = window.turnstile.render(div, {
        sitekey: turnstileSiteKey,
        callback: function (tok) {
          _ts.token = tok;
          if (_ts.resetPromise) {
            var p = _ts.resetPromise;
            _ts.resetPromise = null;
            clearTimeout(p.timer);
            p.resolve();
          }
        },
        'error-callback': function () {
          if (_ts.resetPromise) {
            var p = _ts.resetPromise;
            _ts.resetPromise = null;
            clearTimeout(p.timer);
            console.warn('[monitor] Turnstile reportar erro ao renovar o token.');
            p.reject(new Error('erro ao renovar o Turnstile'));
          }
        },
        'expired-callback': function () {
          if (_ts.resetPromise) {
            var p = _ts.resetPromise;
            _ts.resetPromise = null;
            clearTimeout(p.timer);
            p.reject(new Error('token do Turnstile expirou'));
          }
        },
        'refresh-expired': 'auto',
        appearance: 'interaction-only',
        language: 'pt-BR'
      });
    });
  }

  // Deferred "thenável": resolve/reject preenchidos depois (pelos callbacks do
  // widget) e .then encaminhado para a Promise interna, para o _fetchProtegido
  // poder encadear sem conhecer a mecânica do Turnstile.
  function _resetarTurnstile() {
    if (_ts.resetPromise) return _ts.resetPromise;
    if (!window.turnstile || _ts.widgetId === null) return Promise.resolve();

    var d = {};
    d.promise = new Promise(function (resolve, reject) {
      d.resolve = resolve;
      d.reject = reject;
    });
    d.then = function (onFulfilled, onRejected) {
      return d.promise.then(onFulfilled, onRejected);
    };
    d.timer = setTimeout(function () {
      if (_ts.resetPromise === d) {
        _ts.resetPromise = null;
      }
      console.warn('[monitor] Turnstile não renovou o token a tempo.');
      d.reject(new Error('timeout ao renovar o Turnstile'));
    }, 15000);
    _ts.resetPromise = d;

    try {
      window.turnstile.reset(_ts.widgetId);
    } catch (e) {
      if (_ts.resetPromise === d) {
        _ts.resetPromise = null;
      }
      clearTimeout(d.timer);
      console.warn('[monitor] falha ao reiniciar o Turnstile:', e);
      d.reject(e);
    }
    return d;
  }

  // Envia o token no header quando disponível; ao receber 403 com o Turnstile
  // ligado, renova o token e repete UMA vez a requisição.
  function _fetchProtegido(url) {
    var headers = {};
    if (_ts.token) headers['CF-Turnstile-Token'] = _ts.token;
    return fetch(url, { headers: headers }).then(function (r) {
      if (r.status === 403 && turnstileSiteKey && _ts.widgetId !== null) {
        _ts.token = null;
        return _resetarTurnstile().then(function () {
          var headers2 = {};
          if (_ts.token) headers2['CF-Turnstile-Token'] = _ts.token;
          return fetch(url, { headers: headers2 });
        });
      }
      return r;
    });
  }

  // ---------- Dashboard: toggle de ambiente ----------
  function initAmbienteToggle() {
    var botoes = $$('.ambiente-toggle__btn');
    if (!botoes.length) return;

    function aplicarAmbiente(tpAmb) {
      var novoAmb = Number(tpAmb);
      botoes.forEach(function (btn) {
        var ativo = Number(btn.dataset.tpAmb) === novoAmb;
        btn.classList.toggle('ambiente-toggle__btn--ativo', ativo);
        btn.setAttribute('aria-selected', ativo ? 'true' : 'false');
      });
      $$('.celula').forEach(function (cel) {
        var celAmb = Number(cel.dataset.tpAmb);
        if (celAmb === novoAmb) {
          cel.classList.remove('celula--oculta');
        } else {
          cel.classList.add('celula--oculta');
        }
      });
    }

    botoes.forEach(function (btn) {
      btn.addEventListener('click', function () {
        aplicarAmbiente(btn.dataset.tpAmb);
      });
    });

    aplicarAmbiente(1);
  }

  // ---------- Dashboard: render de célula ----------
  function atualizarCelula(cel, dados) {
    if (!cel || !dados) return;
    var cor = dados.cor || CORES_ESTADO.sem_dados;
    cel.style.setProperty('--celula-cor', cor);
    cel.classList.add('celula--preenchida');

    var estadoEl = $('.celula__estado', cel);
    var latEl = $('.celula__latencia', cel);
    if (estadoEl) estadoEl.textContent = dados.rotulo || 'Sem dados';
    if (latEl) latEl.textContent = fmtMs(latenciaDe(dados));

    var partes = [dados.rotulo || 'Sem dados'];
    var lat = latenciaDe(dados);
    if (lat !== null) partes.push(lat + ' ms');
    if (dados.erro) partes.push(dados.erro);
    else if (dados.cstat) partes.push('cStat ' + dados.cstat);
    cel.setAttribute('title', partes.join(' · '));
  }

  function inicializarCelulaVazia(cel) {
    if (cel.classList.contains('celula--preenchida')) return;
    cel.style.setProperty('--celula-cor', CORES_ESTADO.sem_dados);
    var estadoEl = $('.celula__estado', cel);
    if (estadoEl) estadoEl.textContent = 'Sem dados';
    var latEl = $('.celula__latencia', cel);
    if (latEl) latEl.textContent = '—';
    cel.setAttribute('title', 'Sem dados');
  }

  // ---------- Dashboard: polling /api/status ----------
  function iniciarPollingStatus() {
    var grade = document.getElementById('grade');
    if (!grade) return;

    var alertaEl = document.getElementById('alerta-painel');
    var geradoEl = document.getElementById('gerado-em');

    function aplicarDados(payload) {
      if (!payload || !Array.isArray(payload.celulas)) return;

      // Agrupa por UF:documento → {1: cel, 2: cel}
      var mapa = {};
      payload.celulas.forEach(function (c) {
        var chave = joinUf(c.uf, c.documento);
        if (!mapa[chave]) mapa[chave] = {};
        mapa[chave][c.tp_amb] = c;
      });

      // Atualiza cada célula do DOM
      $$('.grade__td').forEach(function (td) {
        var uf = td.dataset.uf;
        var doc = td.dataset.documento;
        var chave = joinUf(uf, doc);
        var dados = mapa[chave];
        var c1 = dados && dados[1];
        var c2 = dados && dados[2];

        var cel1 = $('[data-tp-amb="1"]', td);
        var cel2 = $('[data-tp-amb="2"]', td);

        if (c1) atualizarCelula(cel1, c1); else if (cel1) inicializarCelulaVazia(cel1);
        if (c2) atualizarCelula(cel2, c2); else if (cel2) inicializarCelulaVazia(cel2);
      });

      // Atualiza timestamp
      if (payload.gerado_em && geradoEl) {
        geradoEl.textContent = fmtDatetime(payload.gerado_em);
        geradoEl.setAttribute('datetime', payload.gerado_em);
      }

      // Heurística: se > 80% das células do ambiente ATIVO (lido do DOM) estão
      // "sem_dados" ou erro, avisa que a fonte pode estar fora do ar. Usar
      // _tpAmbAtivo() garante que o banner reflete o ambiente que o usuário
      // está vendo agora, não um valor capturado no boot.
      var tpAmbAtivo = _tpAmbAtivo();
      var total = 0, semDados = 0;
      $$('.grade__td').forEach(function (td) {
        var chave = joinUf(td.dataset.uf, td.dataset.documento);
        var dados = mapa[chave];
        var cel = dados && dados[tpAmbAtivo];
        total++;
        if (!cel || cel.estado === 'sem_dados' || cel.erro) semDados++;
      });
      if (total && semDados / total > 0.8) {
        if (alertaEl) {
          alertaEl.hidden = false;
          alertaEl.textContent = 'A maioria das células está sem dados — a fonte pode estar indisponível no momento.';
        }
      } else if (alertaEl) {
        alertaEl.hidden = true;
      }
    }

    function buscar() {
      _fetchProtegido('/api/status')
        .then(function (r) {
          if (!r.ok) throw new Error('HTTP ' + r.status);
          return r.json();
        })
        .then(aplicarDados)
        .catch(function (err) {
          console.warn('[monitor] falha ao buscar /api/status:', err);
        });
    }

    buscar();
    setInterval(buscar, INTERVALO_POLLING_MS);
  }

  // ---------- Detalhe: gráfico de faixas (eixo Y semântico) ----------
  // O eixo Y não mostra valores numéricos de latência: mostra 5 faixas de SLA,
  // de "Erro" (topo) a "≤ 2s (normal)" (base). Cada ponto é posicionado no
  // centro da faixa correspondente à sua latência (ou estado), e colorido
  // pela cor do estado.
  function desenharSparkline(container, pontos) {
    if (!container) return;
    container.innerHTML = '';
    container.classList.remove('sparkline--vazio');

    if (!pontos || !pontos.length) {
      container.classList.add('sparkline--vazio');
      container.textContent = 'Sem coletas no período.';
      return;
    }

    // Dimensões internas do SVG
    var W = 600, H = 280;
    var X0 = 110, X1 = 580;         // faixa útil horizontal
    var Y0 = 20, Y1 = 260;          // faixa útil vertical
    var FAIXA_ALT = (Y1 - Y0) / 5;  // 48px por faixa

    // Faixas semânticas (do topo para a base)
    var faixas = [
      { label: 'Erro',  cor: '#FEE2E2' },
      { label: '> 30s', cor: '#FEF3C7' },
      { label: '< 30s', cor: '#FFEDD5' },
      { label: '≤ 5s',  cor: '#DBEAFE' },
      { label: '≤ 2s',  cor: '#DCFCE7' }
    ];

    // Mapeia um ponto para o índice da faixa correspondente
    function faixaDe(p) {
      if (p.estado === 'indisponivel' || p.estado === 'sem_dados') return 0;
      var v = latenciaDe(p);
      if (v === null) return 0;
      if (v > 30000) return 1;
      if (v > 5000)  return 2;
      if (v > 2000)  return 3;
      return 4;
    }

    var svgNS = 'http://www.w3.org/2000/svg';
    var svg = document.createElementNS(svgNS, 'svg');
    svg.setAttribute('viewBox', '0 0 ' + W + ' ' + H);
    svg.setAttribute('preserveAspectRatio', 'none');
    svg.setAttribute('role', 'img');
    svg.setAttribute('aria-label', 'Gráfico de latência nas últimas 24 horas, com faixas semânticas');
    svg.classList.add('sparkline__svg');

    // 1) Retângulos de fundo das faixas
    faixas.forEach(function (f, i) {
      var rect = document.createElementNS(svgNS, 'rect');
      rect.setAttribute('x', X0);
      rect.setAttribute('y', Y0 + i * FAIXA_ALT);
      rect.setAttribute('width', X1 - X0);
      rect.setAttribute('height', FAIXA_ALT);
      rect.setAttribute('fill', f.cor);
      svg.appendChild(rect);
    });

    // 2) Labels Y (rótulos das faixas)
    faixas.forEach(function (f, i) {
      var txt = document.createElementNS(svgNS, 'text');
      txt.setAttribute('x', X0 - 10);
      txt.setAttribute('y', Y0 + i * FAIXA_ALT + FAIXA_ALT / 2 + 3);
      txt.setAttribute('text-anchor', 'end');
      txt.setAttribute('class', 'sparkline__faixa-texto');
      txt.textContent = f.label;
      svg.appendChild(txt);
    });

    // 3) Linhas de grade horizontais (separando as faixas)
    for (var i = 1; i < faixas.length; i++) {
      var y = Y0 + i * FAIXA_ALT;
      var line = document.createElementNS(svgNS, 'line');
      line.setAttribute('x1', X0);
      line.setAttribute('x2', X1);
      line.setAttribute('y1', y);
      line.setAttribute('y2', y);
      line.setAttribute('class', 'sparkline__grade-linha');
      svg.appendChild(line);
    }

    // 4) Borda esquerda (eixo Y)
    var eixo = document.createElementNS(svgNS, 'line');
    eixo.setAttribute('x1', X0);
    eixo.setAttribute('x2', X0);
    eixo.setAttribute('y1', Y0);
    eixo.setAttribute('y2', Y1);
    eixo.setAttribute('stroke', '#CBD5E1');
    eixo.setAttribute('stroke-width', '1');
    svg.appendChild(eixo);

    // 5) Mapeia pontos para coordenadas
    var n = pontos.length;
    var coords = pontos.map(function (p, idx) {
      var faixa = faixaDe(p);
      var cx = n > 1 ? X0 + idx * ((X1 - X0) / (n - 1)) : (X0 + X1) / 2;
      var cy = Y0 + faixa * FAIXA_ALT + FAIXA_ALT / 2;
      var v = latenciaDe(p);
      return {
        i: idx,
        cx: cx,
        cy: cy,
        estado: p.estado,
        t_med: v,
        coletado_em: p.coletado_em
      };
    });

    // 6) Linha conectando pontos (na ordem temporal)
    if (coords.length > 1) {
      var d = coords.map(function (c, idx) {
        return (idx === 0 ? 'M' : 'L') + c.cx.toFixed(1) + ',' + c.cy.toFixed(1);
      }).join(' ');
      var path = document.createElementNS(svgNS, 'path');
      path.setAttribute('d', d);
      path.setAttribute('class', 'sparkline__path');
      svg.appendChild(path);
    }

    // 7) Pontos (círculos coloridos por estado)
    coords.forEach(function (c) {
      var circle = document.createElementNS(svgNS, 'circle');
      circle.setAttribute('cx', c.cx.toFixed(1));
      circle.setAttribute('cy', c.cy.toFixed(1));
      circle.setAttribute('r', '3.5');
      circle.setAttribute('class', 'sparkline__ponto');
      circle.setAttribute('fill', CORES_ESTADO[c.estado] || CORES_ESTADO.sem_dados);
      circle.setAttribute('tabindex', '0');
      var title = document.createElementNS(svgNS, 'title');
      var lat = c.t_med !== null && c.t_med !== undefined ? c.t_med + ' ms' : '—';
      title.textContent = fmtDatetime(c.coletado_em) + ' · ' + lat + ' · ' + (c.estado || 'sem dados');
      circle.appendChild(title);
      svg.appendChild(circle);
    });

    // 8) Eixo X: ~6 timestamps distribuídos, rotacionados -45°
    var passo = Math.max(1, Math.floor(n / 6));
    for (var j = 0; j < n; j += passo) {
      var c = coords[j];
      var txt = document.createElementNS(svgNS, 'text');
      var ty = Y1 + 18;
      txt.setAttribute('x', c.cx.toFixed(1));
      txt.setAttribute('y', ty);
      txt.setAttribute('text-anchor', 'end');
      txt.setAttribute('class', 'sparkline__eixo-x-texto');
      txt.setAttribute('transform', 'rotate(-45 ' + c.cx.toFixed(1) + ' ' + ty + ')');
      txt.textContent = fmtHora(c.coletado_em);
      svg.appendChild(txt);
    }

    // Último ponto sempre visível no eixo X, se ainda não foi incluído
    if ((n - 1) % passo !== 0 && n > 1) {
      var ultimo = coords[n - 1];
      var txt2 = document.createElementNS(svgNS, 'text');
      var ty2 = Y1 + 18;
      txt2.setAttribute('x', ultimo.cx.toFixed(1));
      txt2.setAttribute('y', ty2);
      txt2.setAttribute('text-anchor', 'end');
      txt2.setAttribute('class', 'sparkline__eixo-x-texto');
      txt2.setAttribute('transform', 'rotate(-45 ' + ultimo.cx.toFixed(1) + ' ' + ty2 + ')');
      txt2.textContent = fmtHora(ultimo.coletado_em);
      svg.appendChild(txt2);
    }

    container.appendChild(svg);
  }

  // ---------- Detalhe: re-fetch de histórico ----------
  function iniciarDetalhe() {
    // A UF vem do atributo data-uf do <body> (sem dados inline no template).
    var uf = document.body.getAttribute('data-uf');
    if (!uf) return;

    var docBtnAtivo = $('.seletor-documento__btn--ativo');
    var documento = docBtnAtivo ? docBtnAtivo.dataset.documento : '';

    var ambBtnAtivo = $('.ambiente-toggle__btn--ativo');
    var tpAmb = ambBtnAtivo ? Number(ambBtnAtivo.dataset.tpAmb) : 1;

    var sparklineEl = document.getElementById('sparkline');
    var uptimePctEl = document.getElementById('uptime-pct');
    var uptimeFillEl = document.getElementById('uptime-fill');
    var badgeEstadoEl = document.getElementById('badge-estado');
    var campoMotivo = document.getElementById('campo-motivo');
    var campoCstat = document.getElementById('campo-cstat');
    var campoVerAplic = document.getElementById('campo-ver-aplic');
    var campoLatencia = document.getElementById('campo-latencia');
    var campoDhRecebto = document.getElementById('campo-dh-recebto');
    var campoColetadoEm = document.getElementById('campo-coletado-em');
    var campoMsg = document.getElementById('campo-msg');
    var ambienteRotuloEl = document.getElementById('detalhe-ambiente-rotulo');

    function aplicarUltimo(ultimo) {
      if (!ultimo) {
        if (badgeEstadoEl) {
          badgeEstadoEl.textContent = 'Sem dados';
          badgeEstadoEl.style.background = CORES_ESTADO.sem_dados;
        }
        [campoMotivo, campoCstat, campoVerAplic, campoDhRecebto, campoColetadoEm, campoMsg].forEach(function (el) {
          if (el) el.textContent = '—';
        });
        if (campoLatencia) campoLatencia.textContent = '—';
        return;
      }
      if (badgeEstadoEl) {
        badgeEstadoEl.textContent = ultimo.rotulo || 'Sem dados';
        badgeEstadoEl.style.background = ultimo.cor || CORES_ESTADO.sem_dados;
      }
      if (campoMotivo) campoMotivo.textContent = ultimo.x_motivo || '—';
      if (campoCstat) campoCstat.textContent = ultimo.cstat || '—';
      if (campoVerAplic) campoVerAplic.textContent = ultimo.ver_aplic || '—';
      if (campoLatencia) campoLatencia.textContent = fmtMs(latenciaDe(ultimo));
      if (campoDhRecebto) campoDhRecebto.textContent = ultimo.dh_recebto || '—';
      if (campoColetadoEm) campoColetadoEm.textContent = fmtDatetime(ultimo.coletado_em);
      if (campoMsg) campoMsg.textContent = ultimo.msg || '—';
    }

    function aplicarHistorico(payload) {
      if (!payload) return;

      // D10: quando não há pontos na janela, exibe "—" no uptime e barra em 0%.
      var semPontos = !Array.isArray(payload.pontos) || payload.pontos.length === 0;

      if (Array.isArray(payload.pontos)) desenharSparkline(sparklineEl, payload.pontos);

      if (semPontos) {
        if (uptimePctEl) uptimePctEl.textContent = '—';
        if (uptimeFillEl) uptimeFillEl.style.width = '0%';
      } else if (typeof payload.uptime_pct === 'number') {
        if (uptimePctEl) uptimePctEl.textContent = payload.uptime_pct.toFixed(1);
        if (uptimeFillEl) uptimeFillEl.style.width = payload.uptime_pct + '%';
      }

      if (payload.ultimo) aplicarUltimo(payload.ultimo);
    }

    function buscarHistorico(doc, amb) {
      var url = '/api/uf/' + encodeURIComponent(uf) + '/historico'
        + '?horas=24'
        + '&documento=' + encodeURIComponent(doc)
        + '&tp_amb=' + encodeURIComponent(amb);
      return _fetchProtegido(url)
        .then(function (r) {
          if (!r.ok) throw new Error('HTTP ' + r.status);
          return r.json();
        })
        .then(aplicarHistorico)
        .catch(function (err) {
          console.warn('[monitor] falha ao buscar histórico:', err);
        });
    }

    // Render inicial: o template já entrega o estado server-side (Jinja); o
    // fetch apenas refaz/atualiza sparkline, uptime e último status.
    buscarHistorico(documento, tpAmb);

    // Toggle de ambiente (usa o estado local tpAmb para evitar refetch duplicado)
    var botoesAmb = $$('.ambiente-toggle__btn');
    botoesAmb.forEach(function (btn) {
      var ativo = Number(btn.dataset.tpAmb) === tpAmb;
      btn.classList.toggle('ambiente-toggle__btn--ativo', ativo);
      btn.setAttribute('aria-selected', ativo ? 'true' : 'false');
      btn.addEventListener('click', function () {
        var novoAmb = Number(btn.dataset.tpAmb);
        if (novoAmb === tpAmb) return;
        botoesAmb.forEach(function (b) {
          b.classList.toggle('ambiente-toggle__btn--ativo', Number(b.dataset.tpAmb) === novoAmb);
          b.setAttribute('aria-selected', Number(b.dataset.tpAmb) === novoAmb ? 'true' : 'false');
        });
        tpAmb = novoAmb;
        if (ambienteRotuloEl) ambienteRotuloEl.textContent = btn.textContent.trim();
        buscarHistorico(documento, novoAmb);
      });
    });

    // Seletor de documento
    var botoesDoc = $$('.seletor-documento__btn');
    botoesDoc.forEach(function (btn) {
      btn.addEventListener('click', function () {
        var novoDoc = btn.dataset.documento;
        if (novoDoc === documento) return;
        botoesDoc.forEach(function (b) {
          b.classList.toggle('seletor-documento__btn--ativo', b.dataset.documento === novoDoc);
        });
        documento = novoDoc;
        buscarHistorico(documento, tpAmb);
      });
    });
  }

  // ---------- Bootstrap ----------
  function init() {
    _iniciarTurnstile();
    initAmbienteToggle();
    iniciarPollingStatus();
    iniciarDetalhe();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
