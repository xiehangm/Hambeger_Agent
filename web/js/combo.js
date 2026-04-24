/**
 * combo.js — 🍱 汉堡套餐工坊（LangGraph 工作流可视化搭建器）
 *
 * 职责：
 *   - 渲染 5 种工作流模式的画布模板（slots + SVG 连线）
 *   - 渲染已保存汉堡库（从 /api/burgers）
 *   - 点击槽位 / 选中汉堡完成绑定
 *   - 右栏编辑套餐级别属性（路由 prompt / 评委标准 / max_iterations 等）
 *   - 「上菜运行」→ /api/combo/build → 弹出聊天抽屉 → /api/combo/chat/stream
 *   - 「保存套餐」→ /api/combos
 */
window.BurgerGame = window.BurgerGame || {};

(function () {
    'use strict';

    // 模式模板：每个模式定义画布节点布局 + 连线 + 默认配置
    const PATTERNS = {
        chain: {
            label: '串联套餐 · Prompt Chaining',
            icon: '🧵',
            desc: 'N 个汉堡按顺序协作，上一个的输出作为下一个的输入',
            slots: 3,
            layout: (n) => {
                // 水平链式，等间距
                const gap = 230;
                return Array.from({ length: n }, (_, i) => ({
                    id: `s${i + 1}`,
                    role: 'burger',
                    title: `步骤 ${i + 1}`,
                    x: 40 + i * gap,
                    y: 120,
                }));
            },
            edges: (slots) => slots.slice(0, -1).map((s, i) => ({ from: s.id, to: slots[i + 1].id })),
            defaultConfig: () => ({ steps: [] }),
            buildConfig: (state) => ({
                steps: state.slots.map(s => ({ node_id: s.id, burger_id: s.burger_id })).filter(x => x.burger_id),
            }),
            validate: (state) => state.slots.every(s => s.burger_id) ? null : '请为每个步骤选择一个汉堡',
        },
        routing: {
            label: '分流套餐 · Routing',
            icon: '🔀',
            desc: '路由器根据意图把请求分发到不同汉堡',
            slots: 3,
            layout: (n) => {
                const arr = [{ id: 'router', role: 'router', title: '🔀 路由器', x: 40, y: 160 }];
                for (let i = 0; i < n; i++) {
                    arr.push({
                        id: `route_${i + 1}`,
                        role: 'burger',
                        title: `分支 ${i + 1}`,
                        route_key: `branch_${i + 1}`,
                        route_label: `分支 ${i + 1}`,
                        route_desc: '',
                        x: 340,
                        y: 40 + i * 130,
                    });
                }
                return arr;
            },
            edges: (slots) => slots.filter(s => s.role === 'burger').map(s => ({ from: 'router', to: s.id })),
            defaultConfig: () => ({ routes: [], router_system: '' }),
            buildConfig: (state) => ({
                router_system: state.routerSystem || '',
                routes: state.slots.filter(s => s.role === 'burger').map(s => ({
                    key: s.route_key,
                    label: s.route_label,
                    description: s.route_desc || '',
                    node_id: s.id,
                    burger_id: s.burger_id,
                })).filter(r => r.burger_id),
            }),
            validate: (state) => {
                const routes = state.slots.filter(s => s.role === 'burger');
                if (!routes.every(r => r.burger_id)) return '每个分支都需要绑定一个汉堡';
                if (!routes.every(r => r.route_key)) return '每个分支必须有唯一 key';
                return null;
            },
        },
        parallel: {
            label: '拼盘套餐 · Parallelization',
            icon: '🎨',
            desc: '多个汉堡并行执行，最后聚合结果',
            slots: 3,
            layout: (n) => {
                const arr = [];
                for (let i = 0; i < n; i++) {
                    arr.push({ id: `b${i + 1}`, role: 'burger', title: `并行 ${i + 1}`, x: 40 + i * 230, y: 60 });
                }
                arr.push({ id: 'agg', role: 'aggregator', title: '🎨 聚合器', x: 40 + Math.floor((n - 1) / 2) * 230, y: 240 });
                return arr;
            },
            edges: (slots) => {
                const agg = slots.find(s => s.role === 'aggregator');
                return slots.filter(s => s.role === 'burger').map(s => ({ from: s.id, to: agg.id }));
            },
            defaultConfig: () => ({ branches: [], aggregate_template: '' }),
            buildConfig: (state) => ({
                aggregate_template: state.aggregateTemplate || '',
                branches: state.slots.filter(s => s.role === 'burger')
                    .map(s => ({ node_id: s.id, burger_id: s.burger_id }))
                    .filter(x => x.burger_id),
            }),
            validate: (state) => state.slots.filter(s => s.role === 'burger').every(s => s.burger_id)
                ? null : '每个并行分支都需要绑定一个汉堡',
        },
        orchestrator: {
            label: '主厨套餐 · Orchestrator-Worker',
            icon: '👨‍🍳',
            desc: '主厨 LLM 规划子任务，动态派生 worker 汉堡执行',
            slots: 1,
            layout: () => [
                { id: 'orch', role: 'orchestrator', title: '👨‍🍳 主厨（规划）', x: 40, y: 160 },
                { id: 'worker', role: 'burger', title: '🧑‍🍳 工人汉堡', x: 320, y: 80 },
                { id: 'synth', role: 'synthesizer', title: '📋 综合', x: 600, y: 160 },
            ],
            edges: () => [
                { from: 'orch', to: 'worker', dashed: true, label: 'Send()' },
                { from: 'worker', to: 'synth' },
            ],
            defaultConfig: () => ({ worker: {}, max_sections: 3, orchestrator: { system: '' } }),
            buildConfig: (state) => {
                const worker = state.slots.find(s => s.id === 'worker');
                return {
                    max_sections: +state.maxSections || 3,
                    orchestrator: { system: state.orchSystem || '' },
                    worker: { node_id: 'worker', burger_id: worker && worker.burger_id },
                };
            },
            validate: (state) => {
                const w = state.slots.find(s => s.id === 'worker');
                return (w && w.burger_id) ? null : '请为工人汉堡绑定一个汉堡';
            },
        },
        evaluator: {
            label: '评委套餐 · Evaluator-Optimizer',
            icon: '⚖️',
            desc: '生成汉堡产出 → 评委 LLM 评价 → 未通过则携带反馈重试',
            slots: 1,
            layout: () => [
                { id: 'gen', role: 'burger', title: '✍️ 生成汉堡', x: 40, y: 160 },
                { id: 'eval', role: 'evaluator', title: '⚖️ 评委', x: 340, y: 160 },
                { id: 'accept', role: 'end', title: '✅ 通过 → 结束', x: 640, y: 80 },
                { id: 'retry', role: 'retry', title: '🔁 重试 (携带反馈)', x: 640, y: 240 },
            ],
            edges: () => [
                { from: 'gen', to: 'eval' },
                { from: 'eval', to: 'accept', label: 'accept' },
                { from: 'eval', to: 'retry', label: 'retry', dashed: true },
                { from: 'retry', to: 'gen', dashed: true },
            ],
            defaultConfig: () => ({ generator: {}, evaluator: { criteria: '' }, max_iterations: 3 }),
            buildConfig: (state) => {
                const gen = state.slots.find(s => s.id === 'gen');
                return {
                    generator: { node_id: 'gen', burger_id: gen && gen.burger_id },
                    evaluator: { criteria: state.criteria || '' },
                    max_iterations: +state.maxIter || 3,
                };
            },
            validate: (state) => {
                const g = state.slots.find(s => s.id === 'gen');
                return (g && g.burger_id) ? null : '请为生成汉堡绑定一个汉堡';
            },
        },
    };

    // 控制器状态
    const state = {
        pattern: null,
        slots: [],
        burgers: [],       // 已保存的汉堡列表
        selectedBurger: null,
        threadId: null,
        // 模式专属配置字段
        routerSystem: '',
        aggregateTemplate: '',
        orchSystem: '',
        maxSections: 3,
        criteria: '回答应当清晰、准确、切题，并且语言流畅。',
        maxIter: 2,
        name: '',
        combo_id: null,
    };

    let els = {};

    function cacheEls() {
        els = {
            view: document.getElementById('combo-view'),
            patternList: document.getElementById('combo-pattern-list'),
            burgerList: document.getElementById('combo-burger-list'),
            savedList: document.getElementById('combo-saved-list'),
            canvas: document.getElementById('combo-canvas'),
            patternBadge: document.getElementById('combo-pattern-badge'),
            nameInput: document.getElementById('combo-name-input'),
            props: document.getElementById('combo-props'),
            runBtn: document.getElementById('combo-run-btn'),
            saveBtn: document.getElementById('combo-save-btn'),
            backBtn: document.getElementById('combo-back-btn'),
            drawer: document.getElementById('combo-chat-drawer'),
            drawerClose: document.getElementById('combo-chat-close'),
            trace: document.getElementById('combo-chat-trace'),
            msgs: document.getElementById('combo-chat-msgs'),
            chatInput: document.getElementById('combo-chat-input'),
            chatSend: document.getElementById('combo-chat-send'),
        };
    }

    function show() {
        if (!els.view) cacheEls();
        const buildView = document.getElementById('build-view');
        const chatView = document.getElementById('chat-view');
        if (buildView) buildView.classList.add('view-hidden');
        if (chatView) chatView.classList.remove('view-visible');
        els.view.classList.add('view-visible');
        refresh();
    }

    function hide() {
        if (!els.view) cacheEls();
        els.view.classList.remove('view-visible');
        const buildView = document.getElementById('build-view');
        if (buildView) buildView.classList.remove('view-hidden');
    }

    function renderPatternList() {
        const entries = Object.entries(PATTERNS);
        els.patternList.innerHTML = entries.map(([k, p]) => `
            <div class="combo-pattern-card ${state.pattern === k ? 'active' : ''}" data-pattern="${k}">
                <div><span class="cp-icon">${p.icon}</span><span class="cp-name">${p.label}</span></div>
                <div class="cp-desc">${p.desc}</div>
            </div>
        `).join('');
        els.patternList.querySelectorAll('[data-pattern]').forEach(el => {
            el.addEventListener('click', () => selectPattern(el.dataset.pattern));
        });
    }

    function selectPattern(kind) {
        if (state.pattern === kind) return;
        state.pattern = kind;
        const p = PATTERNS[kind];
        const layout = p.layout(p.slots);
        state.slots = layout.map(l => ({ ...l }));
        // 重置模式专属字段
        Object.assign(state, p.defaultConfig());
        renderPatternList();
        renderCanvas();
        renderProps();
        els.patternBadge.textContent = p.label;
    }

    function renderCanvas() {
        const wrap = els.canvas;
        wrap.innerHTML = '';
        if (!state.pattern) {
            wrap.innerHTML = '<div class="combo-placeholder">← 从左侧选择一种工作流模式</div>';
            return;
        }
        const p = PATTERNS[state.pattern];

        // 计算 svg 尺寸
        const maxX = Math.max(...state.slots.map(s => s.x)) + 220;
        const maxY = Math.max(...state.slots.map(s => s.y)) + 140;
        const svgNS = 'http://www.w3.org/2000/svg';
        const svg = document.createElementNS(svgNS, 'svg');
        svg.classList.add('combo-edges');
        svg.setAttribute('width', maxX);
        svg.setAttribute('height', maxY);
        svg.style.minWidth = maxX + 'px';
        svg.style.minHeight = maxY + 'px';

        // 箭头
        const defs = document.createElementNS(svgNS, 'defs');
        defs.innerHTML = `<marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
            <path d="M 0 0 L 10 5 L 0 10 z" fill="rgba(255,154,60,0.8)"/></marker>`;
        svg.appendChild(defs);

        const edges = p.edges(state.slots);
        const byId = Object.fromEntries(state.slots.map(s => [s.id, s]));
        edges.forEach(e => {
            const a = byId[e.from], b = byId[e.to];
            if (!a || !b) return;
            const x1 = a.x + 95, y1 = a.y + 50;
            const x2 = b.x + 95, y2 = b.y + 50;
            const midX = (x1 + x2) / 2;
            const path = document.createElementNS(svgNS, 'path');
            path.setAttribute('d', `M ${x1} ${y1} C ${midX} ${y1}, ${midX} ${y2}, ${x2} ${y2}`);
            path.setAttribute('marker-end', 'url(#arrow)');
            if (e.dashed) path.setAttribute('stroke-dasharray', '6 4');
            svg.appendChild(path);
            if (e.label) {
                const t = document.createElementNS(svgNS, 'text');
                t.textContent = e.label;
                t.setAttribute('x', midX);
                t.setAttribute('y', (y1 + y2) / 2 - 6);
                t.setAttribute('fill', 'rgba(255,200,140,0.8)');
                t.setAttribute('font-size', '10');
                t.setAttribute('text-anchor', 'middle');
                svg.appendChild(t);
            }
        });
        wrap.appendChild(svg);

        // slots
        state.slots.forEach(slot => {
            const el = document.createElement('div');
            el.className = 'combo-slot ' + (slot.burger_id ? 'filled' : '');
            if (slot.role !== 'burger') el.classList.add('combo-slot-special');
            el.dataset.slotId = slot.id;
            el.style.left = slot.x + 'px';
            el.style.top = slot.y + 'px';

            let bodyHTML = '';
            if (slot.role === 'burger') {
                if (slot.burger_id) {
                    const b = state.burgers.find(x => x.burger_id === slot.burger_id);
                    bodyHTML = b ? `<div><strong>${escapeHtml(b.name)}</strong></div><div class="slot-meta">${b.agent_type || ''}</div>` : `<div class="slot-empty">汉堡不存在: ${slot.burger_id}</div>`;
                } else {
                    bodyHTML = '<div class="slot-empty">点击选中 ← 然后点左侧菜品卡</div>';
                }
            } else {
                const descMap = {
                    router: 'LLM 结构化输出选择下游',
                    aggregator: '合并所有并行输出',
                    orchestrator: '主厨 LLM 拆分 sections → Send()',
                    synthesizer: '综合工人输出为最终报告',
                    evaluator: 'LLM 评判 good / bad → 路由',
                    end: '终止节点',
                    retry: '把评委反馈注入下一轮',
                };
                bodyHTML = `<div class="slot-empty">${descMap[slot.role] || ''}</div>`;
            }

            el.innerHTML = `
                <div class="combo-slot-head">
                    <span>${escapeHtml(slot.title)}</span>
                    <span class="combo-slot-status" data-status></span>
                </div>
                <div class="combo-slot-body">${bodyHTML}</div>
                <div class="combo-slot-output" data-output hidden></div>
            `;
            if (slot.role === 'burger') {
                el.addEventListener('click', () => onSlotClick(slot.id));
            } else {
                el.style.borderStyle = 'solid';
                el.style.borderColor = 'rgba(140,160,220,0.4)';
                el.style.background = 'rgba(30,40,70,0.6)';
            }
            wrap.appendChild(el);
        });

        // 更新最小宽高
        wrap.scrollLeft = 0;
    }

    function onSlotClick(slotId) {
        const slot = state.slots.find(s => s.id === slotId);
        if (!slot) return;
        if (!state.selectedBurger) {
            BurgerGame.showToast && BurgerGame.showToast('请先从左侧菜品库选择一个汉堡', 'info');
            return;
        }
        slot.burger_id = state.selectedBurger.burger_id;
        state.selectedBurger = null;
        renderBurgerList();
        renderCanvas();
    }

    async function loadBurgers() {
        try {
            const resp = await fetch('/api/burgers');
            const data = await resp.json();
            state.burgers = data.burgers || [];
        } catch (e) {
            state.burgers = [];
        }
        renderBurgerList();
    }

    function renderBurgerList() {
        if (!state.burgers.length) {
            els.burgerList.innerHTML = '<div class="combo-empty">尚未保存任何汉堡。<br/>到搭建视图搭好汉堡后点「保存为菜品」即可。</div>';
            return;
        }
        els.burgerList.innerHTML = state.burgers.map(b => `
            <div class="combo-burger-card ${state.selectedBurger && state.selectedBurger.burger_id === b.burger_id ? 'active' : ''}" data-id="${b.burger_id}">
                <div class="cb-name">🍔 ${escapeHtml(b.name)}</div>
                <div class="cb-meta">${escapeHtml(b.agent_type || '-')} · ${(b.vegetables || []).length} 工具 · ${escapeHtml(b.meat_model || '')}</div>
            </div>
        `).join('');
        els.burgerList.querySelectorAll('[data-id]').forEach(el => {
            el.addEventListener('click', () => {
                const b = state.burgers.find(x => x.burger_id === el.dataset.id);
                state.selectedBurger = b || null;
                BurgerGame.showToast && BurgerGame.showToast(`已选中 ${b.name}，点击画布槽位填入`, 'info');
                els.burgerList.querySelectorAll('.combo-burger-card').forEach(c => c.classList.toggle('active', c === el));
            });
        });
    }

    async function loadCombos() {
        try {
            const resp = await fetch('/api/combos');
            const data = await resp.json();
            const list = data.combos || [];
            if (!list.length) {
                els.savedList.innerHTML = '<div class="combo-empty">尚未保存任何套餐</div>';
                return;
            }
            els.savedList.innerHTML = list.map(c => `
                <div class="combo-saved-card" data-id="${c.combo_id}">
                    <div class="cb-name">${PATTERNS[c.pattern] ? PATTERNS[c.pattern].icon : ''} ${escapeHtml(c.name)}</div>
                    <div class="cb-meta">${PATTERNS[c.pattern] ? PATTERNS[c.pattern].label : c.pattern}</div>
                </div>
            `).join('');
            els.savedList.querySelectorAll('[data-id]').forEach(el => {
                el.addEventListener('click', () => loadSavedCombo(el.dataset.id));
            });
        } catch (e) {
            els.savedList.innerHTML = '<div class="combo-empty">加载失败</div>';
        }
    }

    async function loadSavedCombo(combo_id) {
        try {
            const resp = await fetch(`/api/combos/${combo_id}`);
            if (!resp.ok) throw new Error('加载失败');
            const rec = await resp.json();
            state.combo_id = rec.combo_id;
            state.name = rec.name;
            els.nameInput.value = rec.name;
            selectPattern(rec.pattern);
            const cfg = rec.config || {};
            // 把 cfg 反填到 state.slots + 专属字段
            applyConfigToState(rec.pattern, cfg);
            renderCanvas();
            renderProps();
        } catch (e) {
            BurgerGame.showToast && BurgerGame.showToast('加载套餐失败: ' + e.message, 'error');
        }
    }

    function applyConfigToState(pattern, cfg) {
        if (pattern === 'chain') {
            (cfg.steps || []).forEach((step, i) => {
                const slot = state.slots[i];
                if (slot) slot.burger_id = step.burger_id;
            });
        } else if (pattern === 'routing') {
            state.routerSystem = cfg.router_system || '';
            (cfg.routes || []).forEach((r, i) => {
                const slot = state.slots.find(s => s.id === `route_${i + 1}`);
                if (slot) {
                    slot.burger_id = r.burger_id;
                    slot.route_key = r.key;
                    slot.route_label = r.label;
                    slot.route_desc = r.description;
                }
            });
        } else if (pattern === 'parallel') {
            state.aggregateTemplate = cfg.aggregate_template || '';
            (cfg.branches || []).forEach((b, i) => {
                const slot = state.slots.find(s => s.id === `b${i + 1}`);
                if (slot) slot.burger_id = b.burger_id;
            });
        } else if (pattern === 'orchestrator') {
            state.maxSections = cfg.max_sections || 3;
            state.orchSystem = (cfg.orchestrator || {}).system || '';
            const w = state.slots.find(s => s.id === 'worker');
            if (w) w.burger_id = (cfg.worker || {}).burger_id;
        } else if (pattern === 'evaluator') {
            state.maxIter = cfg.max_iterations || 2;
            state.criteria = (cfg.evaluator || {}).criteria || '';
            const g = state.slots.find(s => s.id === 'gen');
            if (g) g.burger_id = (cfg.generator || {}).burger_id;
        }
    }

    function renderProps() {
        if (!state.pattern) {
            els.props.innerHTML = '<div class="combo-empty">选择一种模式后，这里会显示可配置项</div>';
            return;
        }
        let html = '';
        if (state.pattern === 'routing') {
            const routes = state.slots.filter(s => s.role === 'burger');
            html += `<div class="prop-row"><label>路由系统提示（可选）</label>
                <textarea data-bind="routerSystem" placeholder="默认会自动根据分支描述生成">${escapeHtml(state.routerSystem)}</textarea></div>`;
            html += `<div class="prop-row"><label>分支配置（key / label / 描述）</label>`;
            routes.forEach(r => {
                html += `<div class="prop-subrow">
                    <input type="text" data-slot="${r.id}" data-field="route_key" placeholder="key" value="${escapeHtml(r.route_key || '')}"/>
                    <input type="text" data-slot="${r.id}" data-field="route_label" placeholder="label" value="${escapeHtml(r.route_label || '')}"/>
                </div>
                <div class="prop-subrow">
                    <input type="text" data-slot="${r.id}" data-field="route_desc" placeholder="给路由器看的 description" value="${escapeHtml(r.route_desc || '')}"/>
                </div>`;
            });
            html += `</div>`;
            html += `<div class="prop-row"><button class="mini-btn" data-action="add-route">+ 新增分支</button></div>`;
        } else if (state.pattern === 'chain') {
            html += `<div class="prop-row"><label>步骤数</label>
                <input type="number" min="2" max="6" value="${state.slots.length}" data-action="set-chain-len"/></div>`;
        } else if (state.pattern === 'parallel') {
            html += `<div class="prop-row"><label>并行分支数</label>
                <input type="number" min="2" max="6" value="${state.slots.filter(s => s.role === 'burger').length}" data-action="set-parallel-len"/></div>`;
            html += `<div class="prop-row"><label>聚合模板（可用 {node_id} 占位）</label>
                <textarea data-bind="aggregateTemplate" placeholder="留空使用默认拼接">${escapeHtml(state.aggregateTemplate)}</textarea></div>`;
        } else if (state.pattern === 'orchestrator') {
            html += `<div class="prop-row"><label>最大子任务数</label>
                <input type="number" min="1" max="8" data-bind="maxSections" value="${state.maxSections}"/></div>`;
            html += `<div class="prop-row"><label>主厨系统提示</label>
                <textarea data-bind="orchSystem" placeholder="留空使用默认：拆分为若干小节">${escapeHtml(state.orchSystem)}</textarea></div>`;
        } else if (state.pattern === 'evaluator') {
            html += `<div class="prop-row"><label>评委评价标准</label>
                <textarea data-bind="criteria">${escapeHtml(state.criteria)}</textarea></div>`;
            html += `<div class="prop-row"><label>最大迭代次数</label>
                <input type="number" min="1" max="8" data-bind="maxIter" value="${state.maxIter}"/></div>`;
        }
        els.props.innerHTML = html || '<div class="combo-empty">本模式暂无可配置项</div>';

        // 绑定事件
        els.props.querySelectorAll('[data-bind]').forEach(el => {
            el.addEventListener('input', () => {
                const field = el.dataset.bind;
                state[field] = el.value;
            });
        });
        els.props.querySelectorAll('[data-slot]').forEach(el => {
            el.addEventListener('input', () => {
                const slot = state.slots.find(s => s.id === el.dataset.slot);
                if (slot) slot[el.dataset.field] = el.value;
            });
        });
        const addRoute = els.props.querySelector('[data-action="add-route"]');
        if (addRoute) addRoute.addEventListener('click', () => {
            const idx = state.slots.filter(s => s.role === 'burger').length + 1;
            state.slots.push({
                id: `route_${idx}`, role: 'burger', title: `分支 ${idx}`,
                route_key: `branch_${idx}`, route_label: `分支 ${idx}`, route_desc: '',
                x: 340, y: 40 + (idx - 1) * 130,
            });
            renderCanvas(); renderProps();
        });
        const setChain = els.props.querySelector('[data-action="set-chain-len"]');
        if (setChain) setChain.addEventListener('change', () => {
            const n = Math.max(2, Math.min(6, +setChain.value || 3));
            const old = state.slots;
            state.slots = PATTERNS.chain.layout(n).map((l, i) => ({
                ...l,
                burger_id: (old[i] || {}).burger_id,
            }));
            renderCanvas();
        });
        const setPar = els.props.querySelector('[data-action="set-parallel-len"]');
        if (setPar) setPar.addEventListener('change', () => {
            const n = Math.max(2, Math.min(6, +setPar.value || 3));
            const old = state.slots.filter(s => s.role === 'burger');
            state.slots = PATTERNS.parallel.layout(n).map(l => {
                if (l.role === 'burger') {
                    const i = parseInt(l.id.slice(1), 10) - 1;
                    return { ...l, burger_id: (old[i] || {}).burger_id };
                }
                return { ...l };
            });
            renderCanvas();
        });
    }

    function escapeHtml(s) {
        return String(s || '').replace(/[&<>"']/g, m => ({
            '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
        }[m]));
    }

    // ----------- 构建 / 运行 / 保存 ----------
    async function runCombo() {
        if (!state.pattern) { return toast('请先选择一种模式', 'error'); }
        const p = PATTERNS[state.pattern];
        const err = p.validate(state);
        if (err) return toast(err, 'error');
        const config = p.buildConfig(state);

        setSlotStatus(null, '');
        openDrawer();
        try {
            const resp = await fetch('/api/combo/build', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    pattern: state.pattern,
                    config,
                    meat_model: 'qwen-plus',
                    cheese_prompt: '你是一个有用的智能助手',
                    thread_id: state.threadId || null,
                }),
            });
            if (!resp.ok) {
                const t = await resp.text();
                throw new Error(t || '构建失败');
            }
            const data = await resp.json();
            state.threadId = data.thread_id;
            addMsg('ai', `✅ 套餐已构建，开始对话吧！\n（模式：${PATTERNS[data.pattern].label}）`);
        } catch (e) {
            addMsg('ai', `❌ 构建失败：${e.message}`);
        }
    }

    async function saveCombo() {
        if (!state.pattern) return toast('请先选择模式', 'error');
        const name = (els.nameInput.value || '').trim();
        if (!name) return toast('请先给套餐取个名字', 'error');
        const p = PATTERNS[state.pattern];
        const config = p.buildConfig(state);
        try {
            const resp = await fetch('/api/combos', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    name,
                    pattern: state.pattern,
                    config,
                    combo_id: state.combo_id || null,
                }),
            });
            if (!resp.ok) throw new Error(await resp.text());
            const rec = await resp.json();
            state.combo_id = rec.combo_id;
            toast('💾 套餐已保存', 'success');
            loadCombos();
        } catch (e) {
            toast('保存失败: ' + e.message, 'error');
        }
    }

    function openDrawer() {
        els.drawer.hidden = false;
    }

    function closeDrawer() {
        els.drawer.hidden = true;
        els.trace.innerHTML = '';
        els.msgs.innerHTML = '';
    }

    function addMsg(role, text) {
        const div = document.createElement('div');
        div.className = 'combo-chat-msg ' + role;
        div.textContent = text;
        els.msgs.appendChild(div);
        els.msgs.scrollTop = els.msgs.scrollHeight;
        return div;
    }

    function addTrace(line, kind) {
        const div = document.createElement('div');
        div.className = 'trace-line kind-' + (kind || '');
        div.textContent = line;
        els.trace.appendChild(div);
        els.trace.scrollTop = els.trace.scrollHeight;
    }

    function setSlotStatus(nodeId, statusText, cls) {
        const wrap = els.canvas;
        if (!wrap) return;
        if (nodeId === null) {
            wrap.querySelectorAll('[data-status]').forEach(s => { s.textContent = ''; s.className = 'combo-slot-status'; });
            wrap.querySelectorAll('[data-output]').forEach(s => { s.hidden = true; s.textContent = ''; });
            return;
        }
        const slot = wrap.querySelector(`[data-slot-id="${nodeId}"]`);
        if (!slot) return;
        const s = slot.querySelector('[data-status]');
        if (s) {
            s.textContent = statusText;
            s.className = 'combo-slot-status ' + (cls || '');
        }
    }

    function setSlotOutput(nodeId, text) {
        const wrap = els.canvas;
        const slot = wrap && wrap.querySelector(`[data-slot-id="${nodeId}"]`);
        if (!slot) return;
        const o = slot.querySelector('[data-output]');
        if (o) {
            o.hidden = false;
            o.textContent = (text || '').slice(0, 300);
        }
    }

    async function sendChat() {
        const msg = (els.chatInput.value || '').trim();
        if (!msg) return;
        if (!state.threadId) { toast('请先点击「上菜运行」', 'error'); return; }
        addMsg('user', msg);
        els.chatInput.value = '';
        setSlotStatus(null, '');

        const resp = await fetch('/api/combo/chat/stream', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ thread_id: state.threadId, message: msg }),
        });
        if (!resp.ok || !resp.body) {
            addMsg('ai', '❌ 请求失败: ' + resp.status);
            return;
        }
        const reader = resp.body.getReader();
        const decoder = new TextDecoder('utf-8');
        let buf = '';
        while (true) {
            const { done, value } = await reader.read();
            if (done) break;
            buf += decoder.decode(value, { stream: true });
            const parts = buf.split('\n\n');
            buf = parts.pop();
            for (const chunk of parts) {
                const line = chunk.trim();
                if (!line.startsWith('data:')) continue;
                const payload = line.slice(5).trim();
                if (!payload) continue;
                let ev;
                try { ev = JSON.parse(payload); } catch { continue; }
                handleEvent(ev);
            }
        }
    }

    function handleEvent(ev) {
        switch (ev.type) {
            case 'combo_start':
                addTrace(`▶ 开始运行套餐（${ev.pattern}）`, 'start');
                break;
            case 'combo_burger_start':
                setSlotStatus(ev.node_id, 'running', 'running');
                addTrace(`🍔 汉堡 [${ev.node_id}] 开始执行`, 'burger');
                break;
            case 'combo_burger_end':
                setSlotStatus(ev.node_id, 'done', 'done');
                setSlotOutput(ev.node_id, ev.output || '');
                addTrace(`✔ 汉堡 [${ev.node_id}] 完成`, 'burger');
                break;
            case 'router_decision':
                addTrace(`🔀 路由决策 → ${ev.route}（${ev.why || ''}）`, 'router');
                break;
            case 'work_plan':
                addTrace(`📋 主厨规划 ${ev.sections.length} 个子任务：${ev.sections.map(s => s.name).join('、')}`, 'work_plan');
                break;
            case 'evaluator_feedback':
                addTrace(`⚖️ 第 ${ev.iteration} 轮评委：${ev.grade}${ev.accepted ? ' ✅' : ''} — ${ev.feedback || ''}`, 'evaluate');
                break;
            case 'combo_final':
                addMsg('ai', ev.output || '(空)');
                break;
            case 'error':
                addMsg('ai', '❌ ' + ev.detail);
                break;
        }
    }

    function toast(msg, level) {
        if (BurgerGame.showToast) BurgerGame.showToast(msg, level || 'info');
        else console.log(msg);
    }

    // 保存当前汉堡（在 chat view 中调用）
    async function saveCurrentBurger(burgerJSON, name) {
        try {
            const resp = await fetch('/api/burgers', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    name: name || `汉堡 ${new Date().toLocaleString()}`,
                    config: burgerJSON,
                }),
            });
            if (!resp.ok) throw new Error(await resp.text());
            const rec = await resp.json();
            toast(`💾 已保存为菜品：${rec.name}`, 'success');
            return rec;
        } catch (e) {
            toast('保存失败: ' + e.message, 'error');
            return null;
        }
    }

    function refresh() {
        renderPatternList();
        loadBurgers();
        loadCombos();
        if (!state.pattern) {
            els.canvas.innerHTML = '<div class="combo-placeholder">← 从左侧选择一种工作流模式</div>';
            els.patternBadge.textContent = '—';
        } else {
            renderCanvas();
            renderProps();
        }
    }

    function bindOnce() {
        cacheEls();
        els.backBtn && els.backBtn.addEventListener('click', hide);
        els.runBtn && els.runBtn.addEventListener('click', runCombo);
        els.saveBtn && els.saveBtn.addEventListener('click', saveCombo);
        els.drawerClose && els.drawerClose.addEventListener('click', closeDrawer);
        els.chatSend && els.chatSend.addEventListener('click', sendChat);
        els.nameInput && els.nameInput.addEventListener('input', () => { state.name = els.nameInput.value; });
        els.chatInput && els.chatInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendChat(); }
        });

        const gotoBtn = document.getElementById('btn-goto-combo');
        if (gotoBtn) gotoBtn.addEventListener('click', show);
    }

    // 页面加载后挂载
    document.addEventListener('DOMContentLoaded', bindOnce);

    // 对外 API
    BurgerGame.Combo = {
        show, hide, saveCurrentBurger,
    };
})();
