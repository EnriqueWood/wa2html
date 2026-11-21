/* wa2html viewer: the runtime of a generated chat page. No dependencies,
   no network access (the page's Content-Security-Policy forbids it). */
(function () {
  'use strict';

  var CFG = JSON.parse(document.getElementById('wa-config').textContent);
  var STR = CFG.strings;
  var KEY = 'wa2html:' + CFG.chatKey;
  var D = CFG.defaults || {};
  var root = document.documentElement;

  function $(sel) { return document.querySelector(sel); }
  function $all(sel, base) { return Array.prototype.slice.call((base || document).querySelectorAll(sel)); }

  /* -- settings ---------------------------------------------------------- */

  var DEFAULTS = {
    theme: D.theme || 'auto',
    wallpaper: D.wallpaper || 'default',
    pattern: D.pattern !== false,
    wallImage: D.wallImage || null,
    dim: 0,
    out: null,
    inn: null,
    font: 14.5,
    time: D.time || '24',
    lang: D.lang || 'auto',
    me: CFG.me || '',
    sys: true,
    rate: 1
  };
  var S = load();

  function load() {
    var saved = {};
    try { saved = JSON.parse(localStorage.getItem(KEY) || '{}') || {}; } catch (e) { saved = {}; }
    var s = {};
    for (var k in DEFAULTS) s[k] = Object.prototype.hasOwnProperty.call(saved, k) ? saved[k] : DEFAULTS[k];
    return s;
  }
  function save() {
    try { localStorage.setItem(KEY, JSON.stringify(S)); return true; } catch (e) { return false; }
  }

  /* -- language and dates -------------------------------------------------- */

  function lang() {
    var l = S.lang;
    if (l === 'auto') l = (navigator.language || 'en').slice(0, 2).toLowerCase();
    return STR[l] ? l : 'en';
  }
  function t(key) {
    var table = STR[lang()] || STR.en;
    return table[key] || STR.en[key] || key;
  }
  function parseTs(s) {
    var m = /^(\d{4})-(\d{2})-(\d{2})(?:T(\d{2}):(\d{2})(?::(\d{2}))?)?/.exec(s || '');
    if (!m) return null;
    return new Date(Date.UTC(+m[1], +m[2] - 1, +m[3], +(m[4] || 0), +(m[5] || 0), +(m[6] || 0)));
  }
  function formatter(opts) {
    opts.timeZone = 'UTC';  // timestamps are wall-clock times from the phone
    try { return new Intl.DateTimeFormat(lang(), opts); } catch (e) { return null; }
  }
  function capitalize(s) { return s ? s.charAt(0).toUpperCase() + s.slice(1) : s; }
  function fmtDur(secs) {
    secs = Math.max(0, Math.round(secs || 0));
    var h = Math.floor(secs / 3600), m = Math.floor((secs % 3600) / 60), s = secs % 60;
    return (h ? h + ':' + (m < 10 ? '0' : '') : '') + m + ':' + (s < 10 ? '0' : '') + s;
  }

  function renderDates() {
    var timeFmt = formatter({ hour: 'numeric', minute: '2-digit', hour12: S.time === '12' });
    var dayFmt = formatter({ weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' });
    var shortFmt = formatter({ day: 'numeric', month: 'short', year: 'numeric' });
    if (timeFmt) $all('time[data-ts]').forEach(function (el) {
      var d = parseTs(el.getAttribute('data-ts'));
      if (d) el.textContent = timeFmt.format(d);
    });
    if (dayFmt) $all('.day-sep span[data-date]').forEach(function (el) {
      var d = parseTs(el.getAttribute('data-date'));
      if (d) el.textContent = capitalize(dayFmt.format(d));
    });
    if (shortFmt) $all('.dayname[data-date]').forEach(function (el) {
      var d = parseTs(el.getAttribute('data-date'));
      if (d) el.textContent = shortFmt.format(d);
    });
    root.style.setProperty('--meta-w', S.time === '12' ? '66px' : '44px');
  }

  function applyLang() {
    root.lang = lang();
    $all('[data-i18n]').forEach(function (el) { el.textContent = t(el.getAttribute('data-i18n')); });
    $all('[data-i18n-title]').forEach(function (el) {
      var v = t(el.getAttribute('data-i18n-title'));
      el.title = v;
      el.setAttribute('aria-label', v);
    });
    $all('[data-i18n-ph]').forEach(function (el) { el.placeholder = t(el.getAttribute('data-i18n-ph')); });
    renderDates();
  }

  /* -- appearance ---------------------------------------------------------- */

  var WALLS = ['default', '#efeae2', '#dfe7ec', '#e8dff5', '#fde2e4', '#e2f0cb', '#fff1c1', '#cde7f0', '#d7ccc8',
    '#1f2c34', '#2d2438', '#0b141a',
    'linear-gradient(160deg,#a1c4fd,#c2e9fb)', 'linear-gradient(160deg,#fbc2eb,#a6c1ee)',
    'linear-gradient(160deg,#fdfcfb,#e2d1c3)', 'linear-gradient(160deg,#84fab0,#8fd3f4)',
    'linear-gradient(160deg,#f6d365,#fda085)', 'linear-gradient(160deg,#0f2027,#203a43,#2c5364)'];
  var OUT_COLORS = [null, '#d9fdd3', '#dcf8c6', '#cfe9ff', '#ffe0ec', '#efe1ff', '#fff3c4', '#005c4b', '#6d4aff', '#1f6feb'];
  var IN_COLORS = [null, '#ffffff', '#f0f2f5', '#e7f3ff', '#fff8e1', '#f3e8ff', '#202c33', '#2a2f32'];

  function luminance(color) {
    var m = /^#?([0-9a-f]{6})$/i.exec(color || '');
    if (!m) return 1;
    var n = parseInt(m[1], 16);
    var c = [(n >> 16) & 255, (n >> 8) & 255, n & 255].map(function (v) {
      v /= 255;
      return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4);
    });
    return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2];
  }
  function setBubble(prefix, color) {
    var st = root.style;
    if (!color) {
      ['-bg', '-fg', '-meta'].forEach(function (p) { st.removeProperty('--' + prefix + p); });
      if (prefix === 'out') st.removeProperty('--out-wave');
      return;
    }
    var dark = luminance(color) < 0.35;
    st.setProperty('--' + prefix + '-bg', color);
    st.setProperty('--' + prefix + '-fg', dark ? '#f1f3f4' : '#111b21');
    st.setProperty('--' + prefix + '-meta', dark ? 'rgba(255,255,255,.68)' : 'rgba(0,0,0,.48)');
    if (prefix === 'out') st.setProperty('--out-wave', dark ? '#b6f0ff' : '#1d8fa3');
  }

  function applyLook() {
    root.setAttribute('data-theme', S.theme);
    var bg = '';
    if (S.wallpaper === 'image' && S.wallImage) bg = 'url("' + S.wallImage + '") center / cover no-repeat';
    else if (S.wallpaper && S.wallpaper !== 'default' && S.wallpaper !== 'doodle') bg = S.wallpaper;
    if (bg) root.style.setProperty('--wall-bg', bg); else root.style.removeProperty('--wall-bg');
    $('#wall').classList.toggle('pattern', !!S.pattern);
    root.style.setProperty('--wall-dim', String((S.dim || 0) / 100));
    setBubble('out', S.out);
    setBubble('in', S.inn);
    root.style.setProperty('--fs', S.font + 'px');
    document.body.classList.toggle('hide-sys', !S.sys);
  }

  function applyMe() {
    $all('.msg[data-s]').forEach(function (el) {
      var out = !!S.me && el.getAttribute('data-s') === S.me;
      el.classList.toggle('out', out);
      el.classList.toggle('in', !out);
    });
  }

  /* -- settings panel -------------------------------------------------------- */

  function swatch(value, kind) {
    var b = document.createElement('button');
    b.type = 'button';
    b.className = 'swatch';
    b.setAttribute('data-v', value === null ? '' : value);
    if (value === null || value === 'default') {
      b.classList.add('def');
      b.textContent = 'A';
      b.title = t('defaultColor');
      b.style.background = kind === 'wall' ? 'var(--bg)' : 'var(--' + kind + '-bg-default, transparent)';
    } else {
      b.style.background = value;
      b.title = value;
    }
    return b;
  }
  function customSwatch(kind) {
    var wrap = document.createElement('label');
    wrap.className = 'swatch custom';
    wrap.textContent = '+';
    var input = document.createElement('input');
    input.type = 'color';
    input.setAttribute('data-kind', kind);
    wrap.appendChild(input);
    return wrap;
  }
  function buildSettings() {
    var meSel = $('#set-me');
    meSel.innerHTML = '';
    CFG.senders.forEach(function (s) {
      var o = document.createElement('option');
      o.value = s.id;
      o.textContent = s.name;
      meSel.appendChild(o);
    });
    var none = document.createElement('option');
    none.value = '';
    none.setAttribute('data-i18n', 'nobody');
    meSel.appendChild(none);

    var langSel = $('#set-lang');
    langSel.innerHTML = '';
    var auto = document.createElement('option');
    auto.value = 'auto';
    auto.setAttribute('data-i18n', 'langAuto');
    langSel.appendChild(auto);
    Object.keys(STR).forEach(function (code) {
      var o = document.createElement('option');
      o.value = code;
      o.textContent = STR[code]._name || code;
      langSel.appendChild(o);
    });

    var walls = $('#set-wall');
    WALLS.forEach(function (v) { walls.appendChild(swatch(v, 'wall')); });
    walls.appendChild(customSwatch('wall'));
    var outs = $('#set-out');
    OUT_COLORS.forEach(function (v) { outs.appendChild(swatch(v, 'out')); });
    outs.appendChild(customSwatch('out'));
    var ins = $('#set-in');
    IN_COLORS.forEach(function (v) { ins.appendChild(swatch(v, 'in')); });
    ins.appendChild(customSwatch('in'));

    walls.addEventListener('click', function (e) {
      var b = e.target.closest('.swatch[data-v]');
      if (!b) return;
      S.wallpaper = b.getAttribute('data-v') || 'default';
      commit();
    });
    outs.addEventListener('click', function (e) {
      var b = e.target.closest('.swatch[data-v]');
      if (!b) return;
      S.out = b.getAttribute('data-v') || null;
      commit();
    });
    ins.addEventListener('click', function (e) {
      var b = e.target.closest('.swatch[data-v]');
      if (!b) return;
      S.inn = b.getAttribute('data-v') || null;
      commit();
    });
    $all('.swatch.custom input').forEach(function (input) {
      input.addEventListener('input', function () {
        var kind = input.getAttribute('data-kind');
        if (kind === 'wall') S.wallpaper = input.value;
        else if (kind === 'out') S.out = input.value;
        else S.inn = input.value;
        commit();
      });
    });

    meSel.addEventListener('change', function () { S.me = meSel.value; commit(); applyMe(); });
    langSel.addEventListener('change', function () { S.lang = langSel.value; commit(); applyLang(); });
    $('#set-theme').addEventListener('click', function (e) {
      var b = e.target.closest('button[data-v]');
      if (b) { S.theme = b.getAttribute('data-v'); commit(); }
    });
    $('#set-time').addEventListener('click', function (e) {
      var b = e.target.closest('button[data-v]');
      if (b) { S.time = b.getAttribute('data-v'); commit(); renderDates(); }
    });
    $('#set-pattern').addEventListener('change', function (e) { S.pattern = e.target.checked; commit(); });
    $('#set-dim').addEventListener('input', function (e) { S.dim = +e.target.value; commit(); });
    $('#set-font').addEventListener('input', function (e) { S.font = +e.target.value; commit(); });
    $('#set-sys').addEventListener('change', function (e) { S.sys = e.target.checked; commit(); });
    $('#set-wall-file').addEventListener('change', function (e) {
      var file = e.target.files && e.target.files[0];
      if (file) loadWallpaper(file);
      e.target.value = '';
    });
    $('#set-reset').addEventListener('click', function () {
      var me = S.me, lng = S.lang, rate = S.rate;
      S = load();
      for (var k in DEFAULTS) S[k] = DEFAULTS[k];
      S.me = me; S.lang = lng; S.rate = rate;
      commit();
      applyMe();
      renderDates();
    });
  }

  function syncSettings() {
    $('#set-me').value = S.me || '';
    $('#set-lang').value = S.lang;
    $all('#set-theme button').forEach(function (b) { b.classList.toggle('on', b.getAttribute('data-v') === S.theme); });
    $all('#set-time button').forEach(function (b) { b.classList.toggle('on', b.getAttribute('data-v') === S.time); });
    var wall = S.wallpaper === 'doodle' ? 'default' : S.wallpaper;
    $all('#set-wall .swatch[data-v]').forEach(function (b) { b.classList.toggle('on', b.getAttribute('data-v') === wall); });
    $all('#set-out .swatch[data-v]').forEach(function (b) { b.classList.toggle('on', (b.getAttribute('data-v') || null) === S.out); });
    $all('#set-in .swatch[data-v]').forEach(function (b) { b.classList.toggle('on', (b.getAttribute('data-v') || null) === S.inn); });
    $('#set-pattern').checked = !!S.pattern;
    $('#set-dim').value = S.dim;
    $('#set-font').value = S.font;
    $('#set-sys').checked = !!S.sys;
  }

  function commit() {
    applyLook();
    syncSettings();
    var ok = save();
    var msg = $('#wall-msg');
    if (!ok && S.wallpaper === 'image') { msg.textContent = t('wallpaperTooBig'); msg.hidden = false; }
    else msg.hidden = true;
  }

  function loadWallpaper(file) {
    var url = URL.createObjectURL(file);
    var img = new Image();
    img.onload = function () {
      var scale = Math.min(1, 1920 / Math.max(img.naturalWidth, img.naturalHeight));
      var canvas = document.createElement('canvas');
      canvas.width = Math.round(img.naturalWidth * scale);
      canvas.height = Math.round(img.naturalHeight * scale);
      canvas.getContext('2d').drawImage(img, 0, 0, canvas.width, canvas.height);
      URL.revokeObjectURL(url);
      S.wallImage = canvas.toDataURL('image/jpeg', 0.85);
      S.wallpaper = 'image';
      S.pattern = false;
      commit();
    };
    img.src = url;
  }

  /* -- panels ------------------------------------------------------------------ */

  var openPanel = null;
  function showPanel(id) {
    closePanel();
    openPanel = $(id);
    openPanel.hidden = false;
    $('#scrim').hidden = false;
    var first = openPanel.querySelector('button, select, input');
    if (first) first.focus();
  }
  function closePanel() {
    if (openPanel) openPanel.hidden = true;
    openPanel = null;
    $('#scrim').hidden = true;
  }

  /* -- media ------------------------------------------------------------------- */

  var urls = {};
  var mediaReady = false;

  function bytesFromBase64(b64) {
    if (typeof Uint8Array.fromBase64 === 'function') return Uint8Array.fromBase64(b64);
    var bin = atob(b64), n = bin.length, out = new Uint8Array(n);
    for (var i = 0; i < n; i++) out[i] = bin.charCodeAt(i);
    return out;
  }
  function mediaUrl(ref) {
    if (!ref) return null;
    if (ref.charAt(0) !== '#') return ref;  // folder mode: a relative path
    if (urls[ref]) return urls[ref];
    var block = document.getElementById(ref.slice(1));
    if (!block) return null;
    var blob = new Blob([bytesFromBase64(block.textContent)], { type: block.getAttribute('data-mime') || 'application/octet-stream' });
    urls[ref] = URL.createObjectURL(blob);
    return urls[ref];
  }

  function download(ref, name) {
    var url = mediaUrl(ref);
    if (!url) return;
    var a = document.createElement('a');
    a.href = url;
    a.download = name || 'file';
    document.body.appendChild(a);
    a.click();
    a.remove();
  }

  function hydrate(el) {
    if (el.tagName === 'IMG') {
      var u = mediaUrl(el.getAttribute('data-src'));
      if (u) el.src = u;
    } else if (el.tagName === 'VIDEO') {
      var v = mediaUrl(el.getAttribute('data-src'));
      if (!v) return;
      el.addEventListener('loadeddata', function () { el.parentNode.classList.add('ready'); }, { once: true });
      if (!el.autoplay) {
        el.addEventListener('loadedmetadata', function () { try { el.currentTime = 0.05; } catch (e) { /* ignore */ } }, { once: true });
      }
      el.src = v;
    } else if (el.hasAttribute('data-lottie')) {
      startLottie(el);
    }
  }

  function startLottie(el) {
    if (!window.lottie || el._anim) return;
    var block = document.getElementById(el.getAttribute('data-lottie').slice(1));
    if (!block) return;
    var data = null;
    try { data = JSON.parse(block.textContent); } catch (e) { data = null; }
    if (!data) return;
    el._anim = window.lottie.loadAnimation({ container: el, renderer: 'svg', loop: true, autoplay: true, animationData: data });
    el.classList.add('playing');
  }

  function startLazyMedia() {
    mediaReady = true;
    var targets = $all('#chat img[data-src], #chat video[data-src], #chat [data-lottie]');
    if (!('IntersectionObserver' in window)) { targets.forEach(hydrate); return; }
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (entry.isIntersecting) { io.unobserve(entry.target); hydrate(entry.target); }
      });
    }, { rootMargin: '1200px 0px' });
    targets.forEach(function (el) { io.observe(el); });
  }

  /* -- voice notes --------------------------------------------------------------- */

  var current = null;
  var raf = 0;

  function voiceDuration(v) {
    var a = v._audio;
    var d = a && isFinite(a.duration) && a.duration > 0 ? a.duration : parseFloat(v.getAttribute('data-dur'));
    return d > 0 ? d : 0;
  }
  function setProgress(v, frac) {
    v.style.setProperty('--p', (frac * 100).toFixed(2) + '%');
    var seek = v.querySelector('.v-seek');
    if (seek && document.activeElement !== seek) seek.value = Math.round(frac * 1000);
  }
  function setTime(v, secs) { v.querySelector('.v-time').textContent = fmtDur(secs); }
  function voiceError(v) {
    v.classList.remove('playing');
    v.classList.add('error');
    v.querySelector('.v-err').hidden = false;
  }
  function audioFor(v) {
    if (v._audio) return v._audio;
    var url = mediaUrl(v.getAttribute('data-src'));
    if (!url) { if (mediaReady) voiceError(v); return null; }
    var a = new Audio();
    a.preload = 'auto';
    a.addEventListener('ended', function () { onEnded(v); });
    a.addEventListener('error', function () { voiceError(v); });
    a.src = url;
    a.playbackRate = S.rate || 1;
    v._audio = a;
    return a;
  }
  function tick() {
    if (!current || !current._audio) { raf = 0; return; }
    var a = current._audio, d = voiceDuration(current);
    setProgress(current, d ? Math.min(1, a.currentTime / d) : 0);
    setTime(current, a.currentTime);
    raf = requestAnimationFrame(tick);
  }
  function play(v) {
    if (current && current !== v) pause(current);
    var a = audioFor(v);
    if (!a) return;
    current = v;
    v.classList.add('playing', 'started');
    a.playbackRate = S.rate || 1;
    var p = a.play();
    if (p && p.catch) p.catch(function (err) {
      if (err && err.name === 'AbortError') return;
      if (err && err.name === 'NotAllowedError') { v.classList.remove('playing'); return; }
      voiceError(v);
    });
    if (!raf) raf = requestAnimationFrame(tick);
  }
  function pause(v) {
    if (v._audio) v._audio.pause();
    v.classList.remove('playing');
    if (current === v) current = null;
  }
  function onEnded(v) {
    v.classList.remove('playing', 'started');
    setProgress(v, 0);
    setTime(v, voiceDuration(v));
    if (v._audio) v._audio.currentTime = 0;
    if (current === v) current = null;
    // Like WhatsApp: play the next voice message if it follows directly.
    var msg = v.closest('.msg');
    var next = msg && msg.nextElementSibling;
    if (next && next.classList.contains('k-voice')) play(next.querySelector('.voice'));
  }
  function seek(v, frac) {
    var a = audioFor(v);
    if (!a) return;
    var apply = function () {
      var d = voiceDuration(v);
      if (d) { a.currentTime = frac * d; setProgress(v, frac); setTime(v, frac * d); }
    };
    if (a.readyState >= 1) apply(); else a.addEventListener('loadedmetadata', apply, { once: true });
    v.classList.add('started');
  }
  function cycleSpeed() {
    var rates = [1, 1.5, 2];
    S.rate = rates[(rates.indexOf(S.rate || 1) + 1) % rates.length];
    save();
    if (current && current._audio) current._audio.playbackRate = S.rate;
    showSpeed();
  }
  function showSpeed() {
    var label = (S.rate || 1) + '×';
    $all('.v-speed').forEach(function (b) { b.textContent = label; });
  }

  /* -- lightbox ------------------------------------------------------------------ */

  var lb = { list: [], i: 0 };
  function senderName(msg) {
    var id = msg && msg.getAttribute('data-s');
    for (var i = 0; i < CFG.senders.length; i++) if (CFG.senders[i].id === id) return CFG.senders[i].name;
    return '';
  }
  function openLightbox(btn) {
    lb.list = $all('#chat .media.img');
    lb.i = Math.max(0, lb.list.indexOf(btn));
    $('#lightbox').hidden = false;
    document.body.style.overflow = 'hidden';
    showLightbox();
    $('#lb-close').focus();
  }
  function showLightbox() {
    var btn = lb.list[lb.i];
    if (!btn) return;
    var img = btn.querySelector('img');
    var url = mediaUrl(img.getAttribute('data-src'));
    $('#lb-img').src = url || '';
    var msg = btn.closest('.msg');
    var time = msg && msg.querySelector('time[data-ts]');
    var when = '';
    if (time) {
      var d = parseTs(time.getAttribute('data-ts'));
      var f = formatter({ day: 'numeric', month: 'long', year: 'numeric', hour: 'numeric', minute: '2-digit', hour12: S.time === '12' });
      when = d && f ? f.format(d) : '';
    }
    $('#lb-meta').textContent = [senderName(msg), when].filter(Boolean).join(' · ');
    var dl = $('#lb-download');
    var meta = btn.parentNode.querySelector('.dl');
    dl.href = url || '#';
    dl.setAttribute('download', meta ? meta.getAttribute('data-name') : 'photo');
    $('#lb-prev').style.visibility = lb.i > 0 ? 'visible' : 'hidden';
    $('#lb-next').style.visibility = lb.i < lb.list.length - 1 ? 'visible' : 'hidden';
  }
  function closeLightbox() {
    $('#lightbox').hidden = true;
    document.body.style.overflow = '';
    var btn = lb.list[lb.i];
    if (btn) btn.focus();
  }

  /* -- search -------------------------------------------------------------------- */

  var hits = [];
  var hitIndex = -1;
  var searchTimer = 0;

  function fold(s) { return s.normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase(); }
  function clearHits() {
    $all('mark.hit').forEach(function (m) {
      var parent = m.parentNode;
      parent.replaceChild(document.createTextNode(m.textContent), m);
      parent.normalize();
    });
    hits = [];
    hitIndex = -1;
  }
  function markNode(node, q) {
    var text = node.nodeValue;
    var folded = '';
    var map = [];
    for (var i = 0; i < text.length; i++) {
      var f = fold(text.charAt(i));
      for (var j = 0; j < f.length; j++) { folded += f.charAt(j); map.push(i); }
    }
    var ranges = [];
    var at = folded.indexOf(q);
    while (at !== -1) {
      ranges.push([map[at], map[at + q.length - 1] + 1]);
      at = folded.indexOf(q, at + q.length);
    }
    for (var r = ranges.length - 1; r >= 0; r--) {
      var after = node.splitText(ranges[r][0]);
      after.splitText(ranges[r][1] - ranges[r][0]);
      var mark = document.createElement('mark');
      mark.className = 'hit';
      after.parentNode.replaceChild(mark, after);
      mark.appendChild(after);
    }
  }
  function runSearch(query) {
    clearHits();
    var q = fold(query.trim());
    var count = $('#search-count');
    if (q.length < 2) { count.textContent = ''; return; }
    $all('#chat .text, #chat .doc-name, #chat .call-label, #chat .loc-label, #chat .c-name').forEach(function (el) {
      if (fold(el.textContent).indexOf(q) === -1) return;
      var walker = document.createTreeWalker(el, NodeFilter.SHOW_TEXT);
      var nodes = [];
      while (walker.nextNode()) nodes.push(walker.currentNode);
      nodes.forEach(function (n) { if (fold(n.nodeValue).indexOf(q) !== -1) markNode(n, q); });
    });
    hits = $all('mark.hit');
    if (!hits.length) { count.textContent = t('noResults'); return; }
    gotoHit(hits.length - 1);  // start from the most recent, like WhatsApp
  }
  function gotoHit(i) {
    if (!hits.length) return;
    if (hitIndex >= 0 && hits[hitIndex]) hits[hitIndex].classList.remove('cur');
    hitIndex = (i + hits.length) % hits.length;
    var m = hits[hitIndex];
    m.classList.add('cur');
    m.scrollIntoView({ block: 'center' });
    $('#search-count').textContent = (hitIndex + 1) + ' / ' + hits.length;
  }
  function openSearch() {
    $('#datebar').hidden = true;
    $('#searchbar').hidden = false;
    $('#search-input').focus();
    $('#search-input').select();
  }
  function closeSearch() {
    $('#searchbar').hidden = true;
    clearHits();
    $('#search-count').textContent = '';
  }

  /* -- navigation ------------------------------------------------------------------ */

  function flash(el) {
    var msg = el.closest('.msg') || el;
    msg.classList.remove('flash');
    void msg.offsetWidth;
    msg.classList.add('flash');
  }
  function goToDate(iso) {
    var days = $all('#chat section.day[data-date]');
    var target = null;
    for (var i = 0; i < days.length; i++) {
      if (days[i].getAttribute('data-date') >= iso) { target = days[i]; break; }
    }
    if (!target && days.length) target = days[days.length - 1];
    if (target) target.scrollIntoView({ block: 'start' });
  }
  function toBottom() {
    var n = 0;
    (function step() {
      window.scrollTo(0, document.documentElement.scrollHeight);
      if (++n < 4) requestAnimationFrame(step);
    })();
  }

  var fabTimer = 0;
  function updateFab() {
    fabTimer = 0;
    var y = window.scrollY;
    var max = document.documentElement.scrollHeight - window.innerHeight;
    $('#go-top').classList.toggle('show', y > 800);
    $('#go-bottom').classList.toggle('show', max - y > 800);
  }

  /* -- events ---------------------------------------------------------------------- */

  document.addEventListener('click', function (e) {
    var target = e.target;
    var dl = target.closest('[data-dl]');
    if (dl) {
      var ref = dl.getAttribute('data-dl');
      if (ref.charAt(0) === '#') { e.preventDefault(); download(ref, dl.getAttribute('data-name')); }
      return;
    }
    var playBtn = target.closest('.v-play');
    if (playBtn) {
      var v = playBtn.closest('.voice');
      if (v.classList.contains('playing')) pause(v); else play(v);
      return;
    }
    if (target.closest('.v-speed')) { cycleSpeed(); return; }
    var photo = target.closest('#chat .media.img');
    if (photo) { openLightbox(photo); return; }
    if (target.closest('[data-close]') || target === $('#scrim')) { closePanel(); return; }
  });

  document.addEventListener('input', function (e) {
    if (e.target.classList.contains('v-seek')) seek(e.target.closest('.voice'), e.target.value / 1000);
  });

  $('#btn-search').addEventListener('click', function () { if ($('#searchbar').hidden) openSearch(); else closeSearch(); });
  $('#search-close').addEventListener('click', closeSearch);
  $('#search-prev').addEventListener('click', function () { gotoHit(hitIndex - 1); });
  $('#search-next').addEventListener('click', function () { gotoHit(hitIndex + 1); });
  $('#search-input').addEventListener('input', function (e) {
    clearTimeout(searchTimer);
    var value = e.target.value;
    searchTimer = setTimeout(function () { runSearch(value); }, 250);
  });
  $('#search-input').addEventListener('keydown', function (e) {
    if (e.key === 'Enter') { e.preventDefault(); gotoHit(hitIndex + (e.shiftKey ? 1 : -1)); }
  });

  var dateInput = $('#date-input');
  if (CFG.firstDay) dateInput.min = CFG.firstDay;
  if (CFG.lastDay) dateInput.max = CFG.lastDay;
  $('#btn-date').addEventListener('click', function () {
    $('#searchbar').hidden = true;
    var bar = $('#datebar');
    bar.hidden = !bar.hidden;
    if (!bar.hidden) {
      dateInput.focus();
      if (dateInput.showPicker) { try { dateInput.showPicker(); } catch (e) { /* needs a user gesture */ } }
    }
  });
  $('#date-close').addEventListener('click', function () { $('#datebar').hidden = true; });
  dateInput.addEventListener('change', function () { if (dateInput.value) goToDate(dateInput.value); });

  $('#btn-settings').addEventListener('click', function () { showPanel('#panel-settings'); });
  $('#btn-info').addEventListener('click', function () { showPanel('#panel-info'); });
  $('#go-top').addEventListener('click', function () { window.scrollTo(0, 0); });
  $('#go-bottom').addEventListener('click', toBottom);
  $('#lb-close').addEventListener('click', closeLightbox);
  $('#lb-prev').addEventListener('click', function () { if (lb.i > 0) { lb.i--; showLightbox(); } });
  $('#lb-next').addEventListener('click', function () { if (lb.i < lb.list.length - 1) { lb.i++; showLightbox(); } });
  $('#lightbox').addEventListener('click', function (e) { if (e.target === $('#lightbox')) closeLightbox(); });

  document.addEventListener('keydown', function (e) {
    if (!$('#lightbox').hidden) {
      if (e.key === 'Escape') closeLightbox();
      else if (e.key === 'ArrowLeft') $('#lb-prev').click();
      else if (e.key === 'ArrowRight') $('#lb-next').click();
      return;
    }
    if (e.key === 'Escape') {
      if (openPanel) closePanel();
      else if (!$('#searchbar').hidden) closeSearch();
      else if (!$('#datebar').hidden) $('#datebar').hidden = true;
    }
  });
  window.addEventListener('scroll', function () { if (!fabTimer) fabTimer = requestAnimationFrame(updateFab); }, { passive: true });

  /* -- start ------------------------------------------------------------------------- */

  buildSettings();
  applyLook();
  applyLang();
  applyMe();
  syncSettings();
  showSpeed();

  var hash = location.hash && document.getElementById(location.hash.slice(1));
  if (hash) { hash.scrollIntoView({ block: 'center' }); flash(hash); } else toBottom();

  function ready() {
    $('#loading').classList.add('done');
    startLazyMedia();
    updateFab();
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', ready);
  else ready();
})();
