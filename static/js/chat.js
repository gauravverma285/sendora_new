/* Messages inbox (WhatsApp chat).
 *
 * Talks only to this account's own endpoints (see services/chat_views.py).
 * Everything that comes from a customer (names, message text, filenames) is
 * treated as untrusted and escaped before it touches innerHTML.
 */
(function () {
    'use strict';

    const cfg = window.CHAT_CONFIG;
    const $ = (id) => document.getElementById(id);
    const page = $('chatPage');
    if (!page || !cfg) return;

    const LIST_POLL_MS = 8000;
    const THREAD_POLL_MS = 4000;
    const baseTitle = document.title.replace(/^\(\d+\)\s*/, '');

    const S = {
        tab: 'all', q: '', active: null,
        convs: [], counts: { all: 0, incoming: 0, outgoing: 0 },
        msgs: [], lastId: 0, oldestId: 0, hasMore: false, lastDay: '',
        win: null, sending: false, polling: false,
        openToken: 0, listToken: 0, listSig: '',
        drafts: {}, pinned: true,
    };

    /* ------------------------------------------------------------ helpers */

    const esc = (s) => String(s == null ? '' : s).replace(/[&<>"']/g, (c) => (
        { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]
    ));

    const PALETTE = ['#c8f0da', '#e2d6fb', '#cfe6ff', '#ffe1c6', '#ffd6dc', '#d5f0f4'];
    function colorFor(seed) {
        let h = 0;
        for (const ch of String(seed)) h = (h * 31 + ch.charCodeAt(0)) >>> 0;
        return PALETTE[h % PALETTE.length];
    }

    function initials(name) {
        const src = String(name || '').trim();
        if (!src || /^[+\d\s]+$/.test(src)) return '#';
        const parts = src.split(/\s+/).filter(Boolean);
        const first = Array.from(parts[0])[0] || '#';
        const second = parts.length > 1 ? (Array.from(parts[parts.length - 1])[0] || '') : '';
        return (first + second).toUpperCase();
    }

    function formatPhone(number) {
        const d = String(number || '').replace(/\D/g, '');
        if (d.length === 12 && d.startsWith('91')) return `+91 ${d.slice(2, 7)} ${d.slice(7)}`;
        return d ? `+${d}` : '';
    }

    const sameDay = (a, b) => a.toDateString() === b.toDateString();
    const fmtClock = (d) => d.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' });

    function fmtListTime(iso) {
        if (!iso) return '';
        const d = new Date(iso), now = new Date();
        if (sameDay(d, now)) return fmtClock(d);
        const y = new Date(now); y.setDate(now.getDate() - 1);
        if (sameDay(d, y)) return 'Yesterday';
        return d.toLocaleDateString([], d.getFullYear() === now.getFullYear()
            ? { month: 'short', day: 'numeric' } : { month: 'short', day: 'numeric', year: 'numeric' });
    }

    function fmtDay(iso) {
        const d = new Date(iso), now = new Date();
        if (sameDay(d, now)) return 'Today';
        const y = new Date(now); y.setDate(now.getDate() - 1);
        if (sameDay(d, y)) return 'Yesterday';
        return d.toLocaleDateString([], { weekday: 'short', month: 'short', day: 'numeric', year: 'numeric' });
    }

    const fmtDate = (iso) => new Date(iso).toLocaleDateString([], { month: 'short', day: 'numeric', year: 'numeric' });

    // Escape first, then turn plain http(s) URLs into links. The URL text is
    // already escaped (no quotes/angle brackets can survive), and only
    // http/https is matched — no javascript: links.
    function linkify(text) {
        return esc(text).replace(/(https?:\/\/[^\s<]+)/g, (m) => {
            const trail = (m.match(/[.,;:!?)\]]+$/) || [''])[0];
            const url = trail ? m.slice(0, -trail.length) : m;
            return `<a href="${url}" target="_blank" rel="noopener noreferrer">${url}</a>${trail}`;
        });
    }

    const input = $('composerInput');
    function autoGrow() { input.style.height = 'auto'; input.style.height = Math.min(input.scrollHeight, 140) + 'px'; }

    let toastTimer;
    function toast(msg, isError) {
        const t = $('chatToast');
        t.textContent = msg;
        t.className = 'chat-toast' + (isError ? ' is-error' : '');
        t.hidden = false;
        clearTimeout(toastTimer);
        toastTimer = setTimeout(() => { t.hidden = true; }, 3800);
    }

    async function api(url, opts) {
        const o = opts || {};
        const init = { method: o.method || 'GET', credentials: 'same-origin', headers: { 'X-Requested-With': 'XMLHttpRequest' } };
        if (init.method !== 'GET') {
            init.headers['Content-Type'] = 'application/json';
            init.headers['X-CSRFToken'] = cfg.csrf;
            init.body = JSON.stringify(o.body || {});
        }
        let res;
        try { res = await fetch(url, init); } catch (e) { return { ok: false, status: 0, data: {} }; }
        if (res.redirected && /login/.test(res.url)) { window.location.href = res.url; return { ok: false, status: 401, data: {} }; }
        let data = {};
        try { data = await res.json(); } catch (e) { /* non-JSON */ }
        return { ok: res.ok, status: res.status, data };
    }

    /* ------------------------------------------------- conversation list */

    function convHTML(c) {
        const active = c.number === S.active ? ' is-active' : '';
        const unread = c.unread > 0 ? ' is-unread' : '';
        const badge = c.direction === 'out'
            ? '<span class="chat-badge chat-badge--out"><i class="mdi mdi-send"></i> Outgoing</span>'
            : '<span class="chat-badge chat-badge--in"><i class="mdi mdi-whatsapp"></i> Incoming</span>';
        const unreadBadge = c.unread > 0 ? `<span class="chat-unread-badge">${c.unread > 99 ? '99+' : c.unread}</span>` : '';
        return `<button type="button" class="chat-conv${active}${unread}" data-number="${esc(c.number)}">
            <span class="chat-avatar" style="background:${colorFor(c.number)}">${esc(initials(c.name))}</span>
            <span class="chat-conv__body">
                <span class="chat-conv__top"><strong>${esc(c.name)}</strong><time>${esc(fmtListTime(c.last_at))}</time></span>
                <span class="chat-conv__num" style="display:block">${esc(formatPhone(c.number))}</span>
                <span class="chat-conv__bottom">
                    <span class="chat-conv__preview">${esc(c.preview)}</span>
                    <span class="chat-conv__tags">${unreadBadge}${badge}</span>
                </span>
            </span>
        </button>`;
    }

    function renderList() {
        const sig = JSON.stringify([S.convs, S.active, S.q, S.tab]);
        if (sig === S.listSig) return;
        S.listSig = sig;
        const list = $('convList');
        const top = list.scrollTop;
        if (!S.convs.length) {
            list.innerHTML = `<div class="chat-placeholder">${S.q
                ? 'No conversations match your search.'
                : 'No conversations yet. Messages your customers send to your WhatsApp number will show up here.'}</div>`;
            return;
        }
        list.innerHTML = S.convs.map(convHTML).join('');
        list.scrollTop = top;
    }

    async function loadConversations() {
        const token = ++S.listToken;
        const r = await api(`${cfg.urls.conversations}?tab=${encodeURIComponent(S.tab)}&q=${encodeURIComponent(S.q)}`);
        if (token !== S.listToken || !r.ok) return null;
        S.convs = r.data.conversations || [];
        S.counts = r.data.counts || S.counts;
        $('countAll').textContent = S.counts.all;
        $('countIncoming').textContent = S.counts.incoming;
        $('countOutgoing').textContent = S.counts.outgoing;
        $('convCount').textContent = S.counts.all;
        const unread = r.data.unread_total || 0;
        document.title = unread > 0 ? `(${unread}) ${baseTitle}` : baseTitle;
        renderList();
        return S.convs;
    }

    /* ----------------------------------------------------------- messages */

    function tickHTML(status, error) {
        if (status === 'read') return '<i class="mdi mdi-check-all is-read" title="Read"></i>';
        if (status === 'delivered') return '<i class="mdi mdi-check-all" title="Delivered"></i>';
        if (status === 'failed') return `<i class="mdi mdi-alert-circle-outline is-failed" title="${esc(error || 'Not delivered')}"></i>`;
        return '<i class="mdi mdi-check" title="Sent"></i>';
    }

    function bubbleHTML(m) {
        const out = m.direction === 'out';
        let inner = '';
        if (m.media_url) {
            const u = esc(m.media_url);
            if (m.type === 'image' || m.type === 'sticker') {
                inner += `<a href="${u}" target="_blank" rel="noopener"><img class="chat-media-img" src="${u}" loading="lazy" alt="Photo" data-media></a>`;
            } else if (m.type === 'video') {
                inner += `<video class="chat-media-video" controls preload="metadata" src="${u}"></video>`;
            } else if (m.type === 'audio') {
                inner += `<audio controls preload="none" src="${u}"></audio>`;
            } else {
                inner += `<a class="chat-doc" href="${u}" target="_blank" rel="noopener"><i class="mdi mdi-file-document-outline"></i><span>${esc(m.filename || 'Document')}</span></a>`;
            }
        }
        if (m.body) inner += `<div class="chat-text">${linkify(m.body)}</div>`;
        else if (!m.media_url) inner += `<div class="chat-text muted">[${esc(m.type)} message]</div>`;

        const fail = out && m.status === 'failed'
            ? `<div class="chat-fail">Not delivered${m.error ? ': ' + esc(m.error) : ''}</div>` : '';
        const meta = `<div class="chat-meta"><time>${esc(fmtClock(new Date(m.ts)))}</time>${out ? `<span class="chat-tick">${tickHTML(m.status, m.error)}</span>` : ''}</div>`;
        return `<div class="chat-msg ${out ? 'is-out' : 'is-in'}" data-mid="${m.id}" data-status="${esc(m.status)}">
            <div class="chat-bubble">${inner}${fail}${meta}</div></div>`;
    }

    function dayHTML(iso) { return `<div class="chat-day">${esc(fmtDay(iso))}</div>`; }

    function messagesHTML(list) {
        let html = '';
        let day = '';
        for (const m of list) {
            const d = new Date(m.ts).toDateString();
            if (d !== day) { html += dayHTML(m.ts); day = d; }
            html += bubbleHTML(m);
        }
        S.lastDay = day;
        return html;
    }

    const nearBottom = (box) => box.scrollHeight - box.scrollTop - box.clientHeight < 140;

    function renderMessages(keepScrollFromBottom) {
        const box = $('messages');
        const prevHeight = box.scrollHeight, prevTop = box.scrollTop;
        const more = S.hasMore ? '<button type="button" class="chat-more" data-action="older">Load earlier messages</button>' : '';
        box.innerHTML = more + (S.msgs.length ? messagesHTML(S.msgs) : '<div class="chat-placeholder">No messages yet.</div>');
        if (keepScrollFromBottom) box.scrollTop = prevTop + (box.scrollHeight - prevHeight);
        else scrollToBottom();
        S.oldestId = S.msgs.length ? S.msgs[0].id : 0;
        S.lastId = S.msgs.length ? Math.max(...S.msgs.map((m) => m.id)) : 0;
    }

    function appendMessages(list, forceScroll) {
        const box = $('messages');
        const stick = forceScroll || nearBottom(box);
        let html = '';
        for (const m of list) {
            if (box.querySelector(`[data-mid="${m.id}"]`)) continue;
            const d = new Date(m.ts).toDateString();
            if (d !== S.lastDay) { html += dayHTML(m.ts); S.lastDay = d; }
            html += bubbleHTML(m);
            S.msgs.push(m);
            S.lastId = Math.max(S.lastId, m.id);
        }
        if (!html) return;
        const placeholder = box.querySelector('.chat-placeholder');
        if (placeholder) placeholder.remove();
        box.insertAdjacentHTML('beforeend', html);
        if (stick) scrollToBottom();
    }

    function applyStatuses(list) {
        const box = $('messages');
        for (const s of list) {
            const el = box.querySelector(`[data-mid="${s.id}"]`);
            if (!el || el.dataset.status === s.status) continue;
            el.dataset.status = s.status;
            const tick = el.querySelector('.chat-tick');
            if (tick) tick.innerHTML = tickHTML(s.status, s.error);
            const bubble = el.querySelector('.chat-bubble');
            const existing = bubble.querySelector('.chat-fail');
            if (s.status === 'failed' && !existing) {
                bubble.querySelector('.chat-meta').insertAdjacentHTML(
                    'beforebegin', `<div class="chat-fail">Not delivered${s.error ? ': ' + esc(s.error) : ''}</div>`);
            } else if (s.status !== 'failed' && existing) {
                existing.remove();
            }
        }
    }

    // Media that can't be loaded (expired on Meta's side, or removed).
    $('messages').addEventListener('error', (e) => {
        if (e.target && e.target.matches && e.target.matches('img[data-media]')) {
            const a = e.target.closest('a');
            (a || e.target).outerHTML = '<div class="chat-text muted">Media is no longer available</div>';
            keepPinned();
        }
    }, true);

    // Photos/videos finish loading after we've scrolled to the bottom and push
    // the layout down; stay glued to the newest message unless the user has
    // scrolled up to read history.
    function scrollToBottom() {
        const box = $('messages');
        S.pinned = true;
        S.ignoreScroll = true;   // this jump isn't the user scrolling away
        box.scrollTop = box.scrollHeight;
        setTimeout(() => { S.ignoreScroll = false; }, 60);
    }
    function keepPinned() { if (S.pinned) scrollToBottom(); }
    $('messages').addEventListener('load', keepPinned, true);
    $('messages').addEventListener('loadedmetadata', keepPinned, true);
    $('messages').addEventListener('scroll', () => {
        if (S.ignoreScroll) return;
        S.pinned = nearBottom($('messages'));
    });
    // The message area itself can change height (composer grows, warning
    // banner appears, window resized) — stay on the newest message.
    if ('ResizeObserver' in window) new ResizeObserver(keepPinned).observe($('messages'));

    /* ------------------------------------------------------- thread header */

    function renderHead(conv) {
        $('thName').textContent = conv.name;
        $('thNumber').textContent = formatPhone(conv.number);
        const av = $('thAvatar');
        av.textContent = initials(conv.name);
        av.style.background = colorFor(conv.number);
    }

    function fmtRemaining(iso) {
        const ms = new Date(iso) - new Date();
        if (ms <= 0) return '';
        const h = Math.floor(ms / 3600000), m = Math.floor((ms % 3600000) / 60000);
        return h > 0 ? `${h}h ${m}m left` : `${Math.max(m, 1)}m left`;
    }

    function applyWindow(win) {
        S.win = win || { open: false };
        const open = !!S.win.open && cfg.connected;
        const label = $('thWindow');
        if (S.win.open) {
            label.className = 'chat-window is-open';
            label.textContent = 'Reply window open' + (S.win.expires_at ? ` · ${fmtRemaining(S.win.expires_at)}` : '');
        } else {
            label.className = 'chat-window is-closed';
            label.textContent = 'Reply window closed';
        }
        const input = $('composerInput');
        input.disabled = !open;
        $('sendBtn').disabled = !open || S.sending;
        input.placeholder = !cfg.connected ? 'Connect WhatsApp to reply'
            : (open ? 'Type a message...' : 'Replies are locked — the 24-hour window is closed');
        $('windowWarning').hidden = !cfg.connected || open;
    }

    /* --------------------------------------------------------- side panel */

    function renderSide(d) {
        const c = d.conversation, ct = d.contact, sm = d.summary;
        S.threadSaved = !!ct.saved;
        const tags = (ct.tags || []).map((t) => `<span class="chat-chip">${esc(t.name)}</span>`).join('');
        const chips = ct.saved
            ? (tags || '<span class="chat-chip chat-chip--muted">No tags</span>')
            : '<span class="chat-chip chat-chip--muted">Not in your contacts</span>';

        const info = [];
        if (ct.email) info.push(['mdi-email-outline', 'Email', ct.email]);
        if (ct.age !== null && ct.age !== undefined) info.push(['mdi-cake-variant-outline', 'Age', ct.age]);
        if (ct.saved && c.profile_name && c.profile_name !== c.name) info.push(['mdi-whatsapp', 'WhatsApp name', c.profile_name]);
        info.push(['mdi-calendar-blank-outline', 'First message', fmtDate(c.first_message_at)]);
        const infoHTML = info.map(([icon, label, value]) => `<div class="chat-info"><i class="mdi ${icon}"></i>
            <div><small>${esc(label)}</small><span>${esc(value)}</span></div></div>`).join('');

        const assigned = new Set((ct.tags || []).map((t) => t.id));
        const free = (d.available_tags || []).filter((t) => !assigned.has(t.id));
        const tagMenu = free.length
            ? free.map((t) => `<button type="button" data-action="tag-pick" data-tag="${t.id}">${esc(t.name)}</button>`).join('')
            : `<a href="${esc(cfg.urls.tags)}">${(d.available_tags || []).length ? 'All tags already added' : 'Create a tag first'}</a>`;

        const contactBtn = ct.saved
            ? `<a class="chat-btn chat-btn--ghost" href="${esc(cfg.urls.contacts)}"><i class="mdi mdi-account-outline"></i> View Contact</a>`
            : '<button type="button" class="chat-btn chat-btn--ghost" data-action="save-contact"><i class="mdi mdi-account-plus-outline"></i> Save Contact</button>';

        const recent = (d.recent || []).map((r) => `<div class="chat-activity">
            <i class="mdi ${r.direction === 'in' ? 'mdi-whatsapp is-in' : 'mdi-send is-out'}"></i>
            <div><strong>${esc(r.event)}<time>${esc(fmtClock(new Date(r.ts)))}</time></strong><p>${esc(r.text)}</p></div></div>`).join('')
            || '<div class="chat-placeholder" style="padding:6px 0">No activity yet.</div>';

        $('sideBody').innerHTML = `
            <div class="chat-sec">
                <h4>Contact Details</h4>
                <div class="chat-profile">
                    <span class="chat-avatar" style="background:${colorFor(c.number)}">${esc(initials(c.name))}</span>
                    <div><strong>${esc(c.name)}</strong><span>${esc(formatPhone(c.number))}</span></div>
                </div>
                <div class="chat-chips">${chips}</div>
                ${infoHTML}
            </div>
            <div class="chat-sec">
                <h4>Message Summary</h4>
                <div class="chat-stats">
                    <div class="chat-stat"><b>${sm.total}</b><small>Total</small></div>
                    <div class="chat-stat"><b>${sm.incoming}</b><small>Incoming</small></div>
                    <div class="chat-stat"><b>${sm.outgoing}</b><small>Outgoing</small></div>
                </div>
            </div>
            <div class="chat-sec">
                <h4>Quick Actions</h4>
                <button type="button" class="chat-btn chat-btn--primary" data-action="focus-composer"><i class="mdi mdi-send"></i> Send Message</button>
                <div class="chat-btn-row">
                    <button type="button" class="chat-btn chat-btn--ghost" data-action="tag-toggle"><i class="mdi mdi-tag-outline"></i> Add Tag</button>
                    ${contactBtn}
                    <div class="chat-tagmenu" id="tagMenu" hidden>${tagMenu}</div>
                </div>
            </div>
            <div class="chat-sec">
                <h4>Recent Activity</h4>
                ${recent}
            </div>`;
    }

    async function refreshSide() {
        if (!S.active) return;
        const token = S.openToken;
        const r = await api(`${cfg.urls.thread}?number=${S.active}`);
        if (token !== S.openToken || !r.ok) return;
        renderHead(r.data.conversation);
        renderSide(r.data);
        loadConversations();
    }

    /* ------------------------------------------------------------ open chat */

    function setDrawer(open) {
        $('sidePanel').classList.toggle('is-open', open);
        $('chatScrim').classList.toggle('is-open', open);
    }

    // Each conversation keeps its own unsent draft, so text typed for one
    // customer can never end up being sent to another.
    function saveDraft() { if (S.active) S.drafts[S.active] = input.value; }

    async function openConversation(number) {
        saveDraft();
        S.active = number;
        const token = ++S.openToken;
        page.classList.add('is-thread-open');
        setDrawer(false);
        $('threadEmpty').hidden = true;
        $('threadInner').hidden = false;
        $('messages').innerHTML = '<div class="chat-placeholder">Loading…</div>';
        $('composerError').hidden = true;
        S.listSig = '';
        renderList();

        const r = await api(`${cfg.urls.thread}?number=${encodeURIComponent(number)}&mark_read=1`);
        if (token !== S.openToken) return;
        if (!r.ok) {
            $('messages').innerHTML = `<div class="chat-placeholder">${esc(r.data.error || 'Could not load this conversation.')}</div>`;
            return;
        }
        S.msgs = r.data.messages || [];
        S.hasMore = !!r.data.has_more;
        renderHead(r.data.conversation);
        renderMessages(false);
        renderSide(r.data);
        applyWindow(r.data.window);
        input.value = S.drafts[number] || '';
        autoGrow();
        loadConversations();
        if (window.history && history.replaceState) history.replaceState(null, '', `?number=${encodeURIComponent(number)}`);
        if (window.innerWidth >= 768) $('composerInput').focus({ preventScroll: true });
    }

    function closeConversation() {
        saveDraft();
        S.active = null;
        S.openToken++;
        page.classList.remove('is-thread-open');
        setDrawer(false);
        $('threadInner').hidden = true;
        $('threadEmpty').hidden = false;
        S.listSig = '';
        renderList();
        if (window.history && history.replaceState) history.replaceState(null, '', window.location.pathname);
    }

    async function loadOlder(btn) {
        if (!S.active || !S.oldestId) return;
        btn.disabled = true;
        const r = await api(`${cfg.urls.thread}?number=${encodeURIComponent(S.active)}&before=${S.oldestId}`);
        if (!r.ok) { btn.disabled = false; return; }
        S.msgs = (r.data.messages || []).concat(S.msgs);
        S.hasMore = !!r.data.has_more;
        renderMessages(true);
    }

    async function pollThread() {
        if (!S.active || document.hidden || S.polling) return;
        S.polling = true;
        try {
            const token = S.openToken;
            const r = await api(`${cfg.urls.thread}?number=${encodeURIComponent(S.active)}&after=${S.lastId}&mark_read=1`);
            if (token !== S.openToken || !r.ok) return;
            if ((r.data.messages || []).length) { appendMessages(r.data.messages, false); loadConversations(); }
            applyStatuses(r.data.statuses || []);
            applyWindow(r.data.window);
        } finally {
            S.polling = false;
        }
    }

    /* ------------------------------------------------------------ composer */

    input.addEventListener('input', autoGrow);
    input.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) { e.preventDefault(); $('composer').requestSubmit(); }
    });

    $('composer').addEventListener('submit', async (e) => {
        e.preventDefault();
        const text = input.value.trim();
        if (!text || S.sending || !S.active) return;
        S.sending = true;
        $('sendBtn').disabled = true;
        $('composerError').hidden = true;

        const r = await api(cfg.urls.send, { method: 'POST', body: { number: S.active, text } });
        S.sending = false;
        if (r.ok && r.data.ok) {
            input.value = '';
            delete S.drafts[S.active];
            autoGrow();
            if (r.data.message) appendMessages([r.data.message], true);
            loadConversations();
        } else {
            const err = $('composerError');
            err.textContent = (r.data && r.data.error) || 'Could not send the message. Please try again.';
            err.hidden = false;
        }
        applyWindow(r.data && r.data.window_closed ? { open: false } : S.win);
        input.focus();
    });

    /* -------------------------------------------------------------- events */

    $('convList').addEventListener('click', (e) => {
        const b = e.target.closest('.chat-conv');
        if (b) openConversation(b.dataset.number);
    });

    document.querySelectorAll('.chat-tab').forEach((tab) => tab.addEventListener('click', () => {
        document.querySelectorAll('.chat-tab').forEach((t) => t.classList.remove('is-active'));
        tab.classList.add('is-active');
        S.tab = tab.dataset.tab;
        loadConversations();
    }));

    let searchTimer;
    $('convSearch').addEventListener('input', (e) => {
        clearTimeout(searchTimer);
        const v = e.target.value.trim();
        searchTimer = setTimeout(() => { S.q = v; loadConversations(); }, 300);
    });

    $('messages').addEventListener('click', (e) => {
        const btn = e.target.closest('[data-action="older"]');
        if (btn) loadOlder(btn);
    });

    $('backBtn').addEventListener('click', closeConversation);
    $('detailsBtn').addEventListener('click', () => setDrawer(true));
    $('sideClose').addEventListener('click', () => setDrawer(false));
    $('chatScrim').addEventListener('click', () => setDrawer(false));
    document.addEventListener('keydown', (e) => { if (e.key === 'Escape') setDrawer(false); });

    $('sideBody').addEventListener('click', async (e) => {
        const el = e.target.closest('[data-action]');
        if (!el || !S.active) return;
        const action = el.dataset.action;

        if (action === 'focus-composer') {
            setDrawer(false);
            if (!input.disabled) input.focus();
            else toast('The 24-hour reply window is closed — use a template campaign.', true);
        } else if (action === 'tag-toggle') {
            const menu = $('tagMenu');
            if (!S.threadSaved) { toast('Save this contact first, then add tags.', true); return; }
            menu.hidden = !menu.hidden;
        } else if (action === 'tag-pick') {
            const r = await api(cfg.urls.addTag, { method: 'POST', body: { number: S.active, tag_id: Number(el.dataset.tag) } });
            if (r.ok) { toast('Tag added'); refreshSide(); } else { toast(r.data.error || 'Could not add the tag.', true); }
        } else if (action === 'save-contact') {
            const r = await api(cfg.urls.saveContact, { method: 'POST', body: { number: S.active } });
            if (r.ok) { toast('Saved to your contacts'); refreshSide(); } else { toast(r.data.error || 'Could not save the contact.', true); }
        }
    });
    document.addEventListener('click', (e) => {
        const menu = $('tagMenu');
        if (menu && !menu.hidden && !e.target.closest('.chat-btn-row')) menu.hidden = true;
    });

    /* ---------------------------------------------------------------- boot */

    setInterval(() => { if (!document.hidden) loadConversations(); }, LIST_POLL_MS);
    setInterval(pollThread, THREAD_POLL_MS);
    document.addEventListener('visibilitychange', () => { if (!document.hidden) { loadConversations(); pollThread(); } });

    (async function boot() {
        const convs = await loadConversations();
        const target = cfg.initialNumber || (window.innerWidth >= 768 && convs && convs[0] ? convs[0].number : '');
        if (target) openConversation(target);
    })();
})();
