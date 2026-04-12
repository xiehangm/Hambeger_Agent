/**
 * chat.js — 聊天界面控制器
 * 管理搭建视图 ↔ 聊天视图切换、消息收发、UI 渲染
 */
window.BurgerGame = window.BurgerGame || {};

(function () {
    'use strict';

    // =========================================================
    //  状态
    // =========================================================
    let currentBurgerJSON = null;
    let chatHistory = [];
    let isWaiting = false;

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

        if (!els.buildView) cacheElements();

        // 显示配置摘要
        renderConfigSummary(burgerJSON);

        // 清空聊天记录
        els.chatMessages.innerHTML = '';

        // 添加欢迎消息
        appendMessage('ai', `🍔 你好！我是根据你搭建的汉堡 Agent 生成的助手。\n\n**配置信息**：\n- 模型：\`${burgerJSON.meat_model || 'qwen-plus'}\`\n- 提示词：${(burgerJSON.cheese_prompt || '默认').substring(0, 60)}${(burgerJSON.cheese_prompt || '').length > 60 ? '...' : ''}\n- 工具：${(burgerJSON.vegetables || []).length > 0 ? burgerJSON.vegetables.join(', ') : '无'}\n\n请输入消息开始对话吧！`);

        // 视图切换动画
        els.buildView.classList.add('view-hidden');
        els.chatView.classList.add('view-visible');

        // 聚焦输入框
        setTimeout(() => {
            els.chatInput.focus();
        }, 400);

        // 构建后端 Agent
        buildAgentOnServer(burgerJSON);
    }

    function switchToBuildView() {
        if (!els.buildView) cacheElements();
        els.chatView.classList.remove('view-visible');
        els.buildView.classList.remove('view-hidden');
    }

    // =========================================================
    //  配置摘要
    // =========================================================
    function renderConfigSummary(json) {
        const model = json.meat_model || 'qwen-plus';
        const toolCount = (json.vegetables || []).length;
        const agentLabel = json.agent_label || '传统 LLM 对话';
        const agentEmoji = { tool_agent: '🤖', guided_chat: '🎯', basic_chat: '💬' }[json.agent_type] || '🍔';
        els.chatConfigSummary.innerHTML = `
            <span class="config-chip" style="background:rgba(108,92,231,0.15);border-color:rgba(108,92,231,0.35);color:#a29bfe;">${agentEmoji} ${agentLabel}</span>
            <span class="config-chip">🥩 ${model}</span>
            ${toolCount > 0 ? `<span class="config-chip">🥬 ${toolCount} 工具</span>` : ''}
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
    //  发送消息
    // =========================================================
    async function sendMessage() {
        if (isWaiting) return;

        const text = els.chatInput.value.trim();
        if (!text) return;

        // 显示用户消息
        appendMessage('user', text);
        els.chatInput.value = '';
        chatHistory.push({ role: 'user', content: text });

        // 显示思考中
        const thinkingId = appendMessage('ai', '', true);
        isWaiting = true;
        setInputEnabled(false);

        try {
            const resp = await fetch('/api/chat', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ message: text }),
            });

            if (resp.ok) {
                const data = await resp.json();
                const reply = data.reply || '无返回内容';
                replaceThinking(thinkingId, reply);
                chatHistory.push({ role: 'ai', content: reply });
            } else {
                const errData = await resp.json().catch(() => ({}));
                replaceThinking(thinkingId, `❌ 错误: ${errData.detail || resp.statusText}`);
            }
        } catch (err) {
            replaceThinking(thinkingId, '❌ 无法连接到后端服务器，请确保 `python server.py` 正在运行。');
        }

        isWaiting = false;
        setInputEnabled(true);
        els.chatInput.focus();
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
            // AI
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

    function replaceThinking(id, content) {
        const el = document.getElementById(id);
        if (!el) return;
        const bubble = el.querySelector('.msg-bubble');
        if (bubble) {
            bubble.innerHTML = formatMessage(content);
        }
        scrollToBottom();
    }

    function scrollToBottom() {
        requestAnimationFrame(() => {
            els.chatMessages.scrollTop = els.chatMessages.scrollHeight;
        });
    }

    // =========================================================
    //  消息格式化（简易 Markdown）
    // =========================================================
    function formatMessage(text) {
        // 转义 HTML
        let html = escapeHtml(text);
        // 代码块
        html = html.replace(/```([\s\S]*?)```/g, '<pre class="msg-code">$1</pre>');
        // 行内代码
        html = html.replace(/`([^`]+)`/g, '<code class="msg-inline-code">$1</code>');
        // 粗体
        html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
        // 换行
        html = html.replace(/\n/g, '<br>');
        return html;
    }

    function escapeHtml(str) {
        const div = document.createElement('div');
        div.textContent = str;
        return div.innerHTML;
    }

    // =========================================================
    //  状态指示器
    // =========================================================
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
    //  下载后端文件
    // =========================================================
    async function downloadBackend() {
        if (!currentBurgerJSON) {
            BurgerGame.showToast('请先搭建汉堡！', 'error');
            return;
        }

        try {
            els.chatDownloadBtn.disabled = true;
            els.chatDownloadBtn.textContent = '⏳ 生成中...';

            // 通过服务端生成 ZIP，避免浏览器端 Blob 乱码问题
            const resp = await fetch('/api/download', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(currentBurgerJSON),
            });

            if (!resp.ok) {
                const errData = await resp.json().catch(() => ({}));
                throw new Error(errData.detail || resp.statusText);
            }

            // 用服务端返回的二进制流创建下载
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

        // 发送按钮
        if (els.chatSendBtn) {
            els.chatSendBtn.addEventListener('click', sendMessage);
        }

        // 回车发送
        if (els.chatInput) {
            els.chatInput.addEventListener('keydown', (e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault();
                    sendMessage();
                }
            });
        }

        // 返回搭建
        if (els.chatBackBtn) {
            els.chatBackBtn.addEventListener('click', switchToBuildView);
        }

        // 下载
        if (els.chatDownloadBtn) {
            els.chatDownloadBtn.addEventListener('click', downloadBackend);
        }
    }

    // 初始化
    window.addEventListener('DOMContentLoaded', () => {
        // 延迟绑定，等其他模块加载完
        setTimeout(bindEvents, 50);
    });

    // 导出
    BurgerGame.Chat = {
        switchToChatView: switchToChatView,
        switchToBuildView: switchToBuildView,
        downloadBackend: downloadBackend,
    };
})();
