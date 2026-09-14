/* SuperEzio — Control Panel: o plano de controle MIKE -> Ezio dentro do painel do Ezio.
 *
 * O QUE ESTE BLOCO RESOLVE
 * ------------------------
 * O que o MIKE pediu e foi NEGADO so aparecia no console do bridge (:8009), que e
 * a tela do OUTRO sistema. O dono olhava o painel do Ezio e nao via a recusa.
 * Este bloco traz a mesma fonte para ca: o que foi pedido, o que foi NEGADO (com
 * `origin` e `reason`) e o veredito dos aplicados.
 *
 * FONTE UNICA (nada e inventado aqui)
 * -----------------------------------
 * GET http://127.0.0.1:8009/console/state, o mesmo JSON que o console do bridge
 * consome (bridge/console.py:build_state). Loopback, SEM credencial — decisao de
 * projeto de 12/09/2026: nao ha token a vazar nem a rotacionar. A fronteira e o
 * bind em 127.0.0.1. Por isso o fetch nao manda credencial nenhuma.
 *
 *   blocked[]  {ts, kind, state, command_id, reason, ezio_status, origin}
 *              `origin` diz QUEM barrou:
 *                "bridge" = allowlist default-deny: nem chegou ao Ezio;
 *                "ezio"   = chegou ao Ezio e foi recusado la.
 *   commands[] veredito: applied | rejected | unknown (unknown = em voo, NUNCA
 *              "aplicado" — bridge/commands.py:30-42). Os blocked saem daqui.
 *
 * NEGADO PESA MAIS QUE APLICADO
 * -----------------------------
 * Aplicado e rotina: linha fina, cinza, discreta. Recusa e sinal: tarja vermelha,
 * kind em destaque, motivo e origem. Nao e decoracao — e a informacao que o dono
 * precisa ver primeiro, entao ela vem primeiro e ocupa mais.
 *
 * FONTE MORTA NAO FICA EM SILENCIO
 * --------------------------------
 * Painel vazio quando a fonte morre e o defeito que este bloco conserta. Por isso
 * o estado da fonte e sempre visivel, e a falha e classificada em duas:
 *   - "fora do ar": nem socket. O bridge nao respondeu.
 *   - "ilegivel":  o bridge respondeu, mas o NAVEGADOR nao pode ler a resposta
 *                  (CORS). Sonda: um fetch mode:"no-cors" resolve como opaque se
 *                  o servidor esta no ar e rejeita se esta fora — e assim que as
 *                  duas falhas, que o fetch normal reporta igual, se separam.
 * Com dados antigos em tela, eles ficam marcados como desatualizados: o painel
 * nunca mostra dado velho com cara de novo.
 *
 * SEGURANCA: todo valor entra por textContent — o conteudo vem de outro sistema
 * e payload de evento e texto de fora. Nunca innerHTML aqui.
 */
