/**
 * app.js — 主应用逻辑
 * 初始化画布、绑定 UI 事件、管理属性面板和 JSON 输出
 */
window.BurgerGame = window.BurgerGame || {};

(function () {
    'use strict';

    let canvas = null;
    let mode = 'free';            // 'free' | 'recipe'
    let selectedRecipeName = null;

    // 当前生菜配置面板指向的 layer（用于 mcp:tools-updated 事件刷新）
    let currentLettuceLayer = null;
    // 工具池缓存
    let _nativeToolsCache = null;
    let _mcpToolsCache = null;

    // =========================================================
    //  初始化
    // =========================================================
    function init() {
        canvas = new BurgerGame.BurgerCanvas('canvas-container');
        canvas.init();
        // 暴露给 chat.js 调用 highlightLayer
        BurgerGame.Canvas = canvas;

        bindSidebarEvents();
        bindServeButton();
        bindClearButton();
        bindCanvasCallbacks();
        bindModeToggle();
        bindRightPanelControls();
        bindSidebarDrawer();

        updateLayerCount(0);

        // 等配方数据就绪后渲染配方卡片 & 指南
        BurgerGame.Recipes.onReady(() => {
            renderRecipeGuide();
            renderRecipePicker();
            updateRecipeHint();
        });
    }

    // =========================================================
    //  模式切换（自由搭配 / 按配方）
    // =========================================================
    function bindModeToggle() {
        const freeBtn = document.getElementById('mode-free');
        const recipeBtn = document.getElementById('mode-recipe');
        if (!freeBtn || !recipeBtn) return;
        freeBtn.addEventListener('click', () => setMode('free'));
        recipeBtn.addEventListener('click', () => setMode('recipe'));
    }

    function setMode(newMode) {
        mode = newMode;
        const freeBtn = document.getElementById('mode-free');
        const recipeBtn = document.getElementById('mode-recipe');
        const freePanel = document.getElementById('panel-free');
        const recipePanel = document.getElementById('panel-recipe');
        if (freeBtn) freeBtn.classList.toggle('active', mode === 'free');
        if (recipeBtn) recipeBtn.classList.toggle('active', mode === 'recipe');
        if (freePanel) freePanel.style.display = mode === 'free' ? '' : 'none';
        if (recipePanel) recipePanel.style.display = mode === 'recipe' ? '' : 'none';
    }

    // =========================================================
    //  侧边栏食材按钮
    // =========================================================
    function bindSidebarEvents() {
        const cards = document.querySelectorAll('.ingredient-card');
        cards.forEach((card) => {
            card.addEventListener('click', () => {
                const type = card.dataset.type;
                if (type) {
                    canvas.addIngredient(type);
                    // 按钮点击反馈
                    card.style.transform = 'translateX(4px) scale(0.96)';
                    setTimeout(() => {
                        card.style.transform = '';
                    }, 150);
                    showToast(`已添加 ${BurgerGame.IngredientTypes[type].name}`, 'info');
                }
            });
        });
    }

    // =========================================================
    //  上菜按钮
    // =========================================================
    function bindServeButton() {
        const btn = document.getElementById('btn-serve');
        btn.addEventListener('click', () => {
            if (canvas.layers.length === 0) {
                showToast('请先添加一些食材！', 'error');
                return;
            }

            const json = canvas.exportJSON();

            // 位置验证失败，不继续
            if (!json.valid) {
                showToast(json.error, 'error');
                // 抖动按钮提示
                btn.classList.add('btn-shake');
                setTimeout(() => btn.classList.remove('btn-shake'), 500);
                return;
            }

            // 如果当前是"按配方"模式且选了配方，强制使用该 agent_type
            if (mode === 'recipe' && selectedRecipeName) {
                const recipe = BurgerGame.Recipes.getRecipe(selectedRecipeName);
                if (recipe) {
                    json.agent_type = recipe.name;
                    json.agent_label = recipe.label;
                    // 若配方有默认 cheese_prompt 且画布上没有芝士，注入默认
                    if (recipe.defaultConfig && recipe.defaultConfig.cheese_prompt) {
                        if (!canvas.layers.some((l) => l.meta.id === 'cheese')) {
                            json.cheese_prompt = recipe.defaultConfig.cheese_prompt;
                        }
                    }
                }
            }

            // 播放动画
            canvas.playServeAnimation(() => {
                // 显示 JSON
                showJSONPreview(json);
                showRightPanel();
                showToast(`🍔 ${json.agent_label} 搭建完成！跳转到聊天界面...`, 'success');

                // 切换到聊天视图
                setTimeout(() => {
                    BurgerGame.Chat.switchToChatView(json);
                }, 600);
            });
        });
    }

    // =========================================================
    //  清空按钮
    // =========================================================
    function bindClearButton() {
        const btn = document.getElementById('btn-clear');
        btn.addEventListener('click', () => {
            if (canvas.layers.length === 0) return;
            canvas.clearAll();
            hideRightPanel();
            clearJSONPreview();
            showToast('画布已清空', 'info');
        });
    }

    // =========================================================
    //  画布回调
    // =========================================================
    function bindCanvasCallbacks() {
        canvas.onSelectIngredient = (layer) => {
            showPropertyPanel(layer);
            showRightPanel();
        };

        canvas.onDeselectAll = () => {
            hidePropertyEditor();
        };

        canvas.onLayerCountChange = (count) => {
            updateLayerCount(count);
            updateRecipeHint();
        };
    }

    // =========================================================
    //  配方实时识别提示
    // =========================================================
    function updateRecipeHint() {
        const hintEl = document.getElementById('recipe-hint');
        if (!hintEl) return;

        const layerTypes = canvas.getLayerTypes();

        if (layerTypes.length === 0) {
            hintEl.innerHTML = '';
            hintEl.className = 'recipe-hint recipe-hint-empty';
            renderRecipeScenePanel(null);
            return;
        }

        // 先做结构校验
        const validation = BurgerGame.Recipes.validateStructure(layerTypes);
        if (!validation.valid) {
            hintEl.innerHTML = `<span class="recipe-icon">⚠️</span>
                <span class="recipe-info">
                    <span class="recipe-label">结构问题</span>
                    <span class="recipe-desc">${validation.error.replace('❌ ', '')}</span>
                </span>`;
            hintEl.className = 'recipe-hint recipe-hint-warn';
            renderRecipeScenePanel(null);
            return;
        }

        // 配方匹配
        const recipe = BurgerGame.Recipes.matchRecipe(layerTypes);
        if (recipe) {
            const scene = recipe.scene || {};
            hintEl.innerHTML = `<span class="recipe-icon">${recipe.emoji}</span>
                <span class="recipe-info">
                    <span class="recipe-name-tag">识别到配方 · ${escapeHtml(scene.badge || '标准')}</span>
                    <span class="recipe-label">${recipe.label}</span>
                    <span class="recipe-desc">${escapeHtml(scene.focus || recipe.description || '')}</span>
                </span>`;
            hintEl.className = 'recipe-hint recipe-hint-match';
            renderRecipeScenePanel(recipe);
            if (canvas.setRecipe) canvas.setRecipe(recipe);
        } else {
            hintEl.innerHTML = `<span class="recipe-icon">🔍</span>
                <span class="recipe-info">
                    <span class="recipe-label">未知配方</span>
                    <span class="recipe-desc">当前食材组合不在已知配方中，仍可尝试构建</span>
                </span>`;
            hintEl.className = 'recipe-hint recipe-hint-unknown';
            renderRecipeScenePanel(null);
            if (canvas.setRecipe) canvas.setRecipe(null);
        }
    }

    function renderRecipeScenePanel(recipe) {
        const panel = document.getElementById('recipe-scene-panel');
        if (!panel) return;
        if (!recipe) {
            panel.innerHTML = '';
            panel.className = 'recipe-scene-panel recipe-scene-panel-hidden';
            return;
        }

        const scene = recipe.scene || {};
        const rolesHTML = renderRoleBadges(scene.roles || [], 'scene-role');
        const stagesHTML = renderStagePills(scene.stages || [], 'scene-stage');
        const samples = (scene.sample_prompts || []).slice(0, 2);
        const samplesHTML = samples.map((sample) => `<span class="scene-sample">${escapeHtml(sample)}</span>`).join('');

        panel.innerHTML = `
            <div class="scene-panel-head">
                <div>
                    <div class="scene-panel-kicker">当前组合如何协作</div>
                    <div class="scene-panel-title">${recipe.emoji} ${escapeHtml(recipe.label)}</div>
                </div>
                <span class="scene-mode-badge">${escapeHtml(scene.badge || '标准')}</span>
            </div>
            <div class="scene-panel-focus">${escapeHtml(scene.focus || recipe.description || '')}</div>
            ${rolesHTML ? `<div class="scene-role-row">${rolesHTML}</div>` : ''}
            ${stagesHTML ? `<div class="scene-stage-row">${stagesHTML}</div>` : ''}
            ${samplesHTML ? `<div class="scene-sample-row">${samplesHTML}</div>` : ''}
        `;
        panel.className = 'recipe-scene-panel';
    }

    // =========================================================
    //  属性面板
    // =========================================================
    function showPropertyPanel(layer) {
        const panel = document.getElementById('property-editor');
        const title = document.getElementById('prop-title');
        const content = document.getElementById('prop-content');

        // 清空
        content.innerHTML = '';

        const meta = layer.meta;
        title.textContent = `${meta.emoji} ${meta.name} 属性`;

        if (!meta.configurable) {
            content.innerHTML = `
                <div style="color: var(--text-muted); font-size: 0.85rem; padding: 12px 0;">
                    此食材无可配置项
                </div>`;
            panel.style.display = 'block';
            return;
        }

        // 根据类型生成编辑面板
        if (meta.id === 'cheese') {
            content.innerHTML = `
                <div class="prop-group">
                    <label>系统提示词 (System Prompt)</label>
                    <textarea id="prop-cheese-prompt" rows="4" placeholder="例如：你是一个幽默的脱口秀演员...">${layer.config.prompt || ''}</textarea>
                </div>`;
            // 绑定输入
            setTimeout(() => {
                const ta = document.getElementById('prop-cheese-prompt');
                ta.addEventListener('input', () => {
                    layer.config.prompt = ta.value;
                });
            }, 10);
        }

        if (meta.id === 'meat_patty') {
            const models = [
                { value: 'qwen-plus', label: 'Qwen-Plus (默认推荐)' },
                { value: 'qwen-max', label: 'Qwen-Max (最强模型)' },
                { value: 'qwen-turbo', label: 'Qwen-Turbo (极速模型)' },
            ];
            const optionsHtml = models
                .map((m) => `<option value="${m.value}" ${layer.config.model === m.value ? 'selected' : ''}>${m.label}</option>`)
                .join('');
            content.innerHTML = `
                <div class="prop-group">
                    <label>大语言模型选择</label>
                    <select id="prop-meat-model">${optionsHtml}</select>
                </div>`;
            setTimeout(() => {
                const sel = document.getElementById('prop-meat-model');
                sel.addEventListener('change', () => {
                    layer.config.model = sel.value;
                });
            }, 10);
        }

        if (meta.id === 'lettuce') {
            currentLettuceLayer = layer;
            renderLettuceConfig(content, layer);
        }

        panel.style.display = 'block';
    }

    // =========================================================
    //  生菜配置：原生工具 + MCP 工具分组
    // =========================================================
    async function renderLettuceConfig(content, layer) {
        const cfg = layer.config = layer.config || {};
        cfg.tools = Array.isArray(cfg.tools) ? cfg.tools : [];
        cfg.mcp_tools = Array.isArray(cfg.mcp_tools) ? cfg.mcp_tools : [];

        content.innerHTML = `
            <div class="prop-group">
                <label>🥗 原生工具</label>
                <div class="tool-checkbox-group" id="prop-native-tools">
                    <div style="color:var(--text-muted);font-size:12px;">加载中...</div>
                </div>
            </div>
            <div class="prop-group">
                <label>🔌 MCP 工具（已发现）</label>
                <div class="mcp-tool-groups" id="prop-mcp-tools">
                    <div style="color:var(--text-muted);font-size:12px;">加载中...</div>
                </div>
            </div>`;

        try {
            const [nativeRes, mcpRes] = await Promise.all([
                fetch('/api/tools/native').then((r) => r.json()),
                fetch('/api/mcp/tools').then((r) => r.json()),
            ]);
            _nativeToolsCache = nativeRes.tools || [];
            _mcpToolsCache = mcpRes.tools || [];
        } catch (err) {
            console.error('[Lettuce] 加载工具列表失败', err);
            _nativeToolsCache = _nativeToolsCache || [];
            _mcpToolsCache = _mcpToolsCache || [];
        }

        // 原生工具
        const nativeBox = document.getElementById('prop-native-tools');
        if (nativeBox) {
            if (_nativeToolsCache.length === 0) {
                nativeBox.innerHTML = '<div style="color:var(--text-muted);font-size:12px;">无可用原生工具</div>';
            } else {
                nativeBox.innerHTML = _nativeToolsCache.map((t) => {
                    const checked = cfg.tools.includes(t.name) ? 'checked' : '';
                    const desc = t.description ? `<span class="tool-desc"> · ${escapeHtml(t.description)}</span>` : '';
                    return `<label><input type="checkbox" data-name="${escapeAttr(t.name)}" ${checked}> <code>${escapeHtml(t.name)}</code>${desc}</label>`;
                }).join('');
                nativeBox.querySelectorAll('input[type="checkbox"]').forEach((cb) => {
                    cb.addEventListener('change', () => {
                        const set = new Set(cfg.tools);
                        if (cb.checked) set.add(cb.dataset.name); else set.delete(cb.dataset.name);
                        cfg.tools = Array.from(set);
                    });
                });
            }
        }

        // MCP 工具按 server_id 分组
        const mcpBox = document.getElementById('prop-mcp-tools');
        if (mcpBox) {
            if (_mcpToolsCache.length === 0) {
                mcpBox.innerHTML = `
                    <div class="mcp-empty-hint">
                        尚未发现任何 MCP 工具。<br>
                        <a href="#" id="prop-open-mcp-market">🔌 前往 MCP 工具市场</a> 安装并发现工具。
                    </div>`;
                const link = document.getElementById('prop-open-mcp-market');
                if (link) {
                    link.addEventListener('click', (e) => {
                        e.preventDefault();
                        if (BurgerGame.MCPMarket) BurgerGame.MCPMarket.togglePanel();
                    });
                }
            } else {
                // 分组
                const groups = {};
                _mcpToolsCache.forEach((t) => {
                    if (!groups[t.server_id]) groups[t.server_id] = {
                        emoji: t.server_emoji || '🔌',
                        name: t.server_name || t.server_id,
                        tools: [],
                    };
                    groups[t.server_id].tools.push(t);
                });
                const selectedKey = (sid, tname) => `${sid}::${tname}`;
                const selectedSet = new Set(
                    cfg.mcp_tools.map((m) => selectedKey(m.server_id, m.tool_name))
                );
                mcpBox.innerHTML = Object.keys(groups).map((sid) => {
                    const g = groups[sid];
                    const items = g.tools.map((t) => {
                        const key = selectedKey(sid, t.tool_name);
                        const checked = selectedSet.has(key) ? 'checked' : '';
                        const desc = t.description ? `<span class="tool-desc"> · ${escapeHtml(t.description)}</span>` : '';
                        return `<label><input type="checkbox" data-sid="${escapeAttr(sid)}" data-tname="${escapeAttr(t.tool_name)}" ${checked}> <code>${escapeHtml(t.tool_name)}</code>${desc}</label>`;
                    }).join('');
                    return `<div class="mcp-tool-group">
                        <div class="mcp-tool-group-header">${g.emoji} ${escapeHtml(g.name)} <span class="mcp-server-id">(${escapeHtml(sid)})</span></div>
                        <div class="tool-checkbox-group">${items}</div>
                    </div>`;
                }).join('');
                mcpBox.querySelectorAll('input[type="checkbox"]').forEach((cb) => {
                    cb.addEventListener('change', () => {
                        const sid = cb.dataset.sid;
                        const tname = cb.dataset.tname;
                        const key = selectedKey(sid, tname);
                        const map = new Map(
                            cfg.mcp_tools.map((m) => [selectedKey(m.server_id, m.tool_name), m])
                        );
                        if (cb.checked) map.set(key, { server_id: sid, tool_name: tname });
                        else map.delete(key);
                        cfg.mcp_tools = Array.from(map.values());
                    });
                });
            }
        }
    }

    function escapeHtml(s) {
        const d = document.createElement('div');
        d.textContent = s == null ? '' : String(s);
        return d.innerHTML;
    }

    function escapeAttr(s) {
        return escapeHtml(s).replace(/"/g, '&quot;');
    }

    function hidePropertyEditor() {
        const panel = document.getElementById('property-editor');
        panel.style.display = 'none';
        currentLettuceLayer = null;
    }

    // 跨面板事件：MCP 工具市场发现/卸载后刷新生菜配置
    window.addEventListener('mcp:tools-updated', () => {
        _mcpToolsCache = null; // 强制重拉
        if (currentLettuceLayer) {
            const content = document.getElementById('prop-content');
            if (content) renderLettuceConfig(content, currentLettuceLayer);
        }
    });

    function bindRightPanelControls() {
        const closeBtn = document.getElementById('right-panel-close');
        if (closeBtn) {
            closeBtn.addEventListener('click', hideRightPanel);
        }

        window.addEventListener('keydown', (event) => {
            if (event.key === 'Escape') {
                hideRightPanel();
            }
        });
    }

    // =========================================================
    //  右侧面板显示/隐藏
    // =========================================================
    function showRightPanel() {
        const panel = document.getElementById('right-panel');
        if (panel) panel.classList.add('visible');
    }

    function hideRightPanel() {
        const panel = document.getElementById('right-panel');
        if (panel) panel.classList.remove('visible');
    }

    // =========================================================
    //  JSON 预览
    // =========================================================
    function showJSONPreview(json) {
        const el = document.getElementById('json-output');
        el.textContent = JSON.stringify(json, null, 2);
    }

    function clearJSONPreview() {
        const el = document.getElementById('json-output');
        el.textContent = '';
    }

    // =========================================================
    //  图层计数
    // =========================================================
    function updateLayerCount(count) {
        const el = document.getElementById('layer-count');
        if (el) {
            el.innerHTML = `<span class="lc-label">层数</span><strong>${count}</strong>`;
        }
        // 控制上菜按钮状态
        const btn = document.getElementById('btn-serve');
        if (btn) btn.disabled = count === 0;
    }

    // =========================================================
    //  侧边栏抽屉（移动端）
    // =========================================================
    function bindSidebarDrawer() {
        const app = document.getElementById('build-view');
        const toggleBtn = document.getElementById('btn-toggle-sidebar');
        const closeBtn = document.getElementById('sidebar-close');
        const backdrop = document.getElementById('sidebar-backdrop');
        if (!app) return;

        const open = () => app.classList.add('sidebar-open');
        const close = () => app.classList.remove('sidebar-open');
        const toggle = () => app.classList.toggle('sidebar-open');

        if (toggleBtn) toggleBtn.addEventListener('click', toggle);
        if (closeBtn) closeBtn.addEventListener('click', close);
        if (backdrop) backdrop.addEventListener('click', close);

        // 点击食材卡片后自动收起抽屉（仅在小屏上会显示抽屉形态）
        document.addEventListener('click', (event) => {
            const target = event.target;
            if (!target || !target.closest) return;
            if (target.closest('.ingredient-card, .recipe-picker-card')) {
                if (window.matchMedia('(max-width: 960px)').matches) close();
            }
        });

        // Esc 关闭抽屉
        window.addEventListener('keydown', (event) => {
            if (event.key === 'Escape') close();
        });

        // 同步顶栏高度（顶栏在小屏上可能换行变高）
        const topbar = document.querySelector('.app-topbar');
        if (topbar) {
            const syncHeight = () => {
                const h = topbar.getBoundingClientRect().height;
                document.documentElement.style.setProperty('--topbar-h', h + 'px');
            };
            syncHeight();
            window.addEventListener('resize', syncHeight);
            if (window.ResizeObserver) {
                new ResizeObserver(syncHeight).observe(topbar);
            }
        }
    }

    // =========================================================
    //  配方指南 / 配方选择器（数据源：后端 /api/recipes）
    // =========================================================
    function renderRecipeGuide() {
        const el = document.getElementById('recipe-guide-list');
        if (!el) return;
        const recipes = BurgerGame.Recipes.getAllRecipes();
        if (!recipes.length) {
            el.innerHTML = '<div style="color:var(--text-muted);font-size:0.8rem;">（配方加载中...）</div>';
            return;
        }
        el.innerHTML = recipes.map((r) => {
            const scene = r.scene || {};
            const caps = r.capabilities || {};
            const capsHtml = [
                caps.checkpoint ? '<span class="rg-cap">💾</span>' : '',
                caps.streaming ? '<span class="rg-cap">🌊</span>' : '',
                caps.hitl ? '<span class="rg-cap">🛡️</span>' : '',
            ].join('');
            const layerDesc = (r.canvasLayers || []).map(layerLabel).join(' ＋ ');
            const rolesHTML = renderRoleBadges(scene.roles || [], 'rg-role');
            const stagesHTML = renderStagePills(scene.stages || [], 'rg-stage');
            const sample = ((scene.sample_prompts || [])[0]) || '';
            return `
                <div class="recipe-guide-item ${scene.group === 'core' ? 'recipe-guide-item-core' : ''}">
                    <div class="rg-head">
                        <span class="rg-emoji">${r.emoji}</span>
                        <span class="rg-content">
                            <strong>${escapeHtml(r.label)} <span class="rg-badge">${escapeHtml(scene.badge || '标准')}</span> ${capsHtml}</strong>
                            <span class="rg-focus">${escapeHtml(scene.focus || r.description || '')}</span>
                        </span>
                    </div>
                    ${stagesHTML ? `<div class="rg-stage-row">${stagesHTML}</div>` : ''}
                    ${rolesHTML ? `<div class="rg-role-row">${rolesHTML}</div>` : ''}
                    <div class="rg-layerline">食材：${escapeHtml(layerDesc)}</div>
                    ${sample ? `<div class="rg-sample">例如：${escapeHtml(sample)}</div>` : ''}
                </div>`;
        }).join('');
    }

    function renderRecipePicker() {
        const el = document.getElementById('recipe-picker-list');
        if (!el) return;
        const recipes = BurgerGame.Recipes.getAllRecipes();
        if (!recipes.length) {
            el.innerHTML = '<div style="color:var(--text-muted);font-size:0.85rem;padding:12px;">（配方加载失败）</div>';
            return;
        }
        el.innerHTML = recipes.map((r) => {
            const scene = r.scene || {};
            const caps = r.capabilities || {};
            const capChips = [
                caps.checkpoint ? '<span class="rp-cap" title="多轮记忆">💾</span>' : '',
                caps.streaming ? '<span class="rp-cap" title="流式输出">🌊</span>' : '',
                caps.hitl ? '<span class="rp-cap" title="人类审批">🛡️</span>' : '',
            ].join('');
            const stagesHTML = renderStagePills(scene.stages || [], 'rp-stage');
            const rolesHTML = renderRoleBadges(scene.roles || [], 'rp-role');
            const sample = ((scene.sample_prompts || [])[0]) || '';
            const layerDesc = (r.canvasLayers || []).map(layerLabel).join(' ＋ ');
            return `
                <button class="recipe-picker-card ${scene.group === 'core' ? 'recipe-picker-core' : ''}" data-name="${r.name}">
                    <div class="rp-head">
                        <span class="rp-emoji">${r.emoji}</span>
                        <span class="rp-label">${escapeHtml(r.label)}</span>
                        <span class="rp-badge">${escapeHtml(scene.badge || '标准')}</span>
                        <span class="rp-caps">${capChips}</span>
                    </div>
                    <div class="rp-focus">${escapeHtml(scene.focus || r.description || '')}</div>
                    ${stagesHTML ? `<div class="rp-stage-row">${stagesHTML}</div>` : ''}
                    ${rolesHTML ? `<div class="rp-role-row">${rolesHTML}</div>` : ''}
                    <div class="rp-desc">食材：${escapeHtml(layerDesc)}</div>
                    ${sample ? `<div class="rp-sample">例如：${escapeHtml(sample)}</div>` : ''}
                </button>`;
        }).join('');

        el.querySelectorAll('.recipe-picker-card').forEach((btn) => {
            btn.addEventListener('click', () => {
                const name = btn.dataset.name;
                applyRecipe(name);
                el.querySelectorAll('.recipe-picker-card').forEach((b) => b.classList.toggle('selected', b === btn));
            });
        });
    }

    function applyRecipe(name) {
        const r = BurgerGame.Recipes.getRecipe(name);
        if (!r) return;
        selectedRecipeName = name;
        canvas.loadRecipeLayers(r.canvasLayers || []);
        applyRecipeDefaults(r);
        showToast(`已应用配方：${r.emoji} ${r.label}`, 'info');
    }

    function applyRecipeDefaults(recipe) {
        const defaults = (recipe && recipe.defaultConfig) || {};
        const layerCount = (recipe && recipe.canvasLayers && recipe.canvasLayers.length) || 0;
        const delay = Math.max(300, layerCount * 100 + 120);

        setTimeout(() => {
            canvas.layers.forEach((layer) => {
                if (layer.meta.id === 'lettuce' && (!layer.config.tools || !layer.config.tools.length)) {
                    layer.config.tools = (defaults.default_tools || ['get_weather', 'calculate_add']).slice();
                }
                if (layer.meta.id === 'cheese' && defaults.cheese_prompt && !layer.config.prompt) {
                    layer.config.prompt = defaults.cheese_prompt;
                }
                if (layer.meta.id === 'meat_patty' && !layer.config.model) {
                    layer.config.model = 'qwen-plus';
                }
            });
        }, delay);
    }

    function layerLabel(id) {
        const meta = BurgerGame.IngredientTypes && BurgerGame.IngredientTypes[id];
        return meta ? meta.name : id;
    }

    function renderStagePills(stages, baseClass) {
        return (stages || []).map((stage) => `
            <span class="${baseClass}" data-actor="${escapeHtml(stage.actor || '')}">${escapeHtml(stage.label || stage.key || '')}</span>
        `).join('');
    }

    function renderRoleBadges(roles, baseClass) {
        return (roles || []).map((role) => `
            <span class="${baseClass} ${role.active ? 'is-active' : 'is-muted'}" data-role="${escapeHtml(role.key || '')}">${escapeHtml(role.label || role.key || '')}</span>
        `).join('');
    }

    function escapeHtml(str) {
        const div = document.createElement('div');
        div.textContent = str == null ? '' : String(str);
        return div.innerHTML;
    }

    // =========================================================
    //  Toast 通知
    // =========================================================
    function showToast(message, type) {
        const toast = document.getElementById('toast');
        toast.textContent = message;
        toast.className = 'toast ' + type;

        // 触发动画
        requestAnimationFrame(() => {
            toast.classList.add('visible');
        });

        clearTimeout(toast._timer);
        toast._timer = setTimeout(() => {
            toast.classList.remove('visible');
        }, 2500);
    }

    // =========================================================
    //  启动
    // =========================================================
    window.addEventListener('DOMContentLoaded', init);

    BurgerGame.showToast = showToast;
})();
