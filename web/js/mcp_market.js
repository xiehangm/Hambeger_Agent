/**
 * mcp_market.js — MCP 工具市场（独立面板）
 *
 * 职责：
 *   1. 浏览内置 MCP 服务器目录
 *   2. 一键 / 配置 安装、卸载
 *   3. 工具发现（启动子进程 → tools/list）
 *   4. 添加自定义服务器
 *
 * 不职责：
 *   - 不直接挂载工具到 Agent；工具发现后通过事件 `mcp:tools-updated`
 *     通知生菜面板刷新，由用户在生菜里挑选哪些工具要挂上。
 *
 * 事件契约：
 *   window dispatch:
 *     - 'mcp:installed-changed'  服务器安装/卸载/自定义后触发
 *     - 'mcp:tools-updated'      工具发现成功 / 卸载后触发
 */
window.BurgerGame = window.BurgerGame || {};

(function () {
    'use strict';

    var API = {
        BUILTIN: '/api/mcp/servers/builtin',
        INSTALLED: '/api/mcp/servers/installed',
        INSTALL: '/api/mcp/servers/install',
        UNINSTALL: '/api/mcp/servers/uninstall',
        DISCOVER: function (sid) {
            return '/api/mcp/servers/' + encodeURIComponent(sid) + '/discover';
        },
        CUSTOM: '/api/mcp/servers/custom',
    };

    var mcpPanel = null;
    var installedIds = new Set();
    var allBuiltin = [];

    function init() {
        mcpPanel = document.getElementById('mcp-panel');
        if (!mcpPanel) return;
        bindEvents();
        refresh();
    }

    function bindEvents() {
        var btnOpen = document.getElementById('btn-mcp-market');
        if (btnOpen) btnOpen.addEventListener('click', togglePanel);

        var btnClose = document.getElementById('mcp-panel-close');
        if (btnClose) btnClose.addEventListener('click', closePanel);

        var btnAddCustom = document.getElementById('mcp-add-custom');
        if (btnAddCustom) btnAddCustom.addEventListener('click', showAddCustomDialog);

        var searchInput = document.getElementById('mcp-search-input');
        if (searchInput) {
            searchInput.addEventListener('input', function () {
                renderBuiltin(searchInput.value.trim().toLowerCase());
            });
        }

        var tabBtns = document.querySelectorAll('.mcp-tab-btn');
        tabBtns.forEach(function (btn) {
            btn.addEventListener('click', function () {
                tabBtns.forEach(function (b) { b.classList.remove('active'); });
                btn.classList.add('active');
                switchTab(btn.dataset.tab);
            });
        });
    }

    function switchTab(tab) {
        var builtinTab = document.getElementById('mcp-tab-builtin');
        var installedTab = document.getElementById('mcp-tab-installed');
        if (builtinTab) builtinTab.style.display = tab === 'builtin' ? 'block' : 'none';
        if (installedTab) installedTab.style.display = tab === 'installed' ? 'block' : 'none';
        if (tab === 'installed') loadInstalled();
        if (tab === 'builtin') loadBuiltin();
    }

    function refresh() {
        return loadInstalled().then(loadBuiltin);
    }

    function loadBuiltin() {
        var container = document.getElementById('mcp-builtin-list');
        if (!container) return Promise.resolve();
        container.innerHTML = '<div class="mcp-loading">🔄 加载中...</div>';
        return fetch(API.BUILTIN)
            .then(function (r) { return r.json(); })
            .then(function (data) {
                allBuiltin = data.servers || [];
                renderBuiltin('');
            })
            .catch(function () {
                container.innerHTML = '<div class="mcp-empty">⚠️ 无法加载服务器目录</div>';
            });
    }

    function loadInstalled() {
        var container = document.getElementById('mcp-installed-list');
        return fetch(API.INSTALLED)
            .then(function (r) { return r.json(); })
            .then(function (data) {
                var servers = data.servers || [];
                installedIds = new Set(servers.map(function (s) { return s.id; }));
                if (container) {
                    if (servers.length === 0) {
                        container.innerHTML =
                            '<div class="mcp-empty">尚未安装任何 MCP 服务器<br>' +
                            '<small>前往「内置目录」安装</small></div>';
                    } else {
                        container.innerHTML = '';
                        servers.forEach(function (srv) {
                            container.appendChild(createCard(srv, 'installed'));
                        });
                    }
                }
                updateToolCount(servers.length);
            })
            .catch(function () {
                if (container) {
                    container.innerHTML = '<div class="mcp-empty">⚠️ 无法加载已安装列表</div>';
                }
            });
    }

    function renderBuiltin(filterQ) {
        var container = document.getElementById('mcp-builtin-list');
        if (!container) return;
        var list = filterQ
            ? allBuiltin.filter(function (s) {
                return (s.name || '').toLowerCase().indexOf(filterQ) >= 0 ||
                    (s.description || '').toLowerCase().indexOf(filterQ) >= 0 ||
                    (s.category || '').toLowerCase().indexOf(filterQ) >= 0 ||
                    (s.id || '').toLowerCase().indexOf(filterQ) >= 0;
            })
            : allBuiltin;

        if (list.length === 0) {
            container.innerHTML = '<div class="mcp-empty">没有匹配的服务器</div>';
            return;
        }
        container.innerHTML = '';
        list.forEach(function (srv) {
            container.appendChild(createCard(srv, 'builtin'));
        });
    }

    function createCard(srv, mode) {
        var card = document.createElement('div');
        card.className = 'mcp-server-card';
        card.dataset.serverId = srv.id;

        var isInstalled = installedIds.has(srv.id) || mode === 'installed';
        var envKeys = srv.env_keys || [];
        var needsEnv = envKeys.length > 0;

        var envHtml = '';
        if (needsEnv && mode === 'builtin' && !isInstalled) {
            envHtml = '<div class="mcp-env-config" style="display:none">' +
                envKeys.map(function (k) {
                    return '<div class="mcp-env-item"><label>' + escapeHtml(k) +
                        '</label><input type="text" data-env="' + escapeHtml(k) +
                        '" placeholder="' + escapeHtml(k) + '"></div>';
                }).join('') +
                '</div>';
        }

        var actions;
        if (mode === 'installed') {
            actions =
                '<button class="mcp-btn mcp-btn-discover">🔍 发现工具</button>' +
                '<button class="mcp-btn mcp-btn-uninstall">🗑️ 卸载</button>';
        } else if (isInstalled) {
            actions = '<span class="mcp-badge-installed">✅ 已安装</span>';
        } else if (needsEnv) {
            actions = '<button class="mcp-btn mcp-btn-config">⚙️ 配置安装</button>';
        } else {
            actions = '<button class="mcp-btn mcp-btn-install">📥 一键安装</button>';
        }

        var sourceTag = srv.source === 'custom'
            ? '<span class="mcp-source-tag mcp-source-custom">自定义</span>'
            : '';

        card.innerHTML =
            '<div class="mcp-server-header">' +
            '<span class="mcp-server-emoji">' + (srv.emoji || '🔌') + '</span>' +
            '<div class="mcp-server-info">' +
            '<div class="mcp-server-name">' + escapeHtml(srv.name || srv.id) +
            ' <span class="mcp-server-id">(' + escapeHtml(srv.id) + ')</span>' +
            sourceTag + '</div>' +
            '<div class="mcp-server-desc">' + escapeHtml(srv.description || '') + '</div>' +
            '</div>' +
            '</div>' +
            envHtml +
            '<div class="mcp-server-actions">' + actions + '</div>';

        if (mode === 'installed' && Array.isArray(srv.tools) && srv.tools.length > 0) {
            card.appendChild(renderToolsList(srv.tools));
        }

        bindCardActions(card, srv, mode);
        return card;
    }

    function renderToolsList(tools) {
        var list = document.createElement('div');
        list.className = 'mcp-tools-list';
        tools.forEach(function (t) {
            var item = document.createElement('div');
            item.className = 'mcp-tool-item';
            item.innerHTML =
                '<span class="mcp-tool-name">🔧 ' + escapeHtml(t.name) + '</span>' +
                '<span class="mcp-tool-desc">' + escapeHtml(t.description || '') + '</span>';
            list.appendChild(item);
        });
        return list;
    }

    function bindCardActions(card, srv, mode) {
        var installBtn = card.querySelector('.mcp-btn-install');
        var configBtn = card.querySelector('.mcp-btn-config');
        var uninstallBtn = card.querySelector('.mcp-btn-uninstall');
        var discoverBtn = card.querySelector('.mcp-btn-discover');

        if (installBtn) {
            installBtn.addEventListener('click', function () {
                doInstall(srv.id, {}, installBtn);
            });
        }
        if (configBtn) {
            configBtn.addEventListener('click', function () {
                var envDiv = card.querySelector('.mcp-env-config');
                if (!envDiv) return;
                var visible = envDiv.style.display !== 'none';
                if (!visible) {
                    envDiv.style.display = 'block';
                    configBtn.textContent = '🚀 确认安装';
                    configBtn.classList.remove('mcp-btn-config');
                    configBtn.classList.add('mcp-btn-install');
                    var newHandler = function () {
                        var envValues = {};
                        envDiv.querySelectorAll('input').forEach(function (inp) {
                            envValues[inp.dataset.env] = inp.value;
                        });
                        doInstall(srv.id, envValues, configBtn);
                        configBtn.removeEventListener('click', newHandler);
                    };
                    configBtn.addEventListener('click', newHandler);
                }
            });
        }
        if (uninstallBtn) {
            uninstallBtn.addEventListener('click', function () {
                if (!confirm('确定要卸载 ' + (srv.name || srv.id) + ' 吗？')) return;
                doUninstall(srv.id);
            });
        }
        if (discoverBtn) {
            discoverBtn.addEventListener('click', function () {
                doDiscover(srv.id, card, discoverBtn);
            });
        }
    }

    function doInstall(serverId, envValues, btnEl) {
        if (btnEl) {
            btnEl.disabled = true;
            btnEl.textContent = '⏳ 安装中...';
        }
        return fetch(API.INSTALL, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ server_id: serverId, env_values: envValues || {} }),
        })
            .then(function (r) {
                if (!r.ok) return r.json().then(function (d) { throw new Error(d.detail || '安装失败'); });
                return r.json();
            })
            .then(function () {
                toast('✅ ' + serverId + ' 安装成功', 'success');
                emit('mcp:installed-changed');
                return refresh();
            })
            .catch(function (err) {
                toast('安装失败: ' + err.message, 'error');
                if (btnEl) {
                    btnEl.disabled = false;
                    btnEl.textContent = '📥 重试';
                }
            });
    }

    function doUninstall(serverId) {
        return fetch(API.UNINSTALL, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ server_id: serverId }),
        })
            .then(function (r) { return r.json(); })
            .then(function () {
                toast('🗑️ ' + serverId + ' 已卸载', 'info');
                emit('mcp:installed-changed');
                emit('mcp:tools-updated');
                return refresh();
            })
            .catch(function () { toast('卸载失败', 'error'); });
    }

    function doDiscover(serverId, cardEl, btn) {
        if (btn) { btn.textContent = '⏳ 发现中...'; btn.disabled = true; }
        return fetch(API.DISCOVER(serverId), { method: 'POST' })
            .then(function (r) { return r.json(); })
            .then(function (data) {
                var tools = data.tools || [];
                if (!data.success) {
                    toast('发现失败: ' + (data.error || '未知错误'), 'error');
                } else if (tools.length === 0) {
                    toast('未发现工具', 'info');
                } else {
                    toast('🔍 发现 ' + tools.length + ' 个工具', 'success');
                    var existing = cardEl.querySelector('.mcp-tools-list');
                    if (existing) existing.remove();
                    cardEl.appendChild(renderToolsList(tools));
                    emit('mcp:tools-updated');
                }
                if (btn) { btn.textContent = '🔍 发现工具'; btn.disabled = false; }
            })
            .catch(function () {
                toast('工具发现失败', 'error');
                if (btn) { btn.textContent = '🔍 发现工具'; btn.disabled = false; }
            });
    }

    function showAddCustomDialog() {
        var overlay = document.createElement('div');
        overlay.className = 'mcp-dialog-overlay';
        overlay.addEventListener('click', function (e) {
            if (e.target === overlay) overlay.remove();
        });

        var dialog = document.createElement('div');
        dialog.className = 'mcp-dialog';
        dialog.innerHTML =
            '<div class="mcp-dialog-title">⚡ 添加自定义 MCP 服务器</div>' +
            '<div class="mcp-dialog-form">' +
            '<div class="mcp-env-item"><label>服务器 ID</label><input id="custom-id" placeholder="my-mcp"></div>' +
            '<div class="mcp-env-item"><label>名称</label><input id="custom-name" placeholder="My MCP"></div>' +
            '<div class="mcp-env-item"><label>命令</label><input id="custom-command" placeholder="npx / python / node"></div>' +
            '<div class="mcp-env-item"><label>参数(逗号分隔)</label><input id="custom-args" placeholder="-y, @org/server"></div>' +
            '<div class="mcp-env-item"><label>描述</label><input id="custom-desc" placeholder="可选"></div>' +
            '<div class="mcp-env-item"><label>Emoji</label><input id="custom-emoji" value="⚡"></div>' +
            '</div>' +
            '<div class="mcp-dialog-actions">' +
            '<button class="mcp-btn mcp-btn-cancel" id="custom-cancel">取消</button>' +
            '<button class="mcp-btn mcp-btn-install" id="custom-submit">➕ 添加</button>' +
            '</div>';
        overlay.appendChild(dialog);
        document.body.appendChild(overlay);

        document.getElementById('custom-cancel').addEventListener('click', function () {
            overlay.remove();
        });
        document.getElementById('custom-submit').addEventListener('click', function () {
            var sid = document.getElementById('custom-id').value.trim();
            var name = document.getElementById('custom-name').value.trim();
            var command = document.getElementById('custom-command').value.trim();
            var argsStr = document.getElementById('custom-args').value.trim();
            var desc = document.getElementById('custom-desc').value.trim();
            var emoji = document.getElementById('custom-emoji').value.trim() || '⚡';
            if (!sid || !name || !command) {
                toast('请填写 ID、名称、命令', 'error');
                return;
            }
            var args = argsStr ? argsStr.split(',').map(function (a) { return a.trim(); }) : [];
            fetch(API.CUSTOM, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    server_id: sid, name: name, command: command, args: args,
                    description: desc, emoji: emoji,
                }),
            })
                .then(function (r) {
                    if (!r.ok) return r.json().then(function (d) { throw new Error(d.detail || '失败'); });
                    return r.json();
                })
                .then(function () {
                    toast('✅ 自定义服务器已添加', 'success');
                    overlay.remove();
                    emit('mcp:installed-changed');
                    refresh();
                })
                .catch(function (err) { toast('添加失败: ' + err.message, 'error'); });
        });
    }

    function togglePanel() {
        if (!mcpPanel) return;
        mcpPanel.classList.toggle('visible');
        if (mcpPanel.classList.contains('visible')) refresh();
    }

    function closePanel() {
        if (mcpPanel) mcpPanel.classList.remove('visible');
    }

    function updateToolCount(count) {
        var el = document.getElementById('mcp-tool-count');
        if (!el) return;
        if (count > 0) {
            el.textContent = count + ' 个MCP服务器';
            el.style.display = 'inline';
        } else {
            el.style.display = 'none';
        }
    }

    function emit(name) {
        window.dispatchEvent(new CustomEvent(name));
    }

    function toast(msg, level) {
        if (window.BurgerGame && BurgerGame.showToast) {
            BurgerGame.showToast(msg, level || 'info');
        } else {
            console.log('[MCP]', msg);
        }
    }

    function escapeHtml(str) {
        var div = document.createElement('div');
        div.textContent = (str == null ? '' : String(str));
        return div.innerHTML;
    }

    window.addEventListener('DOMContentLoaded', function () {
        setTimeout(init, 100);
    });

    BurgerGame.MCPMarket = {
        init: init,
        refresh: refresh,
        togglePanel: togglePanel,
        closePanel: closePanel,
    };
})();