(function () {
  "use strict";

  var STATE_URL = "http://127.0.0.1:8009/console/state";
  var POLL_MS = 5000;
  var TIMEOUT_MS = 4000;
  var MAX_ITENS = 8; // por secao; o resto vira "mais N"

  // Como cada `origin` do bridge se explica ao dono (bridge/console.py:407-441).
  var ORIGEM = {
    bridge: "barrado pelo bridge (allowlist) — nem chegou ao Ezio",
    ezio: "chegou ao Ezio e foi recusado la",
  };

  // Veredito do comando (bridge/commands.py:30-42).
  var VEREDITO = {
    applied: { rotulo: "APLICADO", classe: "cp-veredito--applied" },
    unknown: { rotulo: "EM VOO", classe: "cp-veredito--unknown" },
  };

  var el = null; // referencia do container, resolvida no boot
  var corpo = null;
  var visto = {}; // nos montados uma vez
  var ultimoBom = null; // ultimo payload valido (para nao apagar a tela na falha)
  var ultimoBomEm = null; // Date do ultimo payload valido
  var timer = null;
  var ocupado = false;
  // "lendo" | "ok" | "fora" | "ilegivel" | "http" | "formato"
  var fonteSituacao = "lendo";

  /* ---------------- utilidades ---------------- */

  function criar(tag, classe, texto) {
    var no = document.createElement(tag);
    if (classe) no.className = classe;
    if (texto !== undefined && texto !== null && texto !== "") {
      no.textContent = String(texto);
    }
    return no;
  }

  function limpar(no) {
    if (!no) return;
    while (no.firstChild) no.removeChild(no.firstChild);
  }

  function texto(valor, padrao) {
    if (valor === undefined || valor === null) return padrao === undefined ? "" : padrao;
    var s = String(valor);
    return s === "" ? (padrao === undefined ? "" : padrao) : s;
  }

  function lista(valor) {
    return Object.prototype.toString.call(valor) === "[object Array]" ? valor : [];
  }

  function objeto(valor) {
    return valor && typeof valor === "object" && !Array.isArray(valor) ? valor : {};
  }

  function hora(iso) {
    if (!iso) return "--:--:--";
    var d = new Date(iso);
    if (isNaN(d.getTime())) return texto(iso);
    return d.toLocaleTimeString("pt-BR", { hour12: false });
  }

  function idade(desde) {
    if (!desde) return "";
    var s = Math.max(0, Math.round((Date.now() - desde.getTime()) / 1000));
    if (s < 60) return "ha " + s + "s";
    if (s < 3600) return "ha " + Math.floor(s / 60) + "min";
    return "ha " + Math.floor(s / 3600) + "h";
  }

  function conta(n, singular, plural) {
    return n + " " + (n === 1 ? singular : plural);
  }

  /* ---------------- preferencia de abertura ---------------- */

  /* Este painel e um POPOVER, nao uma faixa: ele e ancorado (position: fixed),
     tem alca propria de abrir/fechar e a folha de estilo justifica ser opaco
     para o grafico atras nao diluir o vermelho. O que ninguem tinha decidido
     era ele abrir ABERTO: ancorado sobre o canto inferior esquerdo do grafico,
     ele tapava os candles ja no primeiro paint. O sinal mora no cabecalho — o
     contador de NEGADOS e a moldura vermelha — e o cabecalho aparece aberto ou
     fechado; o corpo e detalhe, entao abre so quando o operador pede. A escolha
     e lembrada entre sessoes. */
  var PREF_KEY = "sz_control_panel_aberto";

  function prefAberto() {
    try { return localStorage.getItem(PREF_KEY) === "1"; } catch (e) { return false; }
  }

  function salvarPref(aberto) {
    try { localStorage.setItem(PREF_KEY, aberto ? "1" : "0"); } catch (e) { /* ignore */ }
  }

  /* ---------------- montagem (uma vez) ---------------- */

  function montar() {
    limpar(el);
    el.classList.add("control-panel");

    var hd = criar("header", "cp-hd");
    var botao = criar("button", "cp-toggle");
    botao.type = "button";
    var aberto = prefAberto();
    botao.setAttribute("aria-expanded", aberto ? "true" : "false");
    botao.setAttribute("aria-controls", "cp-body");
    botao.appendChild(criar("span", "cp-title", "Plano de controle"));
    botao.appendChild(criar("span", "cp-sub", "MIKE → EZIO"));
    var badge = criar("span", "cp-badge cp-badge--standby", "standby (:8009)");
    botao.appendChild(badge);
    botao.appendChild(criar("span", "cp-chev", aberto ? "▾" : "▸"));
    hd.appendChild(botao);

    corpo = criar("div", "cp-body");
    corpo.id = "cp-body";
    if (!aberto) corpo.setAttribute("hidden", "");

    var secFonte = criar("div", "cp-fonte");
    var secNegado = criar("div", "cp-sec cp-sec--negado");
    var secVeredito = criar("div", "cp-sec");

    corpo.appendChild(secFonte);
    corpo.appendChild(secNegado);
    corpo.appendChild(secVeredito);
    el.appendChild(hd);
    el.appendChild(corpo);

    visto = { badge: badge, botao: botao, fonte: secFonte, negado: secNegado, veredito: secVeredito };

    botao.addEventListener("click", function () {
      var abrindo = corpo.hasAttribute("hidden");
      if (abrindo) {
        corpo.removeAttribute("hidden");
      } else {
        corpo.setAttribute("hidden", "");
      }
      botao.setAttribute("aria-expanded", abrindo ? "true" : "false");
      visto.chev.textContent = abrindo ? "▾" : "▸";
      salvarPref(abrindo);
    });
    visto.chev = hd.querySelector(".cp-chev");
  }

  /* ---------------- fonte: sempre visivel, falha nunca muda ---------------- */

  function pintarFonte(payload, situacao) {
    var alvo = visto.fonte;
    limpar(alvo);
    fonteSituacao = situacao;

    // Antes da primeira leitura: diz que esta lendo, nao fica mudo.
    if (!payload && (situacao === "ok" || situacao === "lendo")) {
      alvo.appendChild(criar("span", null, "lendo o estado do bridge em " + STATE_URL + "…"));
      return;
    }

    var saud = objeto(objeto(payload).health);
    var ezio = objeto(saud.ezio);
    var mike = objeto(saud.mike);

    if (payload) {
      alvo.appendChild(criar("span", null, "bridge " + texto(saud.version, "?")));
      alvo.appendChild(criar("span", null, "seq " + texto(payload.seq, "?")));
      alvo.appendChild(criar("span", null, "ezio " + (ezio.ezio_up === true ? "no ar" : "fora")));
      alvo.appendChild(criar("span", null, "mike " + (mike.reachable === true ? "no ar" : "fora")));
      alvo.appendChild(
        criar("span", null, "lido " + hora(payload.ts) + (ultimoBomEm ? " (" + idade(ultimoBomEm) + ")" : ""))
      );
    }

    if (situacao === "ok") return;

    // Fonte morta nao pode deixar o contador do cabecalho dizendo "0 negados":
    // esse zero nao foi medido. O contador passa a admitir que nao leu.
    pintarCabecalho(payload || ultimoBom);

    // Dado antigo em tela: diz que envelheceu, nao deixa passar por novo.
    if (payload) {
      alvo.appendChild(
        criar(
          "span",
          "cp-fonte__dica",
          "Dados de " + hora(payload.ts) + " (" + idade(ultimoBomEm) + ") — a leitura falhou depois disso."
        )
      );
    }

    if (situacao === "fora") {
      alvo.appendChild(
        criar("span", "cp-fonte__aviso", "CANAL DE CONTROLE EM STANDBY — Porta :8009")
      );
      alvo.appendChild(
        criar("span", "cp-fonte__dica", "Bridge MIKE ↔ Ezio aguardando inicializacao (scripts/start-bridge.ps1). O console do MIKE esta ativo em :8083.")
      );
    } else if (situacao === "ilegivel") {
      alvo.appendChild(
        criar(
          "span",
          "cp-fonte__erro",
          "BRIDGE NO AR, MAS ILEGIVEL PARA O NAVEGADOR (CORS) — " + STATE_URL + " respondeu, e o navegador recusou a leitura."
        )
      );
      alvo.appendChild(
        criar(
          "span",
          "cp-fonte__dica",
          "O bridge nao devolve Access-Control-Allow-Origin para a origem desta pagina. Enquanto isso, o painel nao consegue ler o estado — o console do bridge, em http://127.0.0.1:8009/console, continua vendo tudo."
        )
      );
    } else if (situacao === "http") {
      alvo.appendChild(criar("span", "cp-fonte__erro", "O bridge respondeu com erro HTTP — estado nao lido."));
    } else if (situacao === "formato") {
      alvo.appendChild(criar("span", "cp-fonte__erro", "O bridge respondeu algo que nao e o estado esperado."));
    }
  }

  /* ---------------- NEGADOS: o bloco de maior peso ---------------- */

  function pintarNegados(payload) {
    var sec = visto.negado;
    limpar(sec);
    var blocked = lista(objeto(payload).blocked);
    var total = Number(objeto(payload).blocked_total);

    var hd = criar("div", "cp-sec__hd");
    hd.appendChild(criar("span", "cp-sec__titulo", "Negados"));
    if (blocked.length) {
      hd.appendChild(criar("span", "cp-badge cp-badge--denied", conta(blocked.length, "negado", "negados")));
    }
    sec.appendChild(hd);

    if (!blocked.length) {
      sec.appendChild(criar("div", "cp-sec__vazio", "Nada negado. Nem pelo bridge, nem pelo Ezio."));
      return;
    }

    blocked.slice(0, MAX_ITENS).forEach(function (itemRaw) {
      var item = objeto(itemRaw);
      var origin = texto(item.origin);
      var caixa = criar("div", "cp-denied");

      var topo = criar("div", "cp-denied__top");
      topo.appendChild(criar("span", "cp-denied__kind", texto(item.kind, "(kind nao informado)")));
      topo.appendChild(criar("span", "cp-estado", texto(item.state, "denied")));
      var chip = criar(
        "span",
        "cp-origem " + (origin === "bridge" ? "cp-origem--bridge" : origin === "ezio" ? "cp-origem--ezio" : "cp-origem--outro"),
        origin === "bridge" ? "bridge" : origin === "ezio" ? "ezio" : texto(origin, "?")
      );
      chip.title = ORIGEM[origin] || "origem nao informada pelo bridge";
      topo.appendChild(chip);
      caixa.appendChild(topo);

      var quem = ORIGEM[origin] || "origem nao informada pelo bridge";
      var meta = hora(item.ts) + " — " + quem;
      if (item.ezio_status !== undefined && item.ezio_status !== null) {
        meta += " — HTTP " + texto(item.ezio_status);
      }
      if (item.command_id) meta += " — id " + texto(item.command_id);
      caixa.appendChild(criar("div", "cp-denied__meta", meta));

      if (texto(item.reason)) {
        caixa.appendChild(criar("div", "cp-denied__motivo", "motivo: " + texto(item.reason)));
      }
      sec.appendChild(caixa);
    });

    if (blocked.length > MAX_ITENS) {
      sec.appendChild(criar("div", "cp-mais", "mais " + (blocked.length - MAX_ITENS) + " negados na lista"));
    }
    if (!isNaN(total) && total > blocked.length) {
      sec.appendChild(criar("div", "cp-mais", "total no bridge: " + total));
    }
  }

  /* ---------------- veredito: rotina, peso baixo ---------------- */

  function pintarVeredito(payload) {
    var sec = visto.veredito;
    limpar(sec);

    var comandos = lista(objeto(payload).commands).filter(function (c) {
      return objeto(c).blocked !== true; // negado ja esta na secao de cima
    });

    var hd = criar("div", "cp-sec__hd");
    hd.appendChild(criar("span", "cp-sec__titulo", "Veredito dos pedidos"));
    var saud = objeto(objeto(payload).health);
    var allow = lista(objeto(saud.commands).allowlist);
    if (allow.length) {
      hd.appendChild(criar("span", "cp-sub", conta(allow.length, "kind permitido", "kinds permitidos")));
    }
    sec.appendChild(hd);

    if (!comandos.length) {
      var temNegado = lista(objeto(payload).blocked).length > 0;
      sec.appendChild(
        criar(
          "div",
          "cp-sec__vazio",
          temNegado
            ? "Nada aplicado: todo pedido registrado foi negado (acima)."
            : "Nenhum pedido registrado ainda."
        )
      );
    } else {
      comandos.slice(0, MAX_ITENS).forEach(function (itemRaw) {
        var item = objeto(itemRaw);
        var chave = texto(item.state);
        var conf = VEREDITO[chave];
        var linha = criar("div", "cp-linha");
        linha.appendChild(criar("span", "cp-linha__kind", texto(item.kind, "(kind nao informado)")));
        linha.appendChild(
          criar("span", "cp-veredito " + (conf ? conf.classe : "cp-veredito--outro"), conf ? conf.rotulo : texto(chave, "?"))
        );
        var meta = hora(item.ts);
        if (item.ezio_status !== undefined && item.ezio_status !== null) meta += " — HTTP " + texto(item.ezio_status);
        if (texto(item.detail)) meta += " — " + texto(item.detail);
        if (chave === "unknown") meta += " — em voo: NAO foi aplicado";
        linha.appendChild(criar("span", "cp-linha__meta", meta));
        sec.appendChild(linha);
      });
      if (comandos.length > MAX_ITENS) {
        sec.appendChild(criar("div", "cp-mais", "mais " + (comandos.length - MAX_ITENS) + " pedidos na lista"));
      }
    }

    if (allow.length) {
      sec.appendChild(criar("div", "cp-linha__meta", "permitidos: " + allow.join(" · ")));
    }
  }

  /* ---------------- contador do cabecalho ---------------- */

  function pintarCabecalho(payload) {
    var badge = visto.badge;

    // Sem leitura da fonte nao existe contagem — nem zero. Zero medido e uma
    // informacao; zero suposto e o silencio que este painel veio consertar.
    if (fonteSituacao !== "ok") {
      badge.textContent = "standby (:8009)";
      badge.className = "cp-badge cp-badge--standby";
      badge.title = "Bridge MIKE ↔ Ezio aguardando conexao na porta :8009";
      el.classList.remove("cp--tem-negado");
      return;
    }

    var blocked = lista(objeto(payload).blocked);
    var n = blocked.length;
    badge.textContent = n ? conta(n, "negado", "negados") : "0 negados";
    badge.className = "cp-badge " + (n ? "cp-badge--denied" : "cp-badge--zero");
    if (n) {
      el.classList.add("cp--tem-negado");
    } else {
      el.classList.remove("cp--tem-negado");
    }
  }

  function pintarTudo(payload) {
    pintarFonte(payload, "ok"); // primeiro: e ele que marca a fonte como lida
    pintarCabecalho(payload);
    pintarNegados(payload);
    pintarVeredito(payload);
  }

  /* ---------------- leitura da fonte ---------------- */

  function comPrazo(promessa, ms) {
    var controle = typeof AbortController === "function" ? new AbortController() : null;
    var relogio = null;
    var corrida = new Promise(function (resolve, reject) {
      if (!controle) return; // sem AbortController: so o fetch normal decide
      relogio = setTimeout(function () {
        controle.abort();
        reject(new Error("timeout"));
      }, ms);
    });
    var pedido = promessa(controle);
    if (!controle) return pedido;
    return Promise.race([pedido, corrida]).then(
      function (v) {
        clearTimeout(relogio);
        return v;
      },
      function (e) {
        clearTimeout(relogio);
        throw e;
      }
    );
  }

  function ler() {
    return comPrazo(function (controle) {
      return fetch(STATE_URL, {
        method: "GET",
        mode: "cors",
        cache: "no-store",
        credentials: "omit", // loopback sem credencial: decisao de projeto
        signal: controle ? controle.signal : undefined,
      });
    }, TIMEOUT_MS).then(function (resposta) {
      if (!resposta.ok) {
        return { situacao: "http", payload: null };
      }
      return resposta
        .json()
        .then(function (dados) {
          if (!dados || typeof dados !== "object") return { situacao: "formato", payload: null };
          return { situacao: "ok", payload: dados };
        })
        .catch(function () {
          return { situacao: "formato", payload: null };
        });
    });
  }

  // O fetch normal reporta "fora do ar" e "barrado por CORS" do mesmo jeito
  // ("Failed to fetch"). A sonda no-cors separa: opaque = servidor no ar.
  function sondaNoCors() {
    return comPrazo(function (controle) {
      return fetch(STATE_URL, {
        method: "GET",
        mode: "no-cors",
        cache: "no-store",
        credentials: "omit",
        signal: controle ? controle.signal : undefined,
      });
    }, TIMEOUT_MS).then(
      function () {
        return "ilegivel";
      },
      function () {
        return "fora";
      }
    );
  }

  function classificarFalha() {
    return sondaNoCors().then(function (situacao) {
      if (situacao === "fora") return "fora";
      return "ilegivel";
    });
  }

  function ciclo() {
    if (ocupado) return;
    if (document.hidden) {
      agendar();
      return;
    }
    ocupado = true;
    ler()
      .then(function (resultado) {
        if (resultado.situacao === "ok") {
          ultimoBom = resultado.payload;
          ultimoBomEm = new Date();
          el.classList.remove("cp--fonte-morta");
          pintarTudo(ultimoBom);
          return null;
        }
        if (resultado.situacao === "http" || resultado.situacao === "formato") {
          el.classList.add("cp--fonte-morta");
          pintarFonte(ultimoBom, resultado.situacao);
          return null;
        }
        return null;
      })
      .catch(function () {
        // Falha de rede/CORS: separa as duas antes de acusar.
        return classificarFalha().then(function (situacao) {
          el.classList.add("cp--fonte-morta");
          pintarFonte(ultimoBom, situacao);
        });
      })
      .then(function () {
        ocupado = false;
        agendar();
      });
  }

  function agendar() {
    if (timer) clearTimeout(timer);
    timer = setTimeout(ciclo, POLL_MS);
  }

  /* ---------------- boot ---------------- */

  function iniciar() {
    el = document.getElementById("control-panel");
    if (!el) return; // sem container, nada a fazer (nao quebra o resto da pagina)
    try {
      montar();
    } catch (e) {
      el.textContent = "Plano de controle: falha ao montar o painel.";
      return;
    }
    if (document.hidden) {
      corpo.setAttribute("hidden", "");
      visto.botao.setAttribute("aria-expanded", "false");
    }
    // Sem dado ainda: a fonte aparece antes do primeiro resultado para o painel
    // nunca ficar mudo enquanto a primeira leitura nao volta.
    pintarFonte(null, "lendo");
    ciclo();

    document.addEventListener("visibilitychange", function () {
      if (!document.hidden) ciclo();
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", iniciar);
  } else {
    iniciar();
  }
})();
