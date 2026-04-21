/**
 * chat.js — 聊天视图控制器（SSE 流式 + thread_id 多轮 + HITL）
 */
window.BurgerGame = window.BurgerGame || {};

(function () {
    'use strict';

    // =========================================================
    //  状态
    // =========================================================
    let currentBurgerJSON = null;
    let threadId = null;
    let capabilities = {};
    let chatHistory = [];
    let isWaiting = false;
    let pendingApproval = null;      // {hint, tool_calls}

    // DOM 缓存
    let els = {};

    function cacheElements() {
        els = {
            buildView: document.getElementById('build-view'),
            chatView: document.getElementById('chat-view'),
            chatMessages: document.getElementById('chat-messages'),
            chatInput: document.getElementById('chat-input'),
            chatSendBtn: document.getElementById('chat-send-btn'),
            chatBackBtn: document.getElementById('chat-back-btn'),
            chatDownloadBtn: document.getElementById('chat-download-btn'),
            chatConfigSummary: document.getElementById('chat-config-summary'),
            chatStatus: document.getElementById('chat-status'),
        };
    }

    // =========================================================
    //  视图切换
    // =========================================================
    function switchToChatView(burgerJSON) {
        currentBurgerJSON = burgerJSON;
        chatHistory = [];
        threadId = null;
        capabilities = {};
        pendingApproval = null;

        if (!els.buildView) cacheElements();

        renderConfigSummary(burgerJSON);
        els.chatMessages.innerHTML = '';

        appendMessage('ai', `🍔 你好！我是根据你搭建的汉堡 Agent 生成的助手。\n\n**配置信息**：\n- 模型：\`${burgerJSON.meat_model || 'qwen-plus'}\`\n- 配方：${burgerJSON.agent_label || '-'}\n- 工具：${(burgerJSON.vegetables || []).length > 0 ? burgerJSON.vegetables.join(', ') : '无'}\n\n请输入消息开始对话吧！`);

        els.buildView.classList.add('view-hidden');
        els.chatView.classList.add('view-visible');

        setTimeout(() => { els.chatInput.focus(); }, 400);

        buildAgentOnServer(burgerJSON);
    }

    function switchToBuildView() {
        if (!els.buildView) cacheElements();
        els.chatView.classList.remove('view-visible');
        els.buildView.classList.remove('view-hidden');
    }

    function renderConfigSummary(json) {
        const model = json.meat_model || 'qwen-plus';
        const toolCount = (json.vegetables || []).length;
        const agentLabel = json.agent_label || '传统 LLM 对话';
        const agentEmoji = {
            tool_agent: '🤖',
            default_tool_agent: '🔧',
            guided_chat: '🎯',
            basic_chat: '💬',
            memory_chat: '🧠',
            approval_tool_agent: '🛡️',
        }[json.agent_type] || '🍔';

        const capChips = [];
        if (capabilities.checkpoint) capChips.push('💾 多轮');
        if (capabilities.streaming) capChips.push('🌊 流式');
        if (capabilities.hitl) capChips.push('🛡️ 审批');

        els.chatConfigSummary.innerHTML = `
            <span class="config-chip" style="background:rgba(108,92,231,0.15);border-color:rgba(108,92,231,0.35);color:#a29bfe;">${agentEmoji} ${agentLabel}</span>
            <span class="config-chip">🥩 ${model}</span>
            ${toolCount > 0 ? `<span class="config-chip">🥬 ${toolCount} 工具</span>` : ''}
            ${capChips.map((c) => `<span class="config-chip" style="background:rgba(46,204,113,0.12);border-color:rgba(46,204,113,0.3);color:#2ecc71;">${c}</span>`).join('')}
        `;
    }

    // =========================================================
    //  构建后端 Agent
    // =========================================================
    async function buildAgentOnServer(json) {
        setStatus('connecting');
        try {
            const resp = await fetch('/api/build', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(json),
            });
            if (resp.ok) {
                const data = await resp.json();
                threadId = data.thread_id || null;
                capabilities = data.capabilities || {};
                // 重新渲染以显示能力 chip
                renderConfigSummary(currentBurgerJSON);
                setStatus('connected');
            } else {
                setStatus('error');
                appendMessage('system', '⚠️ 后端构建失败，请检查服务器是否运行。');
            }
        } catch (err) {
            setStatus('error');
            appendMessage('system', '⚠️ 无法连接到后端服务器 (localhost:8000)。请确保已启动 `python server.py`。\n\n你仍然可以下载后端项目，在本地配置后运行。');
        }
    }

    // =========================================================
    //  发送消息（SSE 流式 + 多轮 + 节点高亮）
    // =========================================================
    async function sendMessage() {
        if (isWaiting) return;
        if (!threadId) {
            BurgerGame.showToast('会话未就绪，请稍候', 'error');
            return;
        }

        const text = els.chatInput.value.trim();
        if (!text) return;

        appendMessage('user', text);
        els.chatInput.value = '';
        chatHistory.push({ role: 'user', content: text });

        const thinkingId = appendMessage('ai', '', true);
        isWaiting = true;
        setInputEnabled(false);

        await streamChat(thinkingId, { message: text });
    }

    /**
     * 通用 SSE 消费器
     * @param {string} thinkingMsgId - 要被替换的 "thinking" 气泡 id
     * @param {object} payload - 传给 /api/chat/stream 的 body（resume 时可不含 message）
     * @param {string} url - 接口路径
     */
    async function streamChat(thinkingMsgId, payload, url) {
        url = url || '/api/chat/stream';
        payload = { thread_id: threadId, ...payload };

        const nodeEvents = [];
        let finalText = '';
        let streamedText = '';      // 🌊 LLM token 流累积
        let interrupted = false;

        try {
            const resp = await fetch(url, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload),
            });

            if (!resp.ok || !resp.body) {
                const err = await resp.json().catch(() => ({}));
                replaceThinking(thinkingMsgId, `❌ ${err.detail || resp.statusText}`);
                finishTurn();
                return;
            }

            const reader = resp.body.getReader();
            const decoder = new TextDecoder('utf-8');
            let buffer = '';

            while (true) {
                const { value, done } = await reader.read();
                if (done) break;
                buffer += decoder.decode(value, { stream: true });

                // 解析 SSE: 按空行分块
                let idx;
                while ((idx = buffer.indexOf('\n\n')) !== -1) {
                    const raw = buffer.slice(0, idx);
                    buffer = buffer.slice(idx + 2);

                    const lines = raw.split('\n');
                    let dataStr = '';
                    for (const line of lines) {
                        if (line.startsWith('data: ')) {
                            dataStr += line.slice(6);
                        }
                    }
                    if (!dataStr) continue;

                    let ev;
                    try { ev = JSON.parse(dataStr); } catch (e) { continue; }

                    handleStreamEvent(ev, {
                        onNode: (name, status) => {
                            nodeEvents.push({ name, status });
                            if (BurgerGame.Canvas && BurgerGame.Canvas.highlightLayer) {
                                BurgerGame.Canvas.highlightLayer(name, status);
                            }
                            // 有 streaming 文本时，trace 合并显示在气泡底部
                            if (!streamedText) {
                                updateThinkingTrace(thinkingMsgId, nodeEvents);
                            } else {
                                updateStreamingBubble(thinkingMsgId, streamedText, nodeEvents);
                            }
                        },
                        onTool: (name, status, extra) => {
                            nodeEvents.push({ kind: 'tool', name, status, ...extra });
                            if (!streamedText) {
                                updateThinkingTrace(thinkingMsgId, nodeEvents);
                            } else {
                                updateStreamingBubble(thinkingMsgId, streamedText, nodeEvents);
                            }
                        },
                        onToken: (text) => {
                            streamedText += text;
                            updateStreamingBubble(thinkingMsgId, streamedText, nodeEvents);
                        },
                        onFinal: (reply) => {
                            finalText = reply || streamedText || '(空回复)';
                        },
                        onInterrupt: (pending) => {
                            interrupted = true;
                            pendingApproval = pending;
                        },
                        onError: (detail) => {
                            replaceThinking(thinkingMsgId, `❌ ${detail}`);
                        },
                    });
                }
            }

            if (interrupted) {
                replaceThinking(
                    thinkingMsgId,
                    renderApprovalHTML(pendingApproval),
                    /*raw=*/true
                );
                bindApprovalButtons(thinkingMsgId);
            } else if (finalText) {
                replaceThinking(thinkingMsgId, finalText);
                chatHistory.push({ role: 'ai', content: finalText });
            } else if (streamedText) {
                // 没有收到 final 但有流式文本（例如只走 meat 节点就结束）
                replaceThinking(thinkingMsgId, streamedText);
                chatHistory.push({ role: 'ai', content: streamedText });
            }
        } catch (err) {
            console.error(err);
            replaceThinking(thinkingMsgId, '❌ 流式通信错误：' + err.message);
        } finally {
            if (!interrupted) finishTurn();
        }
    }

    function handleStreamEvent(ev, handlers) {
        if (ev.type === 'node') {
            handlers.onNode(ev.name, ev.status);
        } else if (ev.type === 'tool') {
            handlers.onTool(ev.name, ev.status, { input: ev.input, output: ev.output });
        } else if (ev.type === 'token') {
            handlers.onToken(ev.text || '');
        } else if (ev.type === 'final') {
            handlers.onFinal(ev.reply);
        } else if (ev.type === 'interrupt') {
            handlers.onInterrupt(ev.pending || {});
        } else if (ev.type === 'error') {
            handlers.onError(ev.detail || 'unknown error');
        }
    }

    function finishTurn() {
        isWaiting = false;
        setInputEnabled(true);
        els.chatInput.focus();
    }

    // =========================================================
    //  HITL 审批 UI
    // =========================================================
    function renderApprovalHTML(pending) {
        const hint = (pending && pending.hint) || '是否允许执行以下工具调用？';
        const calls = (pending && pending.tool_calls) || [];
        const callsHTML = calls.length === 0
            ? '<div style="color:var(--text-muted);font-size:0.85rem;">(无工具调用信息)</div>'
            : calls.map((c) => `
                <div class="approval-call">
                    <code>${escapeHtml(c.name || '?')}</code>
                    <pre class="msg-code" style="margin-top:4px;">${escapeHtml(JSON.stringify(c.args || {}, null, 2))}</pre>
                </div>`).join('');
        return `
            <div class="approval-card">
                <div class="approval-hint">🛡️ ${escapeHtml(hint)}</div>
                ${callsHTML}
                <div class="approval-actions">
                    <button class="approval-btn approval-approve" data-action="approve">✅ 批准</button>
                    <button class="approval-btn approval-reject" data-action="reject">🚫 拒绝</button>
                </div>
            </div>`;
    }

    function bindApprovalButtons(thinkingMsgId) {
        const el = document.getElementById(thinkingMsgId);
        if (!el) return;
        const approveBtn = el.querySelector('[data-action="approve"]');
        const rejectBtn = el.querySelector('[data-action="reject"]');
        if (approveBtn) approveBtn.addEventListener('click', () => submitApproval(thinkingMsgId, true));
        if (rejectBtn) rejectBtn.addEventListener('click', () => submitApproval(thinkingMsgId, false));
    }

    async function submitApproval(thinkingMsgId, approved) {
        const el = document.getElementById(thinkingMsgId);
        if (el) {
            const actions = el.querySelector('.approval-actions');
            if (actions) actions.innerHTML = `<span style="color:var(--text-muted);">⏳ ${approved ? '执行中...' : '拒绝中...'}</span>`;
        }

        if (approved) {
            // 继续：使用 SSE 继续执行（新气泡展示结果）
            const nextId = appendMessage('ai', '', true);
            await streamChat(nextId, { message: null, approved: true }, '/api/chat/resume');
        } else {
            // 拒绝：非流式调用即可
            try {
                const resp = await fetch('/api/chat/resume', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ thread_id: threadId, approved: false }),
                });
                const data = await resp.json().catch(() => ({}));
                const msg = data.reply || '（已拒绝执行）';
                if (el) {
                    el.querySelector('.msg-bubble').innerHTML = formatMessage('🚫 ' + msg);
                }
                chatHistory.push({ role: 'ai', content: msg });
            } catch (err) {
                if (el) el.querySelector('.msg-bubble').innerHTML = '❌ 拒绝失败：' + err.message;
            }
            finishTurn();
        }
    }

    function updateThinkingTrace(msgId, events) {
        const el = document.getElementById(msgId);
        if (!el) return;
        const bubble = el.querySelector('.msg-bubble');
        if (!bubble) return;
        const traceHTML = renderTraceHTML(events);
        bubble.innerHTML = `
            <div class="thinking-dots"><span></span><span></span><span></span></div>
            <div class="thinking-trace">${traceHTML}</div>`;
        scrollToBottom();
    }

    /**
     * 流式渲染 LLM token：累积文本 + 底部节点/工具轨迹。
     */
    function updateStreamingBubble(msgId, text, events) {
        const el = document.getElementById(msgId);
        if (!el) return;
        const bubble = el.querySelector('.msg-bubble');
        if (!bubble) return;
        const traceHTML = renderTraceHTML(events);
        bubble.innerHTML = `
            <div class="msg-stream-text">${formatMessage(text)}<span class="stream-caret">▊</span></div>
            ${traceHTML ? `<div class="thinking-trace thinking-trace-compact">${traceHTML}</div>` : ''}`;
        scrollToBottom();
    }

    function renderTraceHTML(events) {
        if (!events || events.length === 0) return '';
        const lastFew = events.slice(-5);
        return lastFew.map((e) => {
            const icon = e.kind === 'tool' ? '🔧' : '⚙️';
            const dot = e.status === 'start' ? '●' : '○';
            const title = e.kind === 'tool' && e.output ? ` title="${escapeHtml(e.output)}"` : '';
            return `<span class="trace-step" style="opacity:${e.status === 'start' ? 1 : 0.65};"${title}>${icon} ${escapeHtml(e.name)} ${dot}</span>`;
        }).join(' ');
    }

    // =========================================================
    //  消息渲染
    // =========================================================
    let msgCounter = 0;

    function appendMessage(role, content, isThinking) {
        const id = 'msg-' + (++msgCounter);
        const msgEl = document.createElement('div');
        msgEl.className = `chat-msg chat-msg-${role}`;
        msgEl.id = id;

        if (role === 'system') {
            msgEl.innerHTML = `<div class="msg-bubble msg-system">${escapeHtml(content)}</div>`;
        } else if (role === 'user') {
            msgEl.innerHTML = `
                <div class="msg-content">
                    <div class="msg-bubble msg-user">${escapeHtml(content)}</div>
                </div>
                <div class="msg-avatar msg-avatar-user">👤</div>
            `;
        } else {
            if (isThinking) {
                msgEl.innerHTML = `
                    <div class="msg-avatar msg-avatar-ai">🍔</div>
                    <div class="msg-content">
                        <div class="msg-bubble msg-ai">
                            <div class="thinking-dots">
                                <span></span><span></span><span></span>
                            </div>
                        </div>
                    </div>
                `;
            } else {
                msgEl.innerHTML = `
                    <div class="msg-avatar msg-avatar-ai">🍔</div>
                    <div class="msg-content">
                        <div class="msg-bubble msg-ai">${formatMessage(content)}</div>
                    </div>
                `;
            }
        }

        els.chatMessages.appendChild(msgEl);
        scrollToBottom();
        return id;
    }

    function replaceThinking(id, content, raw) {
        const el = document.getElementById(id);
        if (!el) return;
        const bubble = el.querySelector('.msg-bubble');
        if (bubble) {
            bubble.innerHTML = raw ? content : formatMessage(content);
        }
        scrollToBottom();
    }

    function scrollToBottom() {
        requestAnimationFrame(() => {
            els.chatMessages.scrollTop = els.chatMessages.scrollHeight;
        });
    }

    function formatMessage(text) {
        let html = escapeHtml(text || '');
        html = html.replace(/```([\s\S]*?)```/g, '<pre class="msg-code">$1</pre>');
        html = html.replace(/`([^`]+)`/g, '<code class="msg-inline-code">$1</code>');
        html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
        html = html.replace(/\n/g, '<br>');
        return html;
    }

    function escapeHtml(str) {
        const div = document.createElement('div');
        div.textContent = str == null ? '' : String(str);
        return div.innerHTML;
    }

    function setStatus(status) {
        if (!els.chatStatus) return;
        const labels = {
            connecting: '🔄 连接中...',
            connected: '🟢 已连接',
            error: '🔴 未连接',
        };
        els.chatStatus.textContent = labels[status] || '';
        els.chatStatus.className = 'chat-status status-' + status;
    }

    function setInputEnabled(enabled) {
        els.chatInput.disabled = !enabled;
        els.chatSendBtn.disabled = !enabled;
    }

    // =========================================================
    //  下载后端文件（保留原逻辑）
    // =========================================================
    async function downloadBackend() {
        if (!currentBurgerJSON) {
            BurgerGame.showToast('请先搭建汉堡！', 'error');
            return;
        }
        try {
            els.chatDownloadBtn.disabled = true;
            els.chatDownloadBtn.textContent = '⏳ 生成中...';

            const resp = await fetch('/api/download', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(currentBurgerJSON),
            });

            if (!resp.ok) {
                const errData = await resp.json().catch(() => ({}));
                throw new Error(errData.detail || resp.statusText);
            }

            const blob = await resp.blob();
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = 'burger_agent_project.zip';
            a.style.display = 'none';
            document.body.appendChild(a);
            a.click();
            setTimeout(() => {
                document.body.removeChild(a);
                URL.revokeObjectURL(url);
            }, 1000);

            BurgerGame.showToast('📥 项目已下载！解压后按 README 说明配置运行', 'success');
        } catch (err) {
            console.error('下载失败:', err);
            BurgerGame.showToast('下载失败: ' + err.message, 'error');
        } finally {
            els.chatDownloadBtn.disabled = false;
            els.chatDownloadBtn.textContent = '📥 下载后端';
        }
    }

    // =========================================================
    //  事件绑定
    // =========================================================
    function bindEvents() {
        cacheElements();
        if (els.chatSendBtn) els.chatSendBtn.addEventListener('click', sendMessage);
        if (els.chatInput) {
            els.chatInput.addEventListener('keydown', (e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault();
                    sendMessage();
                }
            });
        }
        if (els.chatBackBtn) els.chatBackBtn.addEventListener('click', switchToBuildView);
        if (els.chatDownloadBtn) els.chatDownloadBtn.addEventListener('click', downloadBackend);
    }

    window.addEventListener('DOMContentLoaded', () => {
        setTimeout(bindEvents, 50);
    });

    BurgerGame.Chat = {
        switchToChatView: switchToChatView,
        switchToBuildView: switchToBuildView,
        downloadBackend: downloadBackend,
    };
})();
