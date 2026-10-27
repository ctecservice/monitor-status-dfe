/* ============================================================================
   app.js — Monitor Status DFe (HTML-first)
   As páginas (index.html, detalhe.html, faq.html, termos.html) já contêm
   toda a estrutura HTML estática. Este script apenas:
     - detecta qual página está carregada (data-page no body),
     - liga eventos dos toggles/controles,
     - preenche dados vindos da API (celulas, histórico),
     - renderiza gráficos SVG,
     - mantém polling e persistência (localStorage).
   ============================================================================ */
(function () {
  'use strict';

  // ===== Configuração =======================================================
  var CFG = window.MONITOR_CONFIG || {};
  var API_BASE = (CFG.apiBaseUrl || '').replace(/\/+$/, '');
  var TURNSTILE_KEY = CFG.turnstileSiteKey || '';

  // ===== Constantes =========================================================
  var POLL_MS = 60 * 1000;
  var STORAGE = {
    tpAmb: 'monitor.tpAmb',
    documento: 'monitor.documento',
    janela: 'monitor.janela',
    viz: 'monitor.viz'
  };
  var COR_ESTADO = {
    operacional: '#22C55E',
    instavel: '#F59E0B',
    indisponivel: '#EF4444',
    sem_dados: '#8A8585'
  };
  var JANELAS = {
    '1h':  { horas: 1, rotulo: '1 h' },
    '6h':  { horas: 6, rotulo: '6 h' },
    '24h': { horas: 24, rotulo: '24 h' },
    '72h': { horas: 72, rotulo: '72 h' },
    '7d':  { horas: 168, rotulo: '7 dias' },
    '30d': { horas: 720, rotulo: '30 dias' }
  };

  // Paleta de 27 cores para UFs no gráfico de linha (ângulo áureo HSL)
  var PALETA_UF = (function () {
    var cores = [];
    for (var i = 0; i < 27; i++) {
      var hue = (i * 137.508) % 360;
      cores.push('hsl(' + hue.toFixed(0) + ', 65%, 45%)');
    }
    return cores;
  })();
  var ufParaCor = {};
  function corParaUf(uf, idx) {
    if (!ufParaCor[uf]) ufParaCor[uf] = PALETA_UF[idx % PALETA_UF.length];
    return ufParaCor[uf];
  }

  // ===== Utilidades =========================================================
  function api(path) { return API_BASE + path; }

  function fmtMs(v) {
    if (v === null || v === undefined || v === '') return '—';
    var n = Number(v);
    return isNaN(n) ? '—' : n + ' ms';
  }

  function latenciaDe(d) {
    if (!d) return null;
    var v = d.response_time;
    if (v === null || v === undefined || v === '') v = d.t_med;
    return (v === null || v === undefined || v === '') ? null : v;
  }

  function corSla(ms) {
    if (ms === null || ms === undefined) return null;
    if (ms <= 2000) return 'var(--sla-green)';
    if (ms <= 5000) return 'var(--sla-amber)';
    return 'var(--sla-red)';
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
      return d.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit', timeZone: 'America/Sao_Paulo' });
    } catch (e) { return ''; }
  }

  function fmtHaXMin(iso) {
    if (!iso) return '';
    var d = new Date(iso);
    if (isNaN(d.getTime())) return '';
    var agora = new Date();
    var diff = Math.floor((agora - d) / 60000);
    if (diff < 1) return '(agora)';
    if (diff < 60) return '(há ' + diff + ' min)';
    var h = Math.floor(diff / 60);
    if (h < 24) return '(há ' + h + ' h)';
    var dias = Math.floor(h / 24);
    return '(há ' + dias + ' d)';
  }

  function localStorageGet(key, fallback) {
    try { var v = localStorage.getItem(key); return v === null ? fallback : v; }
    catch (e) { return fallback; }
  }
  function localStorageSet(key, val) {
    try { localStorage.setItem(key, val); } catch (e) { /* ignore */ }
  }

  function el(tag, attrs, children) {
    var e = document.createElement(tag);
    if (attrs) {
      Object.keys(attrs).forEach(function (k) {
        if (k === 'class') e.className = attrs[k];
        else if (k === 'style' && typeof attrs[k] === 'object') {
          Object.keys(attrs[k]).forEach(function (s) { e.style.setProperty(s, attrs[k][s]); });
        }
        else e.setAttribute(k, attrs[k]);
      });
    }
    if (children) {
      (Array.isArray(children) ? children : [children]).forEach(function (c) {
        if (typeof c === 'string') e.appendChild(document.createTextNode(c));
        else if (c) e.appendChild(c);
      });
    }
    return e;
  }
  function clear(parent) { while (parent && parent.firstChild) parent.removeChild(parent.firstChild); }

  function isEmbed() { return /[?&]embed=1/.test(location.search); }

  // ===== Notificação de altura para embed ===================================
  function notificarAltura() {
    if (!state.embed || window.parent === window) return;
    var altura = document.body.scrollHeight;
    window.parent.postMessage({
      type: 'monitor-status-dfe:resize',
      height: altura
    }, '*');
  }

  // Observer para detectar mudanças de altura
  var resizeObserver = null;
  function iniciarResizeObserver() {
    if (!state.embed || !window.ResizeObserver) return;
    resizeObserver = new ResizeObserver(function() {
      notificarAltura();
    });
    resizeObserver.observe(document.body);
  }
  function getQueryParam(name, fallback) {
    var m = new RegExp('[?&]' + name + '=([^&]*)').exec(location.search);
    if (!m) return fallback;
    try { return decodeURIComponent(m[1]); } catch (e) { return fallback; }
  }

  // ===== Turnstile (anti-bot) ===============================================
  var _ts = { widgetId: null, token: null, resetPromise: null };

  function iniciarTurnstile() {
    if (!TURNSTILE_KEY) return;
    function montarWidget() {
      if (!window.turnstile) return;
      var div = document.createElement('div');
      div.style.display = 'none';
      document.body.appendChild(div);
      window.turnstile.ready(function () {
        _ts.widgetId = window.turnstile.render(div, {
          sitekey: TURNSTILE_KEY,
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
              var p = _ts.resetPromise; _ts.resetPromise = null;
              clearTimeout(p.timer); p.reject(new Error('erro Turnstile'));
            }
          },
          'expired-callback': function () {
            if (_ts.resetPromise) {
              var p = _ts.resetPromise; _ts.resetPromise = null;
              clearTimeout(p.timer); p.reject(new Error('token expirou'));
            }
          },
          'refresh-expired': 'auto',
          appearance: 'interaction-only',
          language: 'pt-BR'
        });
      });
    }
    if (window.turnstile) { montarWidget(); return; }
    var script = document.createElement('script');
    script.src = 'https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit';
    script.async = true;
    script.onload = montarWidget;
    document.head.appendChild(script);
  }

  function resetarTurnstile() {
    if (_ts.resetPromise) return _ts.resetPromise;
    if (!window.turnstile || _ts.widgetId === null) return Promise.resolve();
    var d = {};
    d.promise = new Promise(function (resolve, reject) {
      d.resolve = resolve; d.reject = reject;
    });
    d.then = function (a, b) { return d.promise.then(a, b); };
    d.timer = setTimeout(function () {
      if (_ts.resetPromise === d) _ts.resetPromise = null;
      d.reject(new Error('timeout Turnstile'));
    }, 15000);
    _ts.resetPromise = d;
    try { window.turnstile.reset(_ts.widgetId); }
    catch (e) {
      if (_ts.resetPromise === d) { _ts.resetPromise = null; clearTimeout(d.timer); }
      d.reject(e);
    }
    return d;
  }

  function fetchProtegido(url) {
    var headers = {};
    if (_ts.token) headers['CF-Turnstile-Token'] = _ts.token;
    return fetch(url, { headers: headers }).then(function (r) {
      if (r.status === 403 && TURNSTILE_KEY && _ts.widgetId !== null) {
        _ts.token = null;
        return resetarTurnstile().then(function () {
          var h2 = {};
          if (_ts.token) h2['CF-Turnstile-Token'] = _ts.token;
          return fetch(url, { headers: h2 });
        });
      }
      return r;
    });
  }

  // ===== Estado global ======================================================
  // Migração: valor antigo "disponibilidade" no localStorage vira "cards"
  var vizInicial = localStorageGet(STORAGE.viz, 'linha');
  if (vizInicial === 'disponibilidade') vizInicial = 'cards';
  // Default de documento: NFC-e (para visitantes novos/limpos)
  var documentoInicial = localStorageGet(STORAGE.documento, 'nfce');

  var state = {
    modelos: [],
    ambientes: [
      { tp_amb: 1, rotulo: 'Produção' },
      { tp_amb: 2, rotulo: 'Homologação' }
    ],
    celulas: [],
    geradoEm: null,
    tpAmb: Number(localStorageGet(STORAGE.tpAmb, '1')) || 1,
    documento: documentoInicial,
    janela: localStorageGet(STORAGE.janela, '1h'),
    viz: vizInicial,
    embed: false,
    historicoPainel: null,
    _pontosDetalhe: null
  };

  var pollTimer = null;
  var recalcTimer = null;

  // ===== Toggles helpers ====================================================
  function bindAmbToggle(containerId, onSelect) {
    var container = document.getElementById(containerId);
    if (!container) return;
    var botoes = Array.prototype.slice.call(container.querySelectorAll('button[data-tp-amb]'));
    botoes.forEach(function (btn) {
      btn.addEventListener('click', function () {
        var tpAmb = Number(btn.getAttribute('data-tp-amb'));
        botoes.forEach(function (b) {
          var ativo = Number(b.getAttribute('data-tp-amb')) === tpAmb;
          b.classList.toggle('ambiente-toggle__btn--ativo', ativo);
          b.setAttribute('aria-selected', ativo ? 'true' : 'false');
        });
        state.tpAmb = tpAmb;
        localStorageSet(STORAGE.tpAmb, String(tpAmb));
        if (typeof onSelect === 'function') onSelect(tpAmb);
      });
    });
  }

  function marcarAmbAtivo(containerId, tpAmb) {
    var container = document.getElementById(containerId);
    if (!container) return;
    var botoes = Array.prototype.slice.call(container.querySelectorAll('button[data-tp-amb]'));
    botoes.forEach(function (b) {
      var ativo = Number(b.getAttribute('data-tp-amb')) === tpAmb;
      b.classList.toggle('ambiente-toggle__btn--ativo', ativo);
      b.setAttribute('aria-selected', ativo ? 'true' : 'false');
    });
  }

  function bindVizToggle(onChange) {
    var container = document.getElementById('viz-toggle');
    if (!container) return;
    var botoes = Array.prototype.slice.call(container.querySelectorAll('button[data-viz]'));
    botoes.forEach(function (btn) {
      btn.addEventListener('click', function () {
        var viz = btn.getAttribute('data-viz');
        botoes.forEach(function (b) {
          var ativo = b.getAttribute('data-viz') === viz;
          b.classList.toggle('viz-toggle__btn--ativo', ativo);
          b.setAttribute('aria-selected', ativo ? 'true' : 'false');
        });
        state.viz = viz;
        localStorageSet(STORAGE.viz, viz);
        if (typeof onChange === 'function') onChange(viz);
      });
    });
  }

  function marcarVizAtivo(viz) {
    var container = document.getElementById('viz-toggle');
    if (!container) return;
    var botoes = Array.prototype.slice.call(container.querySelectorAll('button[data-viz]'));
    botoes.forEach(function (b) {
      var ativo = b.getAttribute('data-viz') === viz;
      b.classList.toggle('viz-toggle__btn--ativo', ativo);
      b.setAttribute('aria-selected', ativo ? 'true' : 'false');
    });
  }

  function bindJanelaSel(containerId, onSelect) {
    var container = document.getElementById(containerId);
    if (!container) return;
    var botoes = Array.prototype.slice.call(container.querySelectorAll('button[data-janela]'));
    botoes.forEach(function (btn) {
      btn.addEventListener('click', function () {
        var janela = btn.getAttribute('data-janela');
        botoes.forEach(function (b) {
          var ativo = b.getAttribute('data-janela') === janela;
          b.classList.toggle('seletor-janela__btn--ativo', ativo);
          b.setAttribute('aria-selected', ativo ? 'true' : 'false');
        });
        state.janela = janela;
        localStorageSet(STORAGE.janela, janela);
        if (typeof onSelect === 'function') onSelect(janela);
      });
    });
  }

  function marcarJanelaAtiva(containerId, janela) {
    var container = document.getElementById(containerId);
    if (!container) return;
    var botoes = Array.prototype.slice.call(container.querySelectorAll('button[data-janela]'));
    botoes.forEach(function (b) {
      var ativo = b.getAttribute('data-janela') === janela;
      b.classList.toggle('seletor-janela__btn--ativo', ativo);
      b.setAttribute('aria-selected', ativo ? 'true' : 'false');
    });
  }

  // ===== Modelo toggle (preenchido dinamicamente) ===========================
  function preencherModeloToggle(containerId, modelos, documentoAtivo, onSelect) {
    var container = document.getElementById(containerId);
    if (!container) return;
    clear(container);
    if (!modelos || !modelos.length) {
      container.appendChild(el('span', { class: 'filtro-modelo__placeholder' }, 'Carregando modelos...'));
      return;
    }
    modelos.forEach(function (m) {
      var ativo = m.codigo === documentoAtivo;
      var btn = el('button', {
        class: 'filtro-modelo__btn' + (ativo ? ' filtro-modelo__btn--ativo' : ''),
        type: 'button',
        role: 'tab',
        'aria-selected': ativo ? 'true' : 'false',
        'data-documento': m.codigo
      }, m.nome);
      btn.addEventListener('click', function () {
        var btns = Array.prototype.slice.call(container.querySelectorAll('button[data-documento]'));
        btns.forEach(function (b) {
          var a = b.getAttribute('data-documento') === m.codigo;
          b.classList.toggle('filtro-modelo__btn--ativo', a);
          b.setAttribute('aria-selected', a ? 'true' : 'false');
        });
        state.documento = m.codigo;
        localStorageSet(STORAGE.documento, m.codigo);
        if (typeof onSelect === 'function') onSelect(m.codigo);
      });
      container.appendChild(btn);
    });
  }

  // ===== Visibilidade das seções do painel ==================================
  function atualizaVisibilidadePainel() {
    var grade = document.getElementById('grade');
    var cardsView = document.getElementById('cards-view');
    var linhaCard = document.getElementById('linha-card');
    if (grade) grade.style.display = state.viz === 'grade' ? '' : 'none';
    if (cardsView) cardsView.style.display = state.viz === 'cards' ? '' : 'none';
    if (linhaCard) linhaCard.style.display = state.viz === 'linha' ? '' : 'none';
  }

  // ===== Atualização unificada do painel ====================================
  // Redesenha a visualização ativa a partir do cache OU dispara fetch se não houver dados.
  function atualizarPainel() {
    atualizaVisibilidadePainel();
    if (state.viz === 'grade') {
      renderGrade();
    } else if (state.viz === 'cards') {
      renderCards();
    } else if (state.viz === 'linha') {
      if (state.historicoPainel) {
        var j = JANELAS[state.janela] || JANELAS['24h'];
        renderLinha('linha-painel', state.historicoPainel.series || {}, state.historicoPainel.ufs || [], j.horas);
      } else {
        buscarHistoricoPainel();
      }
    }
    // Notifica altura após renderização
    setTimeout(notificarAltura, 100);
  }

  // ===== Render da grade (preenche tbody existente) =========================
  // Link para a página de detalhe; no modo embed o parâmetro é propagado para
  // o Flask manter a liberação de frame (frame-ancestors) na navegação interna.
  function detalheHref(uf) {
    return 'detalhe.html?uf=' + uf + '&doc=' + state.documento + '&amb=' + state.tpAmb +
      (state.embed ? '&embed=1' : '');
  }

  function renderGrade() {
    var tbody = document.getElementById('grade-tbody');
    var thModelo = document.getElementById('grade-modelo-th');
    if (!tbody) return;
    clear(tbody);

    var modeloAtivo = state.modelos.find(function (m) { return m.codigo === state.documento; });
    if (thModelo) thModelo.textContent = modeloAtivo ? modeloAtivo.nome : 'Modelo';

    if (!state.celulas.length) {
      var tr = el('tr');
      var msg = state.geradoEm
        ? 'Sem coletas ainda — aguarde o primeiro ciclo de coleta.'
        : 'Carregando...';
      tr.appendChild(el('td', { colspan: '2', style: { textAlign: 'center', padding: 'var(--space-6)', color: 'var(--muted)' } }, msg));
      tbody.appendChild(tr);
      return;
    }

    var celulasFiltradas = state.celulas.filter(function (c) {
      return c.tp_amb === state.tpAmb && c.documento === state.documento;
    });
    var mapa = {};
    celulasFiltradas.forEach(function (c) { if (!mapa[c.uf]) mapa[c.uf] = c; });
    var ufs = Object.keys(mapa).sort();

    ufs.forEach(function (uf) {
      var c = mapa[uf];
      var tr = el('tr');
      var th = el('th', { class: 'grade__th--sticky', scope: 'row' });
      th.appendChild(el('a', {
        class: 'grade__uf-link',
        href: detalheHref(uf)
      }, uf));
      tr.appendChild(th);

      var td = el('td', { class: 'grade__td' });
      var cor = c.cor || COR_ESTADO.sem_dados;
      var lat = latenciaDe(c);
      var latCor = corSla(lat);

      var celula = el('a', {
        class: 'celula celula--preenchida',
        href: detalheHref(uf),
        title: (c.rotulo || 'Sem dados') + (lat !== null ? ' · ' + lat + ' ms' : '') + ' · ' + fmtHaXMin(c.coletado_em),
        style: { '--celula-cor': cor }
      });
      celula.appendChild(el('span', { class: 'celula__estado' }, c.rotulo || 'Sem dados'));
      var latSpan = el('span', { class: 'celula__latencia' }, fmtMs(lat));
      if (latCor) latSpan.style.color = latCor;
      celula.appendChild(latSpan);
      if (c.cstat) celula.appendChild(el('span', { class: 'celula__cstat' }, 'cStat ' + c.cstat));
      td.appendChild(celula);
      tr.appendChild(td);
      tbody.appendChild(tr);
    });

    // Banner de alerta
    var alerta = document.getElementById('alerta-painel');
    if (alerta && ufs.length) {
      var semDados = ufs.filter(function (uf) {
        var c = mapa[uf];
        return !c || c.estado === 'sem_dados' || c.erro;
      }).length;
      if (semDados / ufs.length > 0.8) {
        alerta.hidden = false;
        alerta.textContent = 'A maioria das células está sem dados — a fonte pode estar indisponível no momento.';
      } else {
        alerta.hidden = true;
      }
    }
  }

  // ===== Modo Cards (preenche grid existente) ===============================
  function renderCards() {
    var grid = document.getElementById('cards-grid');
    if (!grid) return;
    clear(grid);

    if (!state.celulas.length) {
      grid.appendChild(el('div', { class: 'loading' }, [
        el('span', { class: 'loading__spinner' }),
        document.createTextNode('Carregando...')
      ]));
      return;
    }

    var celulasFiltradas = state.celulas.filter(function (c) {
      return c.tp_amb === state.tpAmb && c.documento === state.documento;
    });
    if (!celulasFiltradas.length) {
      grid.appendChild(el('div', { class: 'cards-view__empty' }, 'Sem dados para a seleção atual.'));
      return;
    }
    var mapa = {};
    celulasFiltradas.forEach(function (c) { if (!mapa[c.uf]) mapa[c.uf] = c; });
    var ufs = Object.keys(mapa).sort();

    ufs.forEach(function (uf) {
      var c = mapa[uf];
      var cor = c.cor || COR_ESTADO.sem_dados;
      var lat = latenciaDe(c);
      var latCor = corSla(lat);

      var card = el('a', {
        class: 'card card--uf',
        href: detalheHref(uf),
        'aria-label': uf + ' — ' + (c.rotulo || 'Sem dados')
      });
      var header = el('div', { class: 'card--uf__header' });
      header.appendChild(el('span', { class: 'card--uf__uf' }, uf));
      header.appendChild(el('span', { class: 'badge', style: { background: cor } }, c.rotulo || 'Sem dados'));
      card.appendChild(header);

      var body = el('div', { class: 'card--uf__body' });
      var latRow = el('div', { class: 'card--uf__row' });
      latRow.appendChild(el('span', { class: 'card--uf__label' }, 'Latência'));
      var latVal = el('span', { class: 'card--uf__value' }, fmtMs(lat));
      if (latCor) latVal.style.color = latCor;
      latRow.appendChild(latVal);
      body.appendChild(latRow);

      // Sempre renderizar linha de cStat para manter estrutura uniforme
      var cstatRow = el('div', { class: 'card--uf__row' });
      cstatRow.appendChild(el('span', { class: 'card--uf__label' }, 'cStat'));
      var cstatVal = el('span', { class: 'card--uf__value card--uf__value--mono' }, c.cstat || '—');
      cstatRow.appendChild(cstatVal);
      body.appendChild(cstatRow);

      var haRow = el('div', { class: 'card--uf__row' });
      haRow.appendChild(el('span', { class: 'card--uf__label' }, 'Coletado'));
      haRow.appendChild(el('span', { class: 'card--uf__value' }, fmtHaXMin(c.coletado_em) || '—'));
      body.appendChild(haRow);

      card.appendChild(body);
      grid.appendChild(card);
    });
  }

  // ===== Timestamp (Atualizado às ...) ======================================
  function atualizaTimestamp() {
    var timeEl = document.getElementById('gerado-em');
    var haXMinEl = document.getElementById('ha-x-min');
    if (timeEl && state.geradoEm) {
      timeEl.textContent = fmtDatetime(state.geradoEm);
      timeEl.setAttribute('datetime', state.geradoEm);
      if (haXMinEl) haXMinEl.textContent = fmtHaXMin(state.geradoEm);
    }
  }

  // ===== Gráfico de linha ===================================================
  // Reduz a série a no máximo `maximo` pontos por UF (agregação por bucket com
  // média de latência), evitando dezenas de milhares de nós SVG em janelas
  // grandes (7d/30d) — que travariam o navegador.
  function reduzirPontos(pontos, maximo) {
    if (!pontos || pontos.length <= maximo) return pontos || [];
    var tamanhoBucket = Math.ceil(pontos.length / maximo);
    var resultado = [];
    for (var i = 0; i < pontos.length; i += tamanhoBucket) {
      var fatia = pontos.slice(i, i + tamanhoBucket);
      var lats = fatia.map(latenciaDe).filter(function (v) { return v !== null; });
      var representante = Object.assign({}, fatia[0]);
      representante.response_time = lats.length
        ? Math.round(lats.reduce(function (a, b) { return a + b; }, 0) / lats.length)
        : null;
      // O pior estado do bucket define a cor do ponto agregado.
      var pior = null;
      fatia.forEach(function (p) {
        if (p.estado === 'indisponivel') pior = 'indisponivel';
        else if (p.estado === 'instavel' && pior !== 'indisponivel') pior = 'instavel';
      });
      if (pior) representante.estado = pior;
      resultado.push(representante);
    }
    return resultado;
  }

  // Escapa texto para inserção segura no SVG montado como string.
  function esc(s) {
    return String(s === null || s === undefined ? '' : s)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  function renderLinha(containerId, series, ufs, horas, opts) {
    opts = opts || {};
    var container = document.getElementById(containerId);
    if (!container) return;
    clear(container);

    if (!series || !ufs.length) {
      container.appendChild(el('div', { class: 'loading' }, 'Sem dados no período.'));
      return;
    }

    var minX = Infinity, maxX = -Infinity, maxY = 0, temDados = false;
    var pontosPorUf = {};
    ufs.forEach(function (uf) {
      var pontos = (series[uf] || []).slice().sort(function (a, b) {
        return new Date(a.coletado_em) - new Date(b.coletado_em);
      });
      pontos = reduzirPontos(pontos, 300);
      pontosPorUf[uf] = pontos;
      pontos.forEach(function (p) {
        var t = new Date(p.coletado_em).getTime();
        var lat = latenciaDe(p);
        if (t < minX) minX = t;
        if (t > maxX) maxX = t;
        if (lat !== null && lat > maxY) maxY = lat;
        if (lat !== null) temDados = true;
      });
    });

    if (!temDados) {
      container.appendChild(el('div', { class: 'loading' }, 'Sem dados no período.'));
      return;
    }
    if (minX === maxX) maxX = minX + 60000;

    var maxYRound = Math.ceil(maxY / 1000) * 1000;
    if (maxYRound === 0) maxYRound = 1000;

    var W = 800, H = 400;
    var pad = { top: 20, right: 20, bottom: 50, left: 60 };
    var plotW = W - pad.left - pad.right;
    var plotH = H - pad.top - pad.bottom;

    function scaleX(t) { return pad.left + (t - minX) / (maxX - minX) * plotW; }
    function scaleY(v) { return pad.top + plotH - (v / maxYRound * plotH); }

    // SVG montado como string única (innerHTML): criar nó a nó com
    // createElementNS custa tempo por elemento e, com ~300 pontos por UF em
    // até 27 UFs (~8 mil nós), a renderização travava o navegador.
    var html = '<svg viewBox="0 0 ' + W + ' ' + H + '" preserveAspectRatio="xMidYMid meet" ' +
      'role="img" aria-label="Gráfico de latência por UF ao longo do tempo" class="linha-svg">';

    var numLinhasGrade = 5;
    for (var i = 0; i <= numLinhasGrade; i++) {
      var y = pad.top + (plotH / numLinhasGrade) * i;
      var val = maxYRound - (maxYRound / numLinhasGrade) * i;
      html += '<line x1="' + pad.left + '" x2="' + (W - pad.right) + '" y1="' + y + '" y2="' + y +
        '" stroke="#E2E8F0" stroke-width="1"></line>';
      html += '<text x="' + (pad.left - 10) + '" y="' + (y + 4) + '" text-anchor="end" class="linha-eixo-y-texto">' +
        val + ' ms</text>';
    }

    var numLabelsX = 6;
    for (var j = 0; j <= numLabelsX; j++) {
      var t = minX + (maxX - minX) * (j / numLabelsX);
      var x = scaleX(t);
      var date = new Date(t);
      var label = horas <= 24 ? fmtHora(date.toISOString()) : (date.getDate() + '/' + (date.getMonth() + 1));
      html += '<text x="' + x + '" y="' + (H - pad.bottom + 20) + '" text-anchor="middle" class="linha-eixo-x-texto">' +
        esc(label) + '</text>';
    }

    html += '<g class="linhas-group">';

    var ufIdx = 0;
    var corLinhaDetalhe = opts.corLinha || null;
    ufs.forEach(function (uf) {
      var pontos = pontosPorUf[uf];
      if (!pontos.length) return;
      var corLinha = corLinhaDetalhe || corParaUf(uf, ufIdx++);
      var pathD = '';
      var lastValid = null;
      pontos.forEach(function (p) {
        var tP = new Date(p.coletado_em).getTime();
        var lat = latenciaDe(p);
        if (lat === null || p.estado === 'sem_dados') { lastValid = null; return; }
        var xP = scaleX(tP), yP = scaleY(lat);
        if (lastValid === null) pathD += 'M' + xP.toFixed(1) + ',' + yP.toFixed(1) + ' ';
        else pathD += 'L' + xP.toFixed(1) + ',' + yP.toFixed(1) + ' ';
        lastValid = { x: xP, y: yP };
      });
      if (pathD) {
        html += '<path d="' + esc(pathD.trim()) + '" stroke="' + esc(corLinha) +
          '" stroke-width="1.5" fill="none" class="linha-uf" data-uf="' + esc(uf) + '"></path>';
      }
      pontos.forEach(function (p) {
        var tP = new Date(p.coletado_em).getTime();
        var lat = latenciaDe(p);
        if (lat === null || p.estado === 'sem_dados') return;
        var xP = scaleX(tP), yP = scaleY(lat);
        // No detalhe (corLinhaDetalhe), colore pontos pelo estado; no painel, pela UF
        var corPonto = corLinhaDetalhe ? (COR_ESTADO[p.estado] || COR_ESTADO.sem_dados) : corLinha;
        html += '<circle cx="' + xP.toFixed(1) + '" cy="' + yP.toFixed(1) + '" r="3" fill="' + esc(corPonto) +
          '" class="linha-ponto" data-uf="' + esc(uf) + '"><title>' +
          esc(uf + ' · ' + fmtDatetime(p.coletado_em) + ' · ' + lat + ' ms') + '</title></circle>';
      });
    });
    html += '</g></svg>';

    container.innerHTML = html;
    var svg = container.querySelector('svg');

    // Legenda de UFs (oculta quando há apenas 1 UF no detalhe)
    var showLegenda = ufs.length > 1 && !opts.noLegenda;
    if (showLegenda) {
      var legendaContainer = el('div', { class: 'linha-legenda', 'aria-label': 'Legenda de UFs' });
      var ufIdx2 = 0;
      ufs.forEach(function (uf) {
        var cor = corParaUf(uf, ufIdx2++);
        var item = el('div', {
          class: 'linha-legenda__item',
          'data-uf': uf,
          tabindex: '0',
          role: 'button',
          'aria-label': 'Destacar ' + uf
        });
        item.appendChild(el('span', { class: 'linha-legenda__swatch', style: { background: cor } }));
        item.appendChild(el('span', { class: 'linha-legenda__label' }, uf));
        legendaContainer.appendChild(item);
      });
      container.appendChild(legendaContainer);

      // Interação de destaque
      var ufFixado = null;
      function destacar(uf) {
        Array.prototype.slice.call(svg.querySelectorAll('.linha-uf, .linha-ponto')).forEach(function (e) {
          if (e.getAttribute('data-uf') === uf) {
            e.style.opacity = '1'; e.style.strokeWidth = '2.5';
          } else {
            e.style.opacity = '0.15';
          }
        });
      }
      function restaurar() {
        Array.prototype.slice.call(svg.querySelectorAll('.linha-uf, .linha-ponto')).forEach(function (e) {
          e.style.opacity = ''; e.style.strokeWidth = '';
        });
        // Remove classe ativo de todos os itens da legenda
        Array.prototype.slice.call(legendaContainer.children).forEach(function (item) {
          item.classList.remove('linha-legenda__item--ativo');
        });
      }
      function fixar(uf) {
        if (ufFixado === uf) {
          ufFixado = null;
          restaurar();
        } else {
          ufFixado = uf;
          destacar(uf);
          // Marca visualmente o item fixado
          Array.prototype.slice.call(legendaContainer.children).forEach(function (item) {
            var ativo = item.getAttribute('data-uf') === uf;
            item.classList.toggle('linha-legenda__item--ativo', ativo);
          });
        }
      }
      Array.prototype.slice.call(legendaContainer.children).forEach(function (item) {
        var uf = item.getAttribute('data-uf');
        // Hover só age quando nada está fixado
        item.addEventListener('mouseenter', function () { if (!ufFixado) destacar(uf); });
        item.addEventListener('mouseleave', function () { if (!ufFixado) restaurar(); });
        item.addEventListener('click', function () { fixar(uf); });
        item.addEventListener('keydown', function (e) {
          if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); fixar(uf); }
        });
      });
    }
  }

  // ===== Incidentes =========================================================
  function calcularIncidentes(pontos) {
    if (!pontos || !pontos.length) return [];
    var sorted = pontos.slice().sort(function (a, b) {
      return new Date(a.coletado_em) - new Date(b.coletado_em);
    });
    var incidents = [], current = null;
    sorted.forEach(function (p) {
      if (p.estado === 'indisponivel') {
        if (!current) current = { inicio: p.coletado_em, fim: p.coletado_em };
        else current.fim = p.coletado_em;
      } else {
        if (current) { incidents.push(current); current = null; }
      }
    });
    if (current) incidents.push(current);

    incidents.forEach(function (inc) {
      var diffMin = Math.floor((new Date(inc.fim) - new Date(inc.inicio)) / 60000);
      if (diffMin < 60) inc.duracao = diffMin + ' min';
      else {
        var h = Math.floor(diffMin / 60), m = diffMin % 60;
        inc.duracao = h + ' h ' + m + ' min';
      }
    });
    return incidents;
  }

  function renderIncidentes(container, pontos) {
    if (!container) return;
    clear(container);
    var incidents = calcularIncidentes(pontos);
    if (!incidents.length) {
      container.appendChild(el('p', { class: 'incidents__empty' }, 'Nenhum incidente no período.'));
      return;
    }
    var list = el('ul', { class: 'incidents__list' });
    incidents.slice().reverse().forEach(function (inc) {
      var item = el('li', { class: 'incidents__item' });
      var header = el('div', { class: 'incidents__item-header' });
      header.appendChild(el('span', { class: 'incidents__item-timestamp' }, fmtDatetime(inc.inicio)));
      header.appendChild(el('span', { class: 'incidents__item-duration' }, 'Duração: ' + inc.duracao));
      item.appendChild(header);
      var details = el('div', { class: 'incidents__item-details' });
      details.textContent = 'De ' + fmtDatetime(inc.inicio) + ' até ' + fmtDatetime(inc.fim);
      item.appendChild(details);
      list.appendChild(item);
    });
    container.appendChild(list);
  }

  // ===== Coletas recentes (tabela) ==========================================
  function renderRecentTable(container, pontos) {
    if (!container) return;
    clear(container);
    if (!pontos || !pontos.length) {
      container.appendChild(el('div', { class: 'recent__empty' }, 'Sem coletas no período.'));
      return;
    }
    var sorted = pontos.slice().sort(function (a, b) {
      return new Date(b.coletado_em) - new Date(a.coletado_em);
    }).slice(0, 20);

    var table = el('table', { class: 'recent__table' });
    var thead = el('thead');
    var headRow = el('tr');
    ['Data/Hora', 'Estado', 'cStat', 'Latência'].forEach(function (h) {
      headRow.appendChild(el('th', {}, h));
    });
    thead.appendChild(headRow);
    table.appendChild(thead);

    var tbody = el('tbody');
    sorted.forEach(function (p) {
      var tr = el('tr');
      tr.appendChild(el('td', {}, fmtDatetime(p.coletado_em)));
      tr.appendChild(el('td', {}, [el('span', { class: 'badge', style: { background: p.cor || COR_ESTADO.sem_dados, fontSize: '0.75rem' } }, p.rotulo || 'Sem dados')]));
      tr.appendChild(el('td', {}, p.cstat || '—'));
      var lat = latenciaDe(p);
      var latCor = corSla(lat);
      var latTd = el('td', { class: 'recent__latencia' }, fmtMs(lat));
      if (latCor) latTd.style.color = latCor;
      tr.appendChild(latTd);
      tbody.appendChild(tr);
    });
    table.appendChild(tbody);
    container.appendChild(table);
  }

  // ===== Export CSV / JSON ==================================================
  function exportarCSV(pontos, uf, doc, amb) {
    var headers = ['Data/Hora', 'Estado', 'cStat', 'Latência (ms)'];
    var rows = pontos.map(function (p) {
      return [fmtDatetime(p.coletado_em), p.estado || 'sem_dados', p.cstat || '', latenciaDe(p) || ''];
    });
    // Separador ";" e BOM UTF-8: compatível com o Excel em pt-BR.
    var csv = '\uFEFF' + [headers].concat(rows).map(function (row) {
      return row.map(function (cell) { return '"' + String(cell).replace(/"/g, '""') + '"'; }).join(';');
    }).join('\n');
    var blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
    var url = URL.createObjectURL(blob);
    var a = el('a', { href: url, download: 'status-' + uf + '-' + doc + '-' + amb + '.csv' });
    document.body.appendChild(a); a.click(); document.body.removeChild(a);
    URL.revokeObjectURL(url);
  }
  function exportarJSON(pontos, uf, doc, amb) {
    var json = JSON.stringify(pontos, null, 2);
    var blob = new Blob([json], { type: 'application/json;charset=utf-8;' });
    var url = URL.createObjectURL(blob);
    var a = el('a', { href: url, download: 'status-' + uf + '-' + doc + '-' + amb + '.json' });
    document.body.appendChild(a); a.click(); document.body.removeChild(a);
    URL.revokeObjectURL(url);
  }

  // ===== Inicialização do INDEX =============================================
  function initIndex() {
    if (isEmbed()) document.body.classList.add('embed-mode');
    state.embed = isEmbed();
    iniciarTurnstile();

    // Marca toggles iniciais (antes de qualquer fetch)
    marcarAmbAtivo('amb-toggle', state.tpAmb);
    marcarVizAtivo(state.viz);
    atualizaVisibilidadePainel();

    // Liga eventos dos toggles estáticos
    bindAmbToggle('amb-toggle', function () {
      preencherModeloToggle('modelo-toggle', state.modelos, state.documento, function () {
        atualizarPainel();
        buscarHistoricoPainel();
      });
      atualizarPainel();
      buscarHistoricoPainel();
    });

    bindVizToggle(function () { atualizarPainel(); });

    bindJanelaSel('janela-linha-sel', function () {
      // Sempre refaz o fetch: o cache pode ser de outra janela de tempo.
      buscarHistoricoPainel();
    });
    marcarJanelaAtiva('janela-linha-sel', state.janela);

    // Botão Atualizar
    var btnAtualizar = document.getElementById('btn-atualizar');
    if (btnAtualizar) {
      btnAtualizar.addEventListener('click', function () {
        btnAtualizar.disabled = true;
        btnAtualizar.classList.add('btn-atualizar--loading');
        // buscarStatus já puxa o histórico quando a visualização é linha;
        // chamar os dois aqui duplicaria a requisição de /api/historico.
        buscarStatus().finally(function () {
          btnAtualizar.disabled = false;
          btnAtualizar.classList.remove('btn-atualizar--loading');
        });
      });
    }

    // Polling
    buscarStatus();
    pollTimer = setInterval(buscarStatus, POLL_MS);
    recalcTimer = setInterval(atualizaTimestamp, 60000);

    // Iniciar observer de resize para embed
    iniciarResizeObserver();
    // Notificar altura inicial
    setTimeout(notificarAltura, 300);
  }

  function buscarStatus() {
    return fetchProtegido(api('/api/status'))
      .then(function (r) {
        if (r.status === 429) {
          var alerta = document.getElementById('alerta-painel');
          if (alerta) { alerta.hidden = false; alerta.textContent = 'Muitas requisições. Aguarde alguns segundos.'; }
          throw new Error('429');
        }
        if (!r.ok) throw new Error('HTTP ' + r.status);
        return r.json();
      })
      .then(function (data) {
        state.modelos = data.modelos || [];
        state.ambientes = data.ambientes || state.ambientes;
        state.celulas = data.celulas || [];
        state.geradoEm = data.gerado_em;

        // Se o documento salvo não está nos modelos, usa o primeiro
        if (state.modelos.length && !state.modelos.find(function (m) { return m.codigo === state.documento; })) {
          state.documento = state.modelos[0].codigo;
        }

        preencherModeloToggle('modelo-toggle', state.modelos, state.documento, function () {
          atualizarPainel();
          buscarHistoricoPainel();
        });
        renderGrade();
        renderCards();
        atualizaTimestamp();
        // O histórico agregado só é necessário na visualização de linha:
        // evita ~1,5 MB/min (janela de 24 h) de tráfego desnecessário.
        if (state.viz === 'linha') buscarHistoricoPainel();
      })
      .catch(function (err) {
        console.warn('[monitor] falha /api/status:', err);
        var alerta = document.getElementById('alerta-painel');
        if (alerta && String(err.message).indexOf('403') !== -1) {
          alerta.hidden = false;
          alerta.textContent = 'A verificação anti-bot não pôde ser concluída. Recarregue a página para tentar novamente.';
        }
      });
  }

  function buscarHistoricoPainel() {
    var j = JANELAS[state.janela] || JANELAS['24h'];
    var url = api('/api/historico?documento=' + encodeURIComponent(state.documento) +
                  '&tp_amb=' + state.tpAmb + '&horas=' + j.horas);
    return fetchProtegido(url)
      .then(function (r) {
        if (!r.ok) throw new Error('HTTP ' + r.status);
        return r.json();
      })
      .then(function (data) {
        state.historicoPainel = data;
        if (state.viz === 'linha') {
          renderLinha('linha-painel', data.series || {}, data.ufs || [], j.horas);
        }
      })
      .catch(function (err) {
        console.warn('[monitor] falha /api/historico:', err);
      });
  }

  // ===== Inicialização do DETALHE ===========================================
  function initDetalhe() {
    state.embed = isEmbed();
    if (state.embed) document.body.classList.add('embed-mode');
    var uf = getQueryParam('uf', '').toUpperCase();
    if (!uf || !/^[A-Z]{2}$/.test(uf)) {
      var main = document.querySelector('main');
      if (main) clear(main);
      var container = document.querySelector('.container');
      if (container) container.appendChild(el('p', { class: 'loading' }, 'UF inválida. Volte ao painel e escolha uma UF.'));
      return;
    }
    var doc = getQueryParam('doc', state.documento);
    var amb = Number(getQueryParam('amb', String(state.tpAmb))) || state.tpAmb;

    // Atualiza título da página
    document.title = uf + ' — Monitor Status DFe';
    var ufH1 = document.getElementById('detalhe-uf');
    if (ufH1) ufH1.textContent = uf;

    iniciarTurnstile();

    // Precisamos dos modelos para o toggle; se o state não tem, buscamos /api/status
    var ready = state.modelos.length ? Promise.resolve() : fetchProtegido(api('/api/status')).then(function (r) {
      if (!r.ok) throw new Error('HTTP ' + r.status);
      return r.json();
    }).then(function (data) {
      state.modelos = data.modelos || [];
      state.ambientes = data.ambientes || state.ambientes;
      if (state.modelos.length && !state.modelos.find(function (m) { return m.codigo === doc; })) {
        doc = state.modelos[0].codigo;
      }
    }).catch(function (e) { console.warn('[monitor] falha /api/status:', e); });

    ready.then(function () {
      // Atualiza subtítulo
      var modelo = state.modelos.find(function (m) { return m.codigo === doc; });
      var ambObj = state.ambientes.find(function (a) { return a.tp_amb === amb; });
      var modeloEl = document.getElementById('detalhe-modelo');
      var ambEl = document.getElementById('detalhe-ambiente');
      if (modeloEl) modeloEl.textContent = modelo ? modelo.nome : '—';
      if (ambEl) ambEl.textContent = ambObj ? ambObj.rotulo : '—';

      // Preenche toggle de modelo
      preencherModeloToggle('detalhe-modelo-toggle', state.modelos, doc, function (novoDoc) {
        // Atualiza URL sem recarregar
        var url = 'detalhe.html?uf=' + uf + '&doc=' + novoDoc + '&amb=' + amb + (state.embed ? '&embed=1' : '');
        history.replaceState(null, '', url);
        doc = novoDoc;
        if (modeloEl) {
          var m = state.modelos.find(function (x) { return x.codigo === novoDoc; });
          modeloEl.textContent = m ? m.nome : '—';
        }
        buscarHistoricoDetalhe(uf, doc, amb);
      });

      marcarAmbAtivo('detalhe-amb-toggle', amb);
      bindAmbToggle('detalhe-amb-toggle', function (novoAmb) {
        var url = 'detalhe.html?uf=' + uf + '&doc=' + doc + '&amb=' + novoAmb + (state.embed ? '&embed=1' : '');
        history.replaceState(null, '', url);
        amb = novoAmb;
        if (ambEl) {
          var a = state.ambientes.find(function (x) { return x.tp_amb === novoAmb; });
          ambEl.textContent = a ? a.rotulo : '—';
        }
        buscarHistoricoDetalhe(uf, doc, amb);
      });

      marcarJanelaAtiva('detalhe-janela-sel', state.janela);
      bindJanelaSel('detalhe-janela-sel', function () { buscarHistoricoDetalhe(uf, doc, amb); });

      // Botão Atualizar (detalhe)
      var btnAtualizarDetalhe = document.getElementById('btn-atualizar-detalhe');
      if (btnAtualizarDetalhe) {
        btnAtualizarDetalhe.addEventListener('click', function () {
          btnAtualizarDetalhe.disabled = true;
          btnAtualizarDetalhe.classList.add('btn-atualizar--loading');
          buscarHistoricoDetalhe(uf, doc, amb).then(function () {
            btnAtualizarDetalhe.disabled = false;
            btnAtualizarDetalhe.classList.remove('btn-atualizar--loading');
          }).catch(function () {
            btnAtualizarDetalhe.disabled = false;
            btnAtualizarDetalhe.classList.remove('btn-atualizar--loading');
          });
        });
      }

      // Botões exportar
      var btnCsv = document.getElementById('btn-export-csv');
      var btnJson = document.getElementById('btn-export-json');
      if (btnCsv) btnCsv.addEventListener('click', function () {
        if (state._pontosDetalhe) exportarCSV(state._pontosDetalhe, uf, doc, amb);
      });
      if (btnJson) btnJson.addEventListener('click', function () {
        if (state._pontosDetalhe) exportarJSON(state._pontosDetalhe, uf, doc, amb);
      });

      buscarHistoricoDetalhe(uf, doc, amb);
    });
  }

  function buscarHistoricoDetalhe(uf, doc, amb) {
    var j = JANELAS[state.janela] || JANELAS['24h'];
    var url = api('/api/uf/' + encodeURIComponent(uf) + '/historico?horas=' + j.horas +
                  '&documento=' + encodeURIComponent(doc) + '&tp_amb=' + amb);
    return fetchProtegido(url)
      .then(function (r) {
        if (!r.ok) throw new Error('HTTP ' + r.status);
        return r.json();
      })
      .then(function (data) {
        state._pontosDetalhe = data.pontos || [];
        var ultimo = data.ultimo;

        // Preenche os 8 campos do card "Último status"
        var fields = {
          'estado': ultimo ? el('span', { class: 'badge', style: { background: ultimo.cor || COR_ESTADO.sem_dados } }, ultimo.rotulo || 'Sem dados') : 'Sem dados',
          'motivo': ultimo ? (ultimo.x_motivo || '—') : '—',
          'cstat': ultimo ? (ultimo.cstat || '—') : '—',
          'aplicacao': ultimo ? (ultimo.ver_aplic || '—') : '—',
          'latencia': function () {
            var lat = latenciaDe(ultimo);
            var span = el('span', {}, fmtMs(lat));
            var cor = corSla(lat);
            if (cor) span.style.color = cor;
            return span;
          },
          'recebido-em': ultimo ? (ultimo.dh_recebto || '—') : '—',
          'coletado-em': ultimo ? fmtDatetime(ultimo.coletado_em) : '—',
          'mensagem': ultimo ? (ultimo.msg || '—') : '—'
        };
        Object.keys(fields).forEach(function (k) {
          var dd = document.getElementById('campo-' + k);
          if (!dd) return;
          clear(dd);
          var val = fields[k];
          if (typeof val === 'function') dd.appendChild(val());
          else if (val && typeof val === 'object' && val.nodeType) dd.appendChild(val);
          else dd.textContent = String(val == null ? '—' : val);
        });

        // Uptime
        var uptimePct = document.getElementById('uptime-pct');
        var uptimeFill = document.getElementById('uptime-fill');
        if (data.pontos && data.pontos.length) {
          if (uptimePct) uptimePct.textContent = (data.uptime_pct || 0).toFixed(1);
          if (uptimeFill) uptimeFill.style.width = (data.uptime_pct || 0) + '%';
        } else {
          if (uptimePct) uptimePct.textContent = '—';
          if (uptimeFill) uptimeFill.style.width = '0%';
        }

        // Gráfico de linha (single UF, sem legenda de UFs, cor da marca)
        var series = {}; series[uf] = data.pontos || [];
        renderLinha('linha-detalhe', series, [uf], j.horas, { noLegenda: true, corLinha: '#054687' });

        // Incidentes
        renderIncidentes(document.getElementById('incidents-list'), data.pontos || []);

        // Tabela de coletas recentes
        renderRecentTable(document.getElementById('recent-table'), data.pontos || []);
      })
      .catch(function (err) {
        console.warn('[monitor] falha histórico:', err);
      });
  }

  // ===== Bootstrap ==========================================================
  function init() {
    var page = document.body.getAttribute('data-page');
    if (page === 'detalhe') initDetalhe();
    else if (page === 'index') initIndex();
    // faq/termos não precisam de JS
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();
})();
