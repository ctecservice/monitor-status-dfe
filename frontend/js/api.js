/* ============================================================================
   api.js — Inicialização do Swagger UI para a página /api.html
   Detecta se SwaggerUIBundle está disponível (via vendor scripts) e monta
   a documentação interativa a partir do spec OpenAPI da API.
   ============================================================================ */
(function () {
  'use strict';

  var container = document.getElementById('swagger-ui');
  if (!container) return;

  // Aguarda os scripts vendor carregarem
  function initSwagger() {
    if (typeof SwaggerUIBundle === 'undefined') {
      container.innerHTML = '<div class="api-doc__swagger-error">Não foi possível carregar a documentação interativa.</div>';
      return;
    }

    var cfg = window.MONITOR_CONFIG || {};
    var apiBaseUrl = (cfg.apiBaseUrl || '').replace(/\/+$/, '');
    var specUrl = apiBaseUrl + '/api/openapi.yaml';

    // Botão de download aponta para a API correta (mesma origem ou remota).
    var btnDownload = document.getElementById('btn-download-openapi');
    if (btnDownload) {
      btnDownload.href = specUrl + '?download=1';
    }

    try {
      SwaggerUIBundle({
        url: specUrl,
        dom_id: '#swagger-ui',
        presets: [SwaggerUIBundle.presets.apis],
        layout: 'BaseLayout',
        deepLinking: true
      });
    } catch (err) {
      console.warn('[monitor] falha ao inicializar Swagger UI:', err);
      container.innerHTML = '<div class="api-doc__swagger-error">Não foi possível carregar a documentação interativa.</div>';
    }
  }

  // Swagger UI scripts são carregados sem defer, então já estão disponíveis
  // quando este script executa. Mas usamos DOMContentLoaded como garantia.
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initSwagger);
  } else {
    initSwagger();
  }
})();
