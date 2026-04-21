/**
 * ingredients.js — 汉堡食材定义 & PixiJS 图形绘制
 * 使用全局 PIXI 命名空间 (v7)
 */
window.BurgerGame = window.BurgerGame || {};

(function () {
    'use strict';

    // =========================================================
    //  食材元数据
    // =========================================================
    const INGREDIENT_TYPES = {
        top_bread: {
            id: 'top_bread',
            name: '顶部面包',
            nameEn: 'Top Bun',
            emoji: '🍞',
            desc: '输入处理层 (TopBread)',
            color: 0xd4a574,
            width: 260,
            height: 70,
            configurable: false,
            category: 'bread',
        },
        cheese: {
            id: 'cheese',
            name: '芝士片',
            nameEn: 'Cheese',
            emoji: '🧀',
            desc: '系统提示词 (System Prompt)',
            color: 0xffd700,
            width: 275,
            height: 22,
            configurable: true,
            category: 'filling',
            defaultConfig: { prompt: '你是一个有用的智能助手' },
        },
        meat_patty: {
            id: 'meat_patty',
            name: '肉饼',
            nameEn: 'Patty',
            emoji: '🥩',
            desc: '大语言模型 (LLM)',
            color: 0xa0522d,
            width: 255,
            height: 42,
            configurable: true,
            category: 'filling',
            defaultConfig: { model: 'qwen-plus' },
        },
        lettuce: {
            id: 'lettuce',
            name: '生菜',
            nameEn: 'Lettuce',
            emoji: '🥬',
            desc: '工具挂载 (Tools)',
            color: 0x2ecc71,
            width: 285,
            height: 24,
            configurable: true,
            category: 'filling',
            defaultConfig: { tools: [] },
        },
        tomato: {
            id: 'tomato',
            name: '番茄',
            nameEn: 'Tomato',
            emoji: '🍅',
            desc: '持久化记忆 (Checkpointer)',
            color: 0xe74c3c,
            width: 250,
            height: 18,
            configurable: false,
            category: 'filling',
        },
        pickle: {
            id: 'pickle',
            name: '酸黄瓜',
            nameEn: 'Pickle',
            emoji: '🥒',
            desc: '人类审批 (HITL · interrupt_before)',
            color: 0x7fb069,
            width: 255,
            height: 16,
            configurable: true,
            category: 'filling',
            defaultConfig: { hint: '是否允许执行上述工具调用？' },
        },
        onion: {
            id: 'onion',
            name: '洋葱',
            nameEn: 'Onion',
            emoji: '🧅',
            desc: '条件路由 (Conditional Edge)',
            color: 0xc084fc,
            width: 260,
            height: 22,
            configurable: true,
            category: 'filling',
            defaultConfig: { default: 'chat' },
        },
        chili: {
            id: 'chili',
            name: '辣椒',
            nameEn: 'Chili',
            emoji: '🌶️',
            desc: 'State Reducer 演示 (Annotated)',
            color: 0xef4444,
            width: 240,
            height: 18,
            configurable: true,
            category: 'filling',
            defaultConfig: { heat: 2, flavor: 'spicy' },
        },
        bottom_bread: {
            id: 'bottom_bread',
            name: '底部面包',
            nameEn: 'Bottom Bun',
            emoji: '🍞',
            desc: '输出处理层 (BottomBread)',
            color: 0xd4a574,
            width: 260,
            height: 38,
            configurable: false,
            category: 'bread',
        },
    };

    // =========================================================
    //  绘制辅助
    // =========================================================
    function hexToComponents(hex) {
        return {
            r: (hex >> 16) & 0xff,
            g: (hex >> 8) & 0xff,
            b: hex & 0xff,
        };
    }

    function darken(hex, factor) {
        const c = hexToComponents(hex);
        return (
            ((Math.floor(c.r * factor) & 0xff) << 16) |
            ((Math.floor(c.g * factor) & 0xff) << 8) |
            (Math.floor(c.b * factor) & 0xff)
        );
    }

    function lighten(hex, factor) {
        const c = hexToComponents(hex);
        return (
            ((Math.min(255, Math.floor(c.r + (255 - c.r) * factor)) & 0xff) << 16) |
            ((Math.min(255, Math.floor(c.g + (255 - c.g) * factor)) & 0xff) << 8) |
            (Math.min(255, Math.floor(c.b + (255 - c.b) * factor)) & 0xff)
        );
    }

    // =========================================================
    //  顶部面包 — 拱形圆顶 + 芝麻
    // =========================================================
    function drawTopBread(container, meta) {
        const w = meta.width;
        const h = meta.height;
        const g = new PIXI.Graphics();

        // 面包主体：底部矩形 + 顶部圆拱
        const bodyH = h * 0.4;
        const domeH = h * 0.6;

        // 圆拱
        g.beginFill(meta.color);
        g.moveTo(0, domeH);
        g.quadraticCurveTo(w * 0.05, -domeH * 0.15, w * 0.5, -domeH * 0.1);
        g.quadraticCurveTo(w * 0.95, -domeH * 0.15, w, domeH);
        g.lineTo(w, domeH + bodyH);
        g.lineTo(0, domeH + bodyH);
        g.closePath();
        g.endFill();

        // 底部略深线条
        g.lineStyle(2, darken(meta.color, 0.75), 0.5);
        g.moveTo(4, domeH + bodyH - 2);
        g.lineTo(w - 4, domeH + bodyH - 2);
        g.lineStyle(0);

        // 面包高光
        const highlight = new PIXI.Graphics();
        highlight.beginFill(lighten(meta.color, 0.3), 0.25);
        highlight.moveTo(w * 0.15, domeH * 0.5);
        highlight.quadraticCurveTo(w * 0.35, -domeH * 0.05, w * 0.55, domeH * 0.45);
        highlight.quadraticCurveTo(w * 0.45, domeH * 0.35, w * 0.15, domeH * 0.5);
        highlight.endFill();

        // 芝麻
        const seeds = new PIXI.Graphics();
        const seedPositions = [
            [w * 0.2, domeH * 0.25], [w * 0.35, domeH * 0.1],
            [w * 0.5, domeH * 0.05], [w * 0.65, domeH * 0.1],
            [w * 0.8, domeH * 0.25], [w * 0.3, domeH * 0.45],
            [w * 0.55, domeH * 0.35], [w * 0.72, domeH * 0.42],
        ];
        seedPositions.forEach(([sx, sy]) => {
            seeds.beginFill(0xfff5e6, 0.85);
            seeds.drawEllipse(sx, sy, 4, 2.5);
            seeds.endFill();
        });

        container.addChild(g);
        container.addChild(highlight);
        container.addChild(seeds);
    }

    // =========================================================
    //  底部面包 — 扁平圆角
    // =========================================================
    function drawBottomBread(container, meta) {
        const w = meta.width;
        const h = meta.height;
        const g = new PIXI.Graphics();

        // 主体
        g.beginFill(meta.color);
        g.moveTo(8, 0);
        g.lineTo(w - 8, 0);
        g.quadraticCurveTo(w, 0, w, 8);
        g.lineTo(w, h - 10);
        g.quadraticCurveTo(w, h, w - 10, h);
        g.lineTo(10, h);
        g.quadraticCurveTo(0, h, 0, h - 10);
        g.lineTo(0, 8);
        g.quadraticCurveTo(0, 0, 8, 0);
        g.closePath();
        g.endFill();

        // 顶部高光线
        g.lineStyle(1.5, lighten(meta.color, 0.25), 0.4);
        g.moveTo(8, 2);
        g.lineTo(w - 8, 2);
        g.lineStyle(0);

        container.addChild(g);
    }

    // =========================================================
    //  芝士 — 波浪形 + 融化下垂
    // =========================================================
    function drawCheese(container, meta) {
        const w = meta.width;
        const h = meta.height;
        const g = new PIXI.Graphics();

        g.beginFill(meta.color, 0.92);
        // 顶边
        g.moveTo(0, 4);
        g.lineTo(w, 4);
        // 右边
        g.lineTo(w, h);
        // 底边 — 波浪 + 下垂三角
        const dripWidth = 18;
        const numDrips = 5;
        const segW = w / numDrips;
        for (let i = numDrips - 1; i >= 0; i--) {
            const dx = i * segW + segW * 0.5;
            const dripH = (i % 2 === 0) ? h + 10 : h + 5;
            g.lineTo(dx + dripWidth * 0.5, h);
            g.quadraticCurveTo(dx, dripH + 4, dx - dripWidth * 0.5, h);
        }
        g.lineTo(0, h);
        g.closePath();
        g.endFill();

        // 高光
        g.beginFill(lighten(meta.color, 0.3), 0.2);
        g.drawRoundedRect(w * 0.1, 5, w * 0.3, h * 0.35, 3);
        g.endFill();

        // 暗色孔洞
        g.beginFill(darken(meta.color, 0.82), 0.25);
        g.drawEllipse(w * 0.6, h * 0.45, 8, 4);
        g.drawEllipse(w * 0.25, h * 0.55, 5, 3);
        g.endFill();

        container.addChild(g);
    }

    // =========================================================
    //  肉饼 — 椭圆厚块 + 烤纹
    // =========================================================
    function drawMeatPatty(container, meta) {
        const w = meta.width;
        const h = meta.height;
        const g = new PIXI.Graphics();

        // 主体 — 圆角矩形
        g.beginFill(meta.color);
        g.drawRoundedRect(0, 0, w, h, 12);
        g.endFill();

        // 烤纹
        const grillG = new PIXI.Graphics();
        grillG.lineStyle(2.5, darken(meta.color, 0.55), 0.4);
        for (let i = 0; i < 5; i++) {
            const gx = w * 0.12 + i * (w * 0.19);
            grillG.moveTo(gx, h * 0.2);
            grillG.lineTo(gx + 8, h * 0.8);
        }
        grillG.lineStyle(0);

        // 表面纹理高光
        const texG = new PIXI.Graphics();
        texG.beginFill(lighten(meta.color, 0.15), 0.2);
        texG.drawEllipse(w * 0.3, h * 0.35, w * 0.18, h * 0.2);
        texG.endFill();
        texG.beginFill(lighten(meta.color, 0.12), 0.15);
        texG.drawEllipse(w * 0.7, h * 0.55, w * 0.12, h * 0.15);
        texG.endFill();

        container.addChild(g);
        container.addChild(grillG);
        container.addChild(texG);
    }

    // =========================================================
    //  生菜 — 波浪叶片
    // =========================================================
    function drawLettuce(container, meta) {
        const w = meta.width;
        const h = meta.height;
        const g = new PIXI.Graphics();

        // 主叶片 — 波浪路径
        g.beginFill(meta.color, 0.88);
        g.moveTo(0, h * 0.5);
        // 顶部波浪
        const segs = 8;
        for (let i = 0; i < segs; i++) {
            const sx = (i / segs) * w;
            const ex = ((i + 1) / segs) * w;
            const mx = (sx + ex) / 2;
            const my = (i % 2 === 0) ? -h * 0.15 : h * 0.25;
            g.quadraticCurveTo(mx, my, ex, h * 0.3);
        }
        // 底部波浪
        for (let i = segs - 1; i >= 0; i--) {
            const sx = ((i + 1) / segs) * w;
            const ex = (i / segs) * w;
            const mx = (sx + ex) / 2;
            const my = h + ((i % 2 === 0) ? h * 0.15 : -h * 0.1);
            g.quadraticCurveTo(mx, my, ex, h * 0.7);
        }
        g.closePath();
        g.endFill();

        // 叶脉
        const vein = new PIXI.Graphics();
        vein.lineStyle(1, darken(meta.color, 0.75), 0.3);
        vein.moveTo(w * 0.05, h * 0.5);
        vein.lineTo(w * 0.95, h * 0.5);
        for (let i = 1; i < 6; i++) {
            const bx = w * (i / 6);
            vein.moveTo(bx, h * 0.5);
            vein.lineTo(bx - 8, h * 0.15);
            vein.moveTo(bx, h * 0.5);
            vein.lineTo(bx + 6, h * 0.85);
        }
        vein.lineStyle(0);

        container.addChild(g);
        container.addChild(vein);
    }

    // =========================================================
    //  番茄 — 薄片切面
    // =========================================================
    function drawTomato(container, meta) {
        const w = meta.width;
        const h = meta.height;
        const g = new PIXI.Graphics();

        // 主片
        g.beginFill(meta.color, 0.90);
        g.drawRoundedRect(0, 0, w, h, 8);
        g.endFill();

        // 种子/内部纹理
        const seed = new PIXI.Graphics();
        const seedColor = lighten(meta.color, 0.35);
        seed.beginFill(seedColor, 0.4);
        seed.drawEllipse(w * 0.25, h * 0.5, 12, 5);
        seed.drawEllipse(w * 0.5, h * 0.5, 14, 5);
        seed.drawEllipse(w * 0.75, h * 0.5, 12, 5);
        seed.endFill();

        // 高光
        g.beginFill(lighten(meta.color, 0.25), 0.2);
        g.drawRoundedRect(w * 0.05, 1, w * 0.25, h * 0.35, 3);
        g.endFill();

        container.addChild(g);
        container.addChild(seed);
    }

    // =========================================================
    //  酸黄瓜 — 切片 + 凹凸纹理（HITL 审批关卡）
    // =========================================================
    function drawPickle(container, meta) {
        const w = meta.width;
        const h = meta.height;
        const g = new PIXI.Graphics();

        // 主片 — 椭圆切面
        g.beginFill(meta.color, 0.92);
        g.drawRoundedRect(0, 0, w, h, Math.min(h * 0.6, 12));
        g.endFill();

        // 暗边：浸渍感
        g.lineStyle(1.5, darken(meta.color, 0.65), 0.45);
        g.drawRoundedRect(1, 1, w - 2, h - 2, Math.min(h * 0.5, 10));
        g.lineStyle(0);

        // 凹凸纹理：小籽粒（象征"细节审视"）
        const bumps = new PIXI.Graphics();
        const bumpColor = lighten(meta.color, 0.35);
        const darkBump = darken(meta.color, 0.6);
        const count = 9;
        for (let i = 0; i < count; i++) {
            const bx = ((i + 0.5) / count) * w;
            const by = h * 0.5 + (i % 2 === 0 ? -1.5 : 1.5);
            bumps.beginFill(bumpColor, 0.55);
            bumps.drawCircle(bx, by, 1.8);
            bumps.endFill();
            bumps.beginFill(darkBump, 0.35);
            bumps.drawCircle(bx + 0.4, by + 0.4, 1);
            bumps.endFill();
        }

        // 高光条
        g.beginFill(lighten(meta.color, 0.4), 0.25);
        g.drawRoundedRect(w * 0.04, 1, w * 0.25, h * 0.3, 2);
        g.endFill();

        container.addChild(g);
        container.addChild(bumps);
    }

    // =========================================================
    //  洋葱 — 同心圆环（路由分支隐喻）
    // =========================================================
    function drawOnion(container, meta) {
        const w = meta.width, h = meta.height;
        const g = new PIXI.Graphics();

        // 主体
        g.beginFill(meta.color);
        g.drawRoundedRect(0, 0, w, h, 10);
        g.endFill();

        // 三道同心弧表示"路由分层"
        const cx = w / 2;
        const cy = h / 2;
        for (let i = 0; i < 3; i++) {
            g.lineStyle(1.5, lighten(meta.color, 0.35 + i * 0.15), 0.9);
            g.drawEllipse(cx, cy, w * 0.4 - i * 18, h * 0.36 - i * 4);
        }
        g.lineStyle(0);

        // 三条分支线（从中心向右）
        g.lineStyle(1.2, 0xffffff, 0.6);
        g.moveTo(cx, cy);
        g.lineTo(cx + 40, cy - 6);
        g.moveTo(cx, cy);
        g.lineTo(cx + 40, cy);
        g.moveTo(cx, cy);
        g.lineTo(cx + 40, cy + 6);
        g.lineStyle(0);

        container.addChild(g);
    }

    // =========================================================
    //  辣椒 — 横卧红椒 + 火花点
    // =========================================================
    function drawChili(container, meta) {
        const w = meta.width, h = meta.height;
        const g = new PIXI.Graphics();

        // 椒身（胶囊形）
        g.beginFill(meta.color);
        g.drawRoundedRect(0, 0, w, h, h / 2);
        g.endFill();

        // 椒把（左端小绿叶）
        g.beginFill(0x16a34a);
        g.drawRoundedRect(-6, h * 0.15, 14, h * 0.7, 3);
        g.endFill();

        // 高光
        g.beginFill(lighten(meta.color, 0.4), 0.4);
        g.drawRoundedRect(w * 0.1, 2, w * 0.6, h * 0.35, h * 0.2);
        g.endFill();

        // 火花点
        const sparks = new PIXI.Graphics();
        sparks.beginFill(0xffd700, 0.9);
        for (let i = 0; i < 5; i++) {
            const x = w * (0.2 + 0.15 * i) + (Math.random() - 0.5) * 4;
            const y = h / 2 + (Math.random() - 0.5) * h * 0.4;
            sparks.drawCircle(x, y, 1.2);
        }
        sparks.endFill();

        container.addChild(g);
        container.addChild(sparks);
    }

    // =========================================================
    //  绘制分发
    // =========================================================
    const DRAW_FUNCTIONS = {
        top_bread: drawTopBread,
        bottom_bread: drawBottomBread,
        cheese: drawCheese,
        meat_patty: drawMeatPatty,
        lettuce: drawLettuce,
        tomato: drawTomato,
        pickle: drawPickle,
        onion: drawOnion,
        chili: drawChili,
    };

    /**
     * 创建食材图形容器
     * @param {string} type - 食材类型 ID
     * @returns {{ container: PIXI.Container, meta: Object, config: Object }}
     */
    function createIngredient(type) {
        const meta = INGREDIENT_TYPES[type];
        if (!meta) throw new Error('Unknown ingredient type: ' + type);

        const container = new PIXI.Container();
        container.sortableChildren = true;

        // 绘制图形
        DRAW_FUNCTIONS[type](container, meta);

        // 居中锚点
        container.pivot.set(meta.width / 2, meta.height / 2);

        // 存储元数据
        container._ingredientType = type;
        container._ingredientMeta = meta;
        container._ingredientConfig = meta.defaultConfig
            ? JSON.parse(JSON.stringify(meta.defaultConfig))
            : {};

        return {
            container: container,
            meta: meta,
            config: container._ingredientConfig,
        };
    }

    // =========================================================
    //  创建选中高亮框
    // =========================================================
    function createSelectionBorder(meta) {
        const g = new PIXI.Graphics();
        const pad = 6;
        g.lineStyle(2, 0x6c5ce7, 0.8);
        g.drawRoundedRect(
            -pad, -pad,
            meta.width + pad * 2,
            meta.height + pad * 2,
            8
        );
        g.lineStyle(0);
        g.pivot.set(meta.width / 2, meta.height / 2);
        return g;
    }

    // 导出
    BurgerGame.IngredientTypes = INGREDIENT_TYPES;
    BurgerGame.createIngredient = createIngredient;
    BurgerGame.createSelectionBorder = createSelectionBorder;
})();
