/* ============================================================================
   app.js — Monitor Status DFe
   - Dashboard (/): polling GET /api/status a cada 60s; toggle Produção/Homologação.
   - Detalhe (/uf/<uf>): sparkline em SVG + re-fetch de histórico ao trocar doc/amb.
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

  function fmtDatetime(iso) {
    if (!iso) return '—';
    try {
      var d = new Date(iso);
      if (isNaN(d.getTime())) return iso;
      return d.toLocaleString('pt-BR', { dateStyle: 'short', timeStyle: 'short' });
    } catch (e) { return iso; }
  }

  function joinUf(u, d) { return u + ':' + d; }

  // ---------- Dashboard: toggle de ambiente ----------
  function initAmbienteToggle() {
    var botoes = $$('.ambiente-toggle__btn');
    if (!botoes.length) return;

    // Estado ativo: 1 (Produção) por padrão
    var tpAmbAtivo = 1;

    function aplicarAmbiente(tpAmb) {
      tpAmbAtivo = Number(tpAmb);
      botoes.forEach(function (btn) {
        var ativo = Number(btn.dataset.tpAmb) === tpAmbAtivo;
        btn.classList.toggle('ambiente-toggle__btn--ativo', ativo);
        btn.setAttribute('aria-selected', ativo ? 'true' : 'false');
      });
      $$('.celula').forEach(function (cel) {
        var celAmb = Number(cel.dataset.tpAmb);
        if (celAmb === tpAmbAtivo) {
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
    if (estadoEl) estadoEl.textContent = dados.estado || 'Sem dados';
    if (latEl) latEl.textContent = fmtMs(dados.t_med);

    var partes = [dados.estado || 'Sem dados'];
    if (dados.t_med !== null && dados.t_med !== undefined) partes.push(dados.t_med + ' ms');
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

    var tpAmbAtivo = 1;
    // Observa o toggle ativo (o mesmo state do initAmbienteToggle)
    var btnAtivo = $('.ambiente-toggle__btn--ativo');
    if (btnAtivo) tpAmbAtivo = Number(btnAtivo.dataset.tpAmb);

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

      // Atualiza timestamp e alerta de saúde da fonte
      if (payload.gerado_em && geradoEl) {
        geradoEl.textContent = fmtDatetime(payload.gerado_em);
        geradoEl.setAttribute('datetime', payload.gerado_em);
      }

      // Heurística: se > 80% das células do ambiente ativo estão "sem_dados" ou erro,
      // avisa que a fonte pode estar fora do ar (mitiga "tudo vermelho").
      var total = 0, semDados = 0;
      $$('.grade__td').forEach(function (td) {
        var cel = $('[data-tp-amb="' + tpAmbAtivo + '"]', td);
        if (!cel) return;
        total++;
        var estadoEl = $('.celula__estado', cel);
        if (estadoEl && estadoEl.textContent === 'Sem dados') semDados++;
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
      fetch('/api/status')
        .then(function (r) {
          if (!r.ok) throw new Error('HTTP ' + r.status);
          return r.json();
        })
        .then(aplicarDados)
        .catch(function (err) {
          console.warn('[monitor] falha ao buscar /api/status:', err);
          // Não quebra a página; mantém estado atual.
        });
    }

    // Primeiro fetch imediato, depois a cada 60s
    buscar();
    setInterval(buscar, INTERVALO_POLLING_MS);
  }

  // ---------- Detalhe: sparkline em SVG ----------
  function desenharSparkline(container, pontos) {
    if (!container) return;
    container.innerHTML = '';

    if (!pontos || !pontos.length) {
      container.classList.add('sparkline--vazio');
      container.textContent = 'Sem coletas no período.';
      return;
    }

    var W = 600, H = 120, PAD = 4;
    // Valores válidos de latência
    var valores = pontos.map(function (p, i) {
      var v = (p.t_med !== null && p.t_med !== undefined) ? p.t_med : p.response_time;
      return { i: i, v: v, estado: p.estado, coletado_em: p.coletado_em };
    }).filter(function (p) { return p.v !== null && p.v !== undefined; });

    var svgNS = 'http://www.w3.org/2000/svg';
    var svg = document.createElementNS(svgNS, 'svg');
    svg.setAttribute('viewBox', '0 0 ' + W + ' ' + H);
    svg.setAttribute('preserveAspectRatio', 'none');
    svg.setAttribute('role', 'img');
    svg.setAttribute('aria-label', 'Gráfico de latência nas últimas 24 horas');
    svg.classList.add('sparkline__svg');

    if (!valores.length) {
      container.classList.add('sparkline--vazio');
      container.textContent = 'Sem latência registrada no período.';
      return;
    }

    var min = Math.min.apply(null, valores.map(function (p) { return p.v; }));
    var max = Math.max.apply(null, valores.map(function (p) { return p.v; }));
    var range = Math.max(1, max - min);
    var n = valores.length;
    var xStep = n > 1 ? (W - PAD * 2) / (n - 1) : 0;

    // Linha de fundo (trilha)
    var d = valores.map(function (p, i) {
      var x = PAD + i * xStep;
      var y = H - PAD - ((p.v - min) / range) * (H - PAD * 2);
      return (i === 0 ? 'M' : 'L') + x.toFixed(1) + ',' + y.toFixed(1);
    }).join(' ');

    var path = document.createElementNS(svgNS, 'path');
    path.setAttribute('d', d);
    path.setAttribute('class', 'sparkline__path');
    svg.appendChild(path);

    // Pontos coloridos por estado
    valores.forEach(function (p) {
      var x = PAD + p.i * xStep;
      var y = H - PAD - ((p.v - min) / range) * (H - PAD * 2);
      var circle = document.createElementNS(svgNS, 'circle');
      circle.setAttribute('cx', x.toFixed(1));
      circle.setAttribute('cy', y.toFixed(1));
      circle.setAttribute('r', '3');
      circle.setAttribute('class', 'sparkline__ponto');
      circle.setAttribute('fill', CORES_ESTADO[p.estado] || CORES_ESTADO.sem_dados);
      circle.setAttribute('tabindex', '0');
      var tooltip = document.createElementNS(svgNS, 'title');
      var texto = fmtDatetime(p.coletado_em) + ' · ' + p.v + ' ms · ' + (p.estado || 'sem dados');
      tooltip.textContent = texto;
      circle.appendChild(tooltip);
      svg.appendChild(circle);
    });

    container.appendChild(svg);
  }

  // ---------- Detalhe: re-fetch de histórico ----------
  function iniciarDetalhe() {
    var dados = window.__DETALHE_DATA__;
    if (!dados) return;

    var uf = dados.uf;
    var documento = dados.documento;
    var tpAmb = Number(dados.tp_amb);
    var ambienteRotulo = dados.ambiente_rotulo || '';

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
        badgeEstadoEl.textContent = ultimo.estado || 'Sem dados';
        badgeEstadoEl.style.background = ultimo.cor || CORES_ESTADO.sem_dados;
      }
      if (campoMotivo) campoMotivo.textContent = ultimo.x_motivo || '—';
      if (campoCstat) campoCstat.textContent = ultimo.cstat || '—';
      if (campoVerAplic) campoVerAplic.textContent = ultimo.ver_aplic || '—';
      if (campoLatencia) campoLatencia.textContent = fmtMs(ultimo.t_med);
      if (campoDhRecebto) campoDhRecebto.textContent = ultimo.dh_recebto || '—';
      if (campoColetadoEm) campoColetadoEm.textContent = fmtDatetime(ultimo.coletado_em);
      if (campoMsg) campoMsg.textContent = ultimo.msg || '—';
    }

    function aplicarHistorico(payload) {
      if (!payload) return;
      if (Array.isArray(payload.pontos)) desenharSparkline(sparklineEl, payload.pontos);
      if (typeof payload.uptime_pct === 'number') {
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
      return fetch(url)
        .then(function (r) {
          if (!r.ok) throw new Error('HTTP ' + r.status);
          return r.json();
        })
        .then(aplicarHistorico)
        .catch(function (err) {
          console.warn('[monitor] falha ao buscar histórico:', err);
        });
    }

    // Render inicial com dados injetados pelo Jinja
    desenharSparkline(sparklineEl, dados.pontos || []);
    aplicarUltimo(dados.ultimo || null);
    if (ambienteRotuloEl) ambienteRotuloEl.textContent = ambienteRotulo;

    // Toggle de ambiente
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
        // Atualiza o rótulo visível
        var ambData = (dados.ambientes || []).find(function (a) { return Number(a.tp_amb) === novoAmb; });
        if (ambData && ambienteRotuloEl) ambienteRotuloEl.textContent = ambData.rotulo;
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
