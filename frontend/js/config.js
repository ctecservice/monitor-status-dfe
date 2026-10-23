/* ============================================================================
   config.js — Configuração do frontend Monitor Status DFe
   - apiBaseUrl: string vazia = mesma origem (quando servido pelo próprio Flask).
     Para deploy standalone (Vercel), preencha com a URL pública da API.
     Ex.: "https://8rdtnk.bot-keep.xyz"
   - turnstileSiteKey: preencha somente quando o backend estiver com Turnstile
     ativo. Vazio = widget desligado e fetches comuns.
   ============================================================================ */
(function (global) {
  'use strict';
  global.MONITOR_CONFIG = {
    // URL base da API. Vazio = mesma origem (relative URLs).
    // Exemplo para deploy standalone: "https://monitor.exemplo.com"
    apiBaseUrl: "",

    // Site key do Cloudflare Turnstile. Vazio = sem anti-bot.
    // Exemplo: "0x4AAAAAAA..."
    turnstileSiteKey: ""
  };
})(typeof window !== 'undefined' ? window : this);
