/**
 * app.js — 主应用逻辑
 * 初始化画布、绑定 UI 事件、管理属性面板和 JSON 输出
 */
window.BurgerGame = window.BurgerGame || {};

(function () {
    'use strict';

    let canvas = null;

    // =========================================================
    //  初始化
    // =========================================================
    function init() {
        canvas = new BurgerGame.BurgerCanvas('canvas-container');
        canvas.init();

        bindSidebarEvents();
        bindServeButton();
        bindClearButton();
        bindCanvasCallbacks();

        // 默认隐藏右侧面板 (通过 CSS class)
        updateLayerCount(0);
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

            // 播放动画
            canvas.playServeAnimation(() => {
                // 显示 JSON
                showJSONPreview(json);
                showRightPanel();
                showToast('🍔 汉堡搭建完成！跳转到聊天界面...', 'success');

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
        };
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
            const tools = [
                { value: 'calculate_add', label: '🧮 加法计算器 (Calculator)' },
                { value: 'get_weather', label: '🌤️ 天气查询 (Weather API)' },
            ];
            const checksHtml = tools
                .map((t) => {
                    const checked = (layer.config.tools || []).includes(t.value) ? 'checked' : '';
                    return `<label><input type="checkbox" value="${t.value}" ${checked}> ${t.label}</label>`;
                })
                .join('');
            content.innerHTML = `
                <div class="prop-group">
                    <label>工具挂载 (Tools)</label>
                    <div class="tool-checkbox-group" id="prop-lettuce-tools">${checksHtml}</div>
                </div>`;
            setTimeout(() => {
                const group = document.getElementById('prop-lettuce-tools');
                group.querySelectorAll('input[type="checkbox"]').forEach((cb) => {
                    cb.addEventListener('change', () => {
                        const checked = [];
                        group.querySelectorAll('input[type="checkbox"]:checked').forEach((c) => {
                            checked.push(c.value);
                        });
                        layer.config.tools = checked;
                    });
                });
            }, 10);
        }

        panel.style.display = 'block';
    }

    function hidePropertyEditor() {
        const panel = document.getElementById('property-editor');
        panel.style.display = 'none';
    }

    // =========================================================
    //  右侧面板显示/隐藏
    // =========================================================
    function showRightPanel() {
        document.getElementById('right-panel').classList.add('visible');
    }

    function hideRightPanel() {
        document.getElementById('right-panel').classList.remove('visible');
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
            el.innerHTML = `当前层数: <strong>${count}</strong>`;
        }
        // 控制上菜按钮状态
        const btn = document.getElementById('btn-serve');
        btn.disabled = count === 0;
    }

    // sendToBackend 已迁移到 chat.js 中处理

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
