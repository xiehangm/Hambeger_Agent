/**
 * mcp_market.js — MCP 工具市场交互控制器
 * 管理工具浏览、搜索、安装/卸载、环境变量配置
 */
window.BurgerGame = window.BurgerGame || {};

(function () {
    'use strict';

    let mcpPanel = null;
    let installedServers = {};
    let currentCategory = 'all';

    const CATEGORY_ICONS = {
        '文件操作': '📁',
        '开发工具': '🔧',
        '数据库': '🗄️',
        '搜索': '🔍',
        '网络': '📡',
        '浏览器': '🌐',
        '通讯': '💬',
        '记忆': '🧠',
        '推理': '🤔',
        '云存储': '💾',
        '监控': '🚨',
        '其他': '📦',
        '自定义': '⚡',
    };

    function init() {
        mcpPanel = document.getElementById('mcp-panel');
        if (!mcpPanel) return;

        bindEvents();
        loadBuiltinServers();
        loadInstalledServers();
    }

    function bindEvents() {
        var btnOpen = document.getElementById('btn-mcp-market');
        if (btnOpen) {
            btnOpen.addEventListener('click', togglePanel);
        }

        var btnClose = document.getElementById('mcp-panel-close');
        if (btnClose) {
            btnClose.addEventListener('click', closePanel);
        }

        var btnBuiltinSearch = document.getElementById('mcp-search-btn');
        if (btnBuiltinSearch) {
            btnBuiltinSearch.addEventListener('click', filterBuiltinServers);
        }

        var builtinSearchInput = document.getElementById('mcp-search-input');
        if (builtinSearchInput) {
            builtinSearchInput.addEventListener('keydown', function (e) {
                if (e.key === 'Enter') filterBuiltinServers();
            });
        }

        var btnRegistrySearch = document.getElementById('mcp-registry-search-btn');
        if (btnRegistrySearch) {
            btnRegistrySearch.addEventListener('click', searchRegistry);
        }

        var registrySearchInput = document.getElementById('mcp-registry-search');
        if (registrySearchInput) {
            registrySearchInput.addEventListener('keydown', function (e) {
                if (e.key === 'Enter') searchRegistry();
            });
        }

        var btnAddCustom = document.getElementById('mcp-add-custom');
        if (btnAddCustom) {
            btnAddCustom.addEventListener('click', showAddCustomDialog);
        }

        var tabBtns = document.querySelectorAll('.mcp-tab-btn');
        tabBtns.forEach(function (btn) {
            btn.addEventListener('click', function () {
                document.querySelectorAll('.mcp-tab-btn').forEach(function (b) { b.classList.remove('active'); });
                btn.classList.add('active');
                var tab = btn.dataset.tab;
                switchTab(tab);
            });
        });
    }

    function togglePanel() {
        if (!mcpPanel) return;
        mcpPanel.classList.toggle('visible');
        if (mcpPanel.classList.contains('visible')) {
            loadInstalledServers();
        }
    }

    function closePanel() {
        if (mcpPanel) mcpPanel.classList.remove('visible');
    }

    function switchTab(tab) {
        var builtinTab = document.getElementById('mcp-tab-builtin');
        var registryTab = document.getElementById('mcp-tab-registry');
        var installedTab = document.getElementById('mcp-tab-installed');

        if (builtinTab) builtinTab.style.display = tab === 'builtin' ? 'block' : 'none';
        if (registryTab) registryTab.style.display = tab === 'registry' ? 'block' : 'none';
        if (installedTab) installedTab.style.display = tab === 'installed' ? 'block' : 'none';

        if (tab === 'installed') loadInstalledServers();
        if (tab === 'registry') loadRegistryServers();
    }

    function loadBuiltinServers() {
        var container = document.getElementById('mcp-builtin-list');
        if (!container) return;

        fetch('/api/mcp/builtin')
            .then(function (r) { return r.json(); })
            .then(function (data) {
                renderServerCards(container, data.servers || [], 'builtin');
            })
            .catch(function () {
                container.innerHTML = '<div class="mcp-empty">⚠️ 无法加载内置服务器列表</div>';
            });
    }

    function loadInstalledServers() {
        var container = document.getElementById('mcp-installed-list');
        if (!container) return;

        fetch('/api/mcp/installed')
            .then(function (r) { return r.json(); })
            .then(function (data) {
                var servers = data.servers || [];
                installedServers = {};
                servers.forEach(function (s) { installedServers[s.name] = true; });
                if (servers.length === 0) {
                    container.innerHTML = '<div class="mcp-empty">尚未安装任何 MCP 服务器<br><small>前往「工具市场」或「注册中心」安装</small></div>';
                } else {
                    renderServerCards(container, servers, 'installed');
                }
            })
            .catch(function () {
                container.innerHTML = '<div class="mcp-empty">⚠️ 无法加载已安装列表</div>';
            });
    }

    function loadRegistryServers() {
        var container = document.getElementById('mcp-registry-list');
        if (!container) return;

        container.innerHTML = '<div class="mcp-loading">🔄 正在从 MCP 注册中心搜索...</div>';

        fetch('/api/mcp/popular')
            .then(function (r) { return r.json(); })
            .then(function (data) {
                var servers = data.servers || [];
                if (servers.length === 0) {
                    container.innerHTML = '<div class="mcp-empty">未找到服务器</div>';
                } else {
                    renderPopularServers(container, servers, data.categories || {});
                }
            })
            .catch(function () {
                container.innerHTML = '<div class="mcp-empty">⚠️ 无法连接注册中心</div>';
            });
    }

    var _allBuiltinServers = [];

    function filterBuiltinServers() {
        var input = document.getElementById('mcp-search-input');
        if (!input) return;
        var query = input.value.trim().toLowerCase();
        var container = document.getElementById('mcp-builtin-list');
        if (!container) return;

        if (!_allBuiltinServers.length) {
            container.innerHTML = '<div class="mcp-loading">🔄 加载中...</div>';
            fetch('/api/mcp/builtin')
                .then(function (r) { return r.json(); })
                .then(function (data) {
                    _allBuiltinServers = data.servers || [];
                    doFilter(container, query);
                });
        } else {
            doFilter(container, query);
        }
    }

    function doFilter(container, query) {
        var filtered = query
            ? _allBuiltinServers.filter(function (s) {
                return s.name.toLowerCase().indexOf(query) >= 0 ||
                       (s.description || '').toLowerCase().indexOf(query) >= 0 ||
                       (s.category || '').toLowerCase().indexOf(query) >= 0;
            })
            : _allBuiltinServers;
        renderServerCards(container, filtered, 'builtin');
    }

    function searchRegistry() {
        var input = document.getElementById('mcp-registry-search');
        if (!input) return;
        var query = input.value.trim();
        if (!query) return;

        var container = document.getElementById('mcp-registry-list');
        if (!container) return;

        container.innerHTML = '<div class="mcp-loading">🔄 搜索中: "' + escapeHtml(query) + '"...</div>';

        fetch('/api/mcp/search', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ query: query, limit: 20 }),
        })
            .then(function (r) { return r.json(); })
            .then(function (data) {
                var servers = data.servers || [];
                if (servers.length === 0) {
                    container.innerHTML = '<div class="mcp-empty">没有找到匹配 "' + escapeHtml(query) + '" 的服务器</div>';
                } else {
                    container.innerHTML = '<div class="mcp-search-results-header">找到 ' + servers.length + ' 个结果</div>';
                    servers.forEach(function (srv) {
                        container.appendChild(createRegistryCard(srv));
                    });
                }
            })
            .catch(function () {
                container.innerHTML = '<div class="mcp-empty">⚠️ 搜索失败</div>';
            });
    }

    function renderServerCards(container, servers, mode) {
        container.innerHTML = '';
        servers.forEach(function (srv) {
            container.appendChild(createServerCard(srv, mode));
        });
    }

    function renderPopularServers(container, servers, categories) {
        container.innerHTML = '';
        var catOrder = Object.keys(categories);
        catOrder.forEach(function (cat) {
            var catIcon = CATEGORY_ICONS[cat] || '📦';
            var header = document.createElement('div');
            header.className = 'mcp-category-header';
            header.textContent = catIcon + ' ' + cat;
            container.appendChild(header);

            var grid = document.createElement('div');
            grid.className = 'mcp-server-grid';
            categories[cat].forEach(function (srv) {
                grid.appendChild(createPopularCard(srv));
            });
            container.appendChild(grid);
        });
    }

    function createServerCard(srv, mode) {
        var card = document.createElement('div');
        card.className = 'mcp-server-card';

        var isInstalled = !!installedServers[srv.name];
        var envList = srv.env || [];
        var needsEnv = envList.length > 0;

        var envHtml = '';
        if (needsEnv) {
            var envItems = envList.map(function (e) {
                return '<div class="mcp-env-item"><label>' + escapeHtml(e) + '</label><input type="text" data-env="' + escapeHtml(e) + '" placeholder="请输入 ' + escapeHtml(e) + '"></div>';
            }).join('');
            envHtml = '<div class="mcp-env-config" style="display:none">' + envItems + '</div>';
        }

        var actionBtn = '';
        if (mode === 'installed') {
            actionBtn = '<button class="mcp-btn mcp-btn-uninstall" data-server="' + escapeHtml(srv.name) + '">🗑️ 卸载</button>' +
                '<button class="mcp-btn mcp-btn-discover" data-server="' + escapeHtml(srv.name) + '">🔍 发现工具</button>';
        } else if (isInstalled) {
            actionBtn = '<span class="mcp-badge-installed">✅ 已安装</span>';
        } else if (needsEnv) {
            actionBtn = '<button class="mcp-btn mcp-btn-config" data-server="' + escapeHtml(srv.name) + '">⚙️ 配置安装</button>';
        } else {
            actionBtn = '<button class="mcp-btn mcp-btn-install" data-server="' + escapeHtml(srv.name) + '">📥 一键安装</button>';
        }

        card.innerHTML =
            '<div class="mcp-server-header">' +
                '<span class="mcp-server-emoji">' + (srv.emoji || '🔌') + '</span>' +
                '<div class="mcp-server-info">' +
                    '<div class="mcp-server-name">' + escapeHtml(srv.name) + '</div>' +
                    '<div class="mcp-server-desc">' + escapeHtml(srv.description || '') + '</div>' +
                '</div>' +
            '</div>' +
            envHtml +
            '<div class="mcp-server-actions">' + actionBtn + '</div>';

        bindCardActions(card, srv, mode);
        return card;
    }

    function createPopularCard(srv) {
        var card = document.createElement('div');
        card.className = 'mcp-popular-card';

        var envVars = srv.env_vars || [];
        var badge = envVars.length > 0
            ? '<span class="mcp-popular-badge">需要配置</span>'
            : '<span class="mcp-popular-badge mcp-badge-easy">一键安装</span>';

        card.innerHTML =
            '<div class="mcp-popular-emoji">' + (srv.emoji || '🔌') + '</div>' +
            '<div class="mcp-popular-name">' + escapeHtml(srv.name) + '</div>' +
            '<div class="mcp-popular-desc">' + escapeHtml(srv.description || '') + '</div>' +
            badge;

        card.addEventListener('click', function () {
            showInstallDialog(srv);
        });

        return card;
    }

    function createRegistryCard(srv) {
        var card = document.createElement('div');
        card.className = 'mcp-registry-card';

        var sourceLabel = srv.source === 'official' ? '🇨🇭 Official' : '🔥 Smithery';

        card.innerHTML =
            '<div class="mcp-registry-header">' +
                '<div class="mcp-registry-info">' +
                    '<div class="mcp-registry-name">' + escapeHtml(srv.name || srv.qualified_name) + '</div>' +
                    '<div class="mcp-registry-desc">' + escapeHtml(srv.description || '暂无描述') + '</div>' +
                '</div>' +
                '<span class="mcp-registry-source">' + sourceLabel + '</span>' +
            '</div>';

        return card;
    }

    function bindCardActions(card, srv, mode) {
        var installBtn = card.querySelector('.mcp-btn-install');
        if (installBtn) {
            installBtn.addEventListener('click', function () {
                doInstall(srv.name, {}, installBtn);
            });
        }

        var configBtn = card.querySelector('.mcp-btn-config');
        if (configBtn) {
            configBtn.addEventListener('click', function () {
                var envDiv = card.querySelector('.mcp-env-config');
                if (envDiv) {
                    var visible = envDiv.style.display !== 'none';
                    envDiv.style.display = visible ? 'none' : 'block';
                    if (!visible) {
                        configBtn.textContent = '🚀 确认安装';
                        configBtn.className = 'mcp-btn mcp-btn-install';
                        configBtn.addEventListener('click', function handler() {
                            var envValues = {};
                            envDiv.querySelectorAll('input').forEach(function (inp) {
                                envValues[inp.dataset.env] = inp.value;
                            });
                            doInstall(srv.name, envValues, configBtn);
                            configBtn.removeEventListener('click', handler);
                        });
                    }
                }
            });
        }

        var uninstallBtn = card.querySelector('.mcp-btn-uninstall');
        if (uninstallBtn) {
            uninstallBtn.addEventListener('click', function () {
                doUninstall(srv.name, card);
            });
        }

        var discoverBtn = card.querySelector('.mcp-btn-discover');
        if (discoverBtn) {
            discoverBtn.addEventListener('click', function () {
                doDiscover(srv.name, card);
            });
        }
    }

    function doInstall(serverId, envValues, btnEl) {
        btnEl.disabled = true;
        btnEl.textContent = '⏳ 安装中...';

        fetch('/api/mcp/install', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ server_id: serverId, env_values: envValues }),
        })
            .then(function (r) {
                if (!r.ok) return r.json().then(function (d) { throw new Error(d.detail || '安装失败'); });
                return r.json();
            })
            .then(function (data) {
                btnEl.textContent = '✅ 已安装';
                btnEl.className = 'mcp-btn mcp-btn-done';
                BurgerGame.showToast('✅ ' + serverId + ' 安装成功！', 'success');
                loadInstalledServers();
                updateToolCount();
            })
            .catch(function (err) {
                btnEl.textContent = '❌ 失败';
                btnEl.disabled = false;
                BurgerGame.showToast('安装失败: ' + err.message, 'error');
                setTimeout(function () {
                    btnEl.textContent = '📥 安装';
                    btnEl.className = 'mcp-btn mcp-btn-install';
                }, 2000);
            });
    }

    function doUninstall(serverId, cardEl) {
        if (!confirm('确定要卸载 ' + serverId + ' 吗？')) return;

        fetch('/api/mcp/uninstall', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ server_id: serverId }),
        })
            .then(function (r) { return r.json(); })
            .then(function () {
                BurgerGame.showToast('🗑️ ' + serverId + ' 已卸载', 'info');
                loadInstalledServers();
                loadBuiltinServers();
                updateToolCount();
            })
            .catch(function () {
                BurgerGame.showToast('卸载失败', 'error');
            });
    }

    function doDiscover(serverId, cardEl) {
        var btn = cardEl.querySelector('.mcp-btn-discover');
        if (btn) {
            btn.textContent = '⏳ 发现中...';
            btn.disabled = true;
        }

        fetch('/api/mcp/discover', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ server_id: serverId }),
        })
            .then(function (r) { return r.json(); })
            .then(function (data) {
                var tools = data.tools || [];
                if (tools.length === 0) {
                    BurgerGame.showToast('未发现可用工具（可能需要 npx 环境）', 'info');
                } else {
                    BurgerGame.showToast('🔍 发现 ' + tools.length + ' 个工具！', 'success');
                    showToolsList(cardEl, tools);
                }
                if (btn) {
                    btn.textContent = '🔍 发现工具';
                    btn.disabled = false;
                }
            })
            .catch(function () {
                BurgerGame.showToast('工具发现失败', 'error');
                if (btn) {
                    btn.textContent = '🔍 发现工具';
                    btn.disabled = false;
                }
            });
    }

    function showToolsList(cardEl, tools) {
        var existing = cardEl.querySelector('.mcp-tools-list');
        if (existing) existing.remove();

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
        cardEl.appendChild(list);
    }

    function showInstallDialog(srv) {
        var envVars = srv.env_vars || [];

        var overlay = document.createElement('div');
        overlay.className = 'mcp-dialog-overlay';
        overlay.addEventListener('click', function (e) {
            if (e.target === overlay) overlay.remove();
        });

        var dialog = document.createElement('div');
        dialog.className = 'mcp-dialog';

        var envHtml = '';
        if (envVars.length > 0) {
            envHtml = '<div class="mcp-dialog-env">' +
                '<p>此服务器需要配置以下环境变量：</p>' +
                envVars.map(function (v) {
                    return '<div class="mcp-env-item"><label>' + escapeHtml(v) + '</label><input type="text" id="dlg-env-' + escapeHtml(v) + '" placeholder="' + escapeHtml(v) + '"></div>';
                }).join('') +
                '</div>';
        }

        dialog.innerHTML =
            '<div class="mcp-dialog-title">' + (srv.emoji || '🔌') + ' 安装 ' + escapeHtml(srv.name) + '</div>' +
            '<div class="mcp-dialog-desc">' + escapeHtml(srv.description || '') + '</div>' +
            '<div class="mcp-dialog-hint"><code>' + escapeHtml(srv.install_hint || '') + '</code></div>' +
            envHtml +
            '<div class="mcp-dialog-actions">' +
                '<button class="mcp-btn mcp-btn-cancel" id="dlg-cancel">取消</button>' +
                '<button class="mcp-btn mcp-btn-install" id="dlg-install">🚀 确认安装</button>' +
            '</div>';

        overlay.appendChild(dialog);
        document.body.appendChild(overlay);

        document.getElementById('dlg-cancel').addEventListener('click', function () {
            overlay.remove();
        });

        document.getElementById('dlg-install').addEventListener('click', function () {
            var envValues = {};
            envVars.forEach(function (v) {
                var inp = document.getElementById('dlg-env-' + v);
                if (inp && inp.value) envValues[v] = inp.value;
            });

            var installBtn = document.getElementById('dlg-install');
            installBtn.disabled = true;
            installBtn.textContent = '⏳ 安装中...';

            var serverId = srv.qualified_name || srv.name;

            fetch('/api/mcp/install', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ server_id: serverId, env_values: envValues }),
            })
                .then(function (r) {
                    if (!r.ok) return r.json().then(function (d) { throw new Error(d.detail || '安装失败'); });
                    return r.json();
                })
                .then(function () {
                    BurgerGame.showToast('✅ ' + srv.name + ' 安装成功！', 'success');
                    overlay.remove();
                    loadInstalledServers();
                    loadBuiltinServers();
                    updateToolCount();
                })
                .catch(function (err) {
                    BurgerGame.showToast('安装失败: ' + err.message, 'error');
                    installBtn.textContent = '🚀 确认安装';
                    installBtn.disabled = false;
                });
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
                '<div class="mcp-env-item"><label>服务器 ID</label><input type="text" id="custom-id" placeholder="my-mcp-server"></div>' +
                '<div class="mcp-env-item"><label>名称</label><input type="text" id="custom-name" placeholder="My MCP Server"></div>' +
                '<div class="mcp-env-item"><label>命令</label><input type="text" id="custom-command" placeholder="npx / python / node"></div>' +
                '<div class="mcp-env-item"><label>参数 (逗号分隔)</label><input type="text" id="custom-args" placeholder="-y, @org/mcp-server"></div>' +
                '<div class="mcp-env-item"><label>描述</label><input type="text" id="custom-desc" placeholder="服务器功能描述"></div>' +
                '<div class="mcp-env-item"><label>Emoji</label><input type="text" id="custom-emoji" placeholder="🔌" value="🔌"></div>' +
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
            var id = document.getElementById('custom-id').value.trim();
            var name = document.getElementById('custom-name').value.trim();
            var command = document.getElementById('custom-command').value.trim();
            var argsStr = document.getElementById('custom-args').value.trim();
            var desc = document.getElementById('custom-desc').value.trim();
            var emoji = document.getElementById('custom-emoji').value.trim() || '🔌';

            if (!id || !name || !command) {
                BurgerGame.showToast('请填写 ID、名称和命令', 'error');
                return;
            }

            var args = argsStr ? argsStr.split(',').map(function (a) { return a.trim(); }) : [];

            fetch('/api/mcp/custom', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    server_id: id,
                    name: name,
                    command: command,
                    args: args,
                    description: desc,
                    emoji: emoji,
                }),
            })
                .then(function (r) { return r.json(); })
                .then(function () {
                    BurgerGame.showToast('✅ 自定义服务器 ' + name + ' 已添加！', 'success');
                    overlay.remove();
                    loadInstalledServers();
                })
                .catch(function () {
                    BurgerGame.showToast('添加失败', 'error');
                });
        });
    }

    function updateToolCount() {
        var el = document.getElementById('mcp-tool-count');
        if (!el) return;
        fetch('/api/mcp/installed')
            .then(function (r) { return r.json(); })
            .then(function (data) {
                var count = (data.servers || []).length;
                el.textContent = count > 0 ? count + ' 个MCP工具' : '';
                el.style.display = count > 0 ? 'inline' : 'none';
            })
            .catch(function () {});
    }

    function escapeHtml(str) {
        var div = document.createElement('div');
        div.textContent = str;
        return div.innerHTML;
    }

    window.addEventListener('DOMContentLoaded', function () {
        setTimeout(init, 100);
    });

    BurgerGame.MCPMarket = {
        init: init,
        togglePanel: togglePanel,
        closePanel: closePanel,
        refresh: function () {
            loadBuiltinServers();
            loadInstalledServers();
            updateToolCount();
        },
    };
})();
