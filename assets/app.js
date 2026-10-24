/* Terra Motus — interface script.
   The rows are already in the page (build.py renders them from data/events.json); this script only
   searches, filters and sorts them, and keeps that state in the address bar (#q=…&cat=…&sort=…). */
(function () {
  'use strict';
  const tbody = document.getElementById('rows');
  if (!tbody) return;
  const rows = Array.from(tbody.rows);
  if (!rows.length) return;
  const q = document.getElementById('f-q');
  const chips = Array.from(document.querySelectorAll('.f-cats .chip'));
  const reset = document.getElementById('f-reset');
  const status = document.getElementById('status');
  const empty = document.getElementById('empty');
  const heads = Array.from(document.querySelectorAll('thead th[data-k]'));
  const baseStatus = status.textContent;
  const total = rows.length;

  // Category ids come from the filter buttons (title -> id); everything else from the cell text.
  const catId = {};
  chips.forEach(c => { if (c.dataset.c) catId[c.firstChild.textContent.trim()] = c.dataset.c; });
  rows.forEach((r, i) => {
    r._i = i; // build order is newest first, so the index is the date order
    r._c = catId[r.cells[1].textContent.trim()] || '';
    r._n = parseInt(r.cells[4].textContent, 10) || 0;
    const m = parseFloat(r.cells[3].textContent.replace(/,/g, ''));
    r._m = isNaN(m) ? -1 : m;
    r._t = r.cells[2].textContent.trim();
    r._k = (r._t + ' ' + r.cells[1].textContent + ' ' + r.cells[2].querySelector('a').href).toLowerCase();
  });

  const DEFAULT_SORT = 'd:desc';
  let state = { q: '', cat: '', sort: DEFAULT_SORT };

  function readHash() {
    const p = new URLSearchParams(location.hash.replace(/^#/, ''));
    const cat = p.get('cat') || '';
    const sort = p.get('sort') || DEFAULT_SORT;
    state = {
      q: p.get('q') || '',
      cat: chips.some(c => c.dataset.c === cat && !c.disabled) ? cat : '',
      sort: heads.some(h => sort.split(':')[0] === h.dataset.k) && /:(asc|desc)$/.test(sort) ? sort : DEFAULT_SORT
    };
    q.value = state.q;
  }
  function writeHash() {
    const p = new URLSearchParams();
    if (state.q) p.set('q', state.q);
    if (state.cat) p.set('cat', state.cat);
    if (state.sort !== DEFAULT_SORT) p.set('sort', state.sort);
    const h = p.toString();
    if (!h && !/=/.test(location.hash)) return; // leave a plain section anchor such as #events alone
    history.replaceState(null, '', h ? '#' + h : location.pathname + location.search);
  }

  function apply() {
    const s = state.q.trim().toLowerCase();
    const [k, dir] = state.sort.split(':');
    const m = dir === 'asc' ? 1 : -1;
    const shown = rows.filter(r => (!state.cat || r._c === state.cat) && (!s || r._k.includes(s)));
    shown.sort((a, b) => {
      let av, bv;
      if (k === 'd') { av = b._i; bv = a._i; }
      else if (k === 'c') { av = a._c; bv = b._c; }
      else if (k === 't') { av = a._t.toLowerCase(); bv = b._t.toLowerCase(); }
      else if (k === 'm') { av = a._m; bv = b._m; }
      else { av = a._n; bv = b._n; }
      if (av < bv) return -m;
      if (av > bv) return m;
      return a._i - b._i; // ties: newest first
    });
    const frag = document.createDocumentFragment();
    rows.forEach(r => { r.hidden = true; });
    shown.forEach(r => { r.hidden = false; frag.appendChild(r); });
    tbody.appendChild(frag);
    rows.filter(r => r.hidden).forEach(r => tbody.appendChild(r));

    chips.forEach(c => c.setAttribute('aria-pressed', String(c.dataset.c === state.cat)));
    heads.forEach(h => { if (h.dataset.k === k) h.setAttribute('aria-sort', dir === 'asc' ? 'ascending' : 'descending'); else h.removeAttribute('aria-sort'); });
    empty.hidden = shown.length > 0;
    const filtered = state.cat || s;
    const catName = state.cat ? chips.find(c => c.dataset.c === state.cat).firstChild.textContent.trim() : '';
    status.textContent = filtered
      ? `Showing ${shown.length.toLocaleString()} of ${total.toLocaleString()} events` + (catName ? ` in ${catName}` : '') + (s ? ` matching “${state.q.trim()}”` : '') + '.'
      : baseStatus;
    writeHash();
  }

  q.addEventListener('input', () => { state.q = q.value; apply(); });
  chips.forEach(c => c.addEventListener('click', () => { state.cat = c.dataset.c === state.cat ? '' : c.dataset.c; apply(); }));
  heads.forEach(h => h.querySelector('button').addEventListener('click', () => {
    const k = h.dataset.k;
    const [ck, cd] = state.sort.split(':');
    const def = (k === 'd' || k === 'm' || k === 'n') ? 'desc' : 'asc';
    state.sort = k + ':' + (ck === k ? (cd === 'asc' ? 'desc' : 'asc') : def);
    apply();
  }));
  reset.addEventListener('click', () => { state = { q: '', cat: '', sort: DEFAULT_SORT }; q.value = ''; apply(); q.focus(); });
  window.addEventListener('hashchange', () => { readHash(); apply(); });

  const nav = document.getElementById('nav');
  const onScroll = () => nav.classList.toggle('scrolled', window.scrollY > 20);
  window.addEventListener('scroll', onScroll, { passive: true }); onScroll();

  readHash();
  if (state.q || state.cat || state.sort !== DEFAULT_SORT) apply();
})();
