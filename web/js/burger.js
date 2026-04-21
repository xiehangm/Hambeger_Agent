/**
 * burger.js — 汉堡画布管理器
 * 处理 PixiJS 画布初始化、食材拖曳、堆叠排序、JSON 导出
 */
window.BurgerGame = window.BurgerGame || {};

(function () {
    'use strict';

    const CANVAS_W = 520;
    const CANVAS_H = 640;
    const STACK_CENTER_X = CANVAS_W / 2;
    const PLATE_Y = CANVAS_H - 80;          // 盘子中心 Y
    const STACK_GAP = 3;                     // 食材间距
    const TWEEN_DURATION = 320;              // 动画毫秒
    const DELETE_ZONE_W = 80;                // 右侧删除区宽度

    // =========================================================
    //  BurgerCanvas 类
    // =========================================================
    class BurgerCanvas {
        constructor(containerElementId) {
            this.containerEl = document.getElementById(containerElementId);
            this.app = null;
            this.layers = [];               // { container, meta, config, selectionBorder }
            this.plateContainer = null;
            this.bgContainer = null;
            this.layerContainer = null;
            this.deleteZone = null;
            this.selectedLayer = null;
            this.isDragging = false;
            this.dragData = null;
            this.tweens = [];

            // 回调
            this.onSelectIngredient = null;  // (layer) => void
            this.onDeselectAll = null;       // () => void
            this.onLayerCountChange = null;  // (count) => void
        }

        // ---- 初始化 -----
        init() {
            this.app = new PIXI.Application({
                width: CANVAS_W,
                height: CANVAS_H,
                backgroundColor: 0x0f0f25,
                antialias: true,
                resolution: window.devicePixelRatio || 1,
                autoDensity: true,
            });
            this.containerEl.appendChild(this.app.view);

            // 层级容器
            this.bgContainer = new PIXI.Container();
            this.edgesContainer = new PIXI.Container();   // 🔗 LangGraph 边连线层
            this.layerContainer = new PIXI.Container();
            this.app.stage.addChild(this.bgContainer);
            this.app.stage.addChild(this.edgesContainer);
            this.app.stage.addChild(this.layerContainer);

            this.currentRecipe = null;     // 当前匹配的 recipe 蓝图（由外部 setRecipe 注入）

            this._drawBackground();
            this._drawPlate();
            this._drawDeleteZone();

            // 点击空白区取消选择
            this.app.stage.eventMode = 'static';
            this.app.stage.hitArea = new PIXI.Rectangle(0, 0, CANVAS_W, CANVAS_H);
            this.app.stage.on('pointerdown', (e) => {
                if (e.target === this.app.stage) {
                    this.deselectAll();
                }
            });

            // ticker 更新 tweens
            this.app.ticker.add(() => this._updateTweens());
        }

        // ---- 背景 ----
        _drawBackground() {
            const bg = new PIXI.Graphics();

            // 渐变模拟 — 多个半透明矩形叠加
            bg.beginFill(0x0f0f25);
            bg.drawRect(0, 0, CANVAS_W, CANVAS_H);
            bg.endFill();

            // 微妙的网格点
            bg.beginFill(0xffffff, 0.015);
            for (let x = 0; x < CANVAS_W; x += 30) {
                for (let y = 0; y < CANVAS_H; y += 30) {
                    bg.drawCircle(x, y, 1);
                }
            }
            bg.endFill();

            // 中心光晕
            const glow = new PIXI.Graphics();
            glow.beginFill(0x6c5ce7, 0.02);
            glow.drawCircle(STACK_CENTER_X, PLATE_Y - 120, 200);
            glow.endFill();
            glow.beginFill(0xf39c12, 0.015);
            glow.drawCircle(STACK_CENTER_X, PLATE_Y - 80, 150);
            glow.endFill();

            this.bgContainer.addChild(bg);
            this.bgContainer.addChild(glow);
        }

        // ---- 盘子 ----
        _drawPlate() {
            this.plateContainer = new PIXI.Container();

            // 盘子阴影
            const shadow = new PIXI.Graphics();
            shadow.beginFill(0x000000, 0.2);
            shadow.drawEllipse(STACK_CENTER_X, PLATE_Y + 12, 160, 18);
            shadow.endFill();

            // 盘子主体
            const plate = new PIXI.Graphics();
            plate.beginFill(0x2a2a45, 0.7);
            plate.drawEllipse(STACK_CENTER_X, PLATE_Y, 155, 22);
            plate.endFill();
            // 盘子高光
            plate.beginFill(0x3a3a5a, 0.4);
            plate.drawEllipse(STACK_CENTER_X, PLATE_Y - 3, 140, 16);
            plate.endFill();
            // 盘子边缘
            plate.lineStyle(1, 0x4a4a6a, 0.3);
            plate.drawEllipse(STACK_CENTER_X, PLATE_Y, 155, 22);
            plate.lineStyle(0);

            // 提示文字
            this.hintText = new PIXI.Text('点击左侧食材开始搭建 →', {
                fontFamily: 'Noto Sans SC, Segoe UI, sans-serif',
                fontSize: 14,
                fill: 0x555580,
                align: 'center',
            });
            this.hintText.anchor.set(0.5);
            this.hintText.position.set(STACK_CENTER_X, PLATE_Y - 60);

            this.plateContainer.addChild(shadow);
            this.plateContainer.addChild(plate);
            this.plateContainer.addChild(this.hintText);

            this.bgContainer.addChild(this.plateContainer);
        }

        // ---- 删除区 ----
        _drawDeleteZone() {
            this.deleteZone = new PIXI.Container();
            this.deleteZone.visible = false;

            const zone = new PIXI.Graphics();
            zone.beginFill(0xe74c3c, 0.08);
            zone.drawRoundedRect(CANVAS_W - DELETE_ZONE_W, 0, DELETE_ZONE_W, CANVAS_H, 0);
            zone.endFill();
            zone.lineStyle(2, 0xe74c3c, 0.2);
            zone.moveTo(CANVAS_W - DELETE_ZONE_W, 0);
            zone.lineTo(CANVAS_W - DELETE_ZONE_W, CANVAS_H);
            zone.lineStyle(0);

            // 垃圾桶图标文字
            const trashText = new PIXI.Text('🗑️', {
                fontSize: 28,
            });
            trashText.anchor.set(0.5);
            trashText.position.set(CANVAS_W - DELETE_ZONE_W / 2, CANVAS_H / 2);
            trashText.alpha = 0.5;

            this.deleteZone.addChild(zone);
            this.deleteZone.addChild(trashText);
            this.bgContainer.addChild(this.deleteZone);
        }

        // =========================================================
        //  添加食材
        // =========================================================
        addIngredient(type) {
            const { container, meta, config } = BurgerGame.createIngredient(type);

            // 初始位置 — 从左侧飞入
            container.x = -100;
            container.y = PLATE_Y - 100;
            container.alpha = 0;

            // 交互
            container.eventMode = 'static';
            container.cursor = 'grab';

            // 阴影层
            const shadowG = new PIXI.Graphics();
            shadowG.beginFill(0x000000, 0.15);
            shadowG.drawEllipse(0, meta.height / 2 + 4, meta.width * 0.4, 6);
            shadowG.endFill();
            shadowG.pivot.set(0, 0);
            shadowG.x = 0;
            shadowG.y = 0;
            shadowG.zIndex = -1;
            container.addChild(shadowG);
            container.sortChildren();

            // 保存图层信息
            const layer = {
                container: container,
                meta: meta,
                config: config,
                shadow: shadowG,
                id: Date.now() + '_' + Math.random().toString(36).substr(2, 5),
            };

            this.layers.push(layer);
            this.layerContainer.addChild(container);

            // 绑定拖拽
            this._setupDrag(layer);

            // 绑定点击选择
            container.on('pointertap', (e) => {
                if (!this.isDragging) {
                    e.stopPropagation();
                    this.selectLayer(layer);
                }
            });

            // 飞入动画 → 然后重排堆叠
            this._tween(container, { x: STACK_CENTER_X, alpha: 1 }, 250, () => {
                this.updateStack(true);
            });

            // 隐藏提示
            if (this.hintText) this.hintText.visible = false;

            this._fireLayerCountChange();
        }

        // =========================================================
        //  拖拽系统
        // =========================================================
        _setupDrag(layer) {
            const container = layer.container;
            let startPos = null;
            let dragOffset = null;
            let moved = false;

            const onDragStart = (event) => {
                this.isDragging = false;
                moved = false;
                startPos = { x: container.x, y: container.y };
                const pos = event.data.getLocalPosition(container.parent);
                dragOffset = {
                    x: pos.x - container.x,
                    y: pos.y - container.y,
                };
                this.dragData = event.data;

                container.alpha = 0.8;
                container.cursor = 'grabbing';
                container.zIndex = 1000;
                this.layerContainer.sortChildren();

                // 显示删除区
                this.deleteZone.visible = true;

                this.app.stage.on('pointermove', onDragMove);
                this.app.stage.on('pointerup', onDragEnd);
                this.app.stage.on('pointerupoutside', onDragEnd);
            };

            const onDragMove = (event) => {
                if (!this.dragData) return;
                const newPos = this.dragData.getLocalPosition(container.parent);
                const nx = newPos.x - dragOffset.x;
                const ny = newPos.y - dragOffset.y;

                if (!moved && (Math.abs(nx - startPos.x) > 4 || Math.abs(ny - startPos.y) > 4)) {
                    moved = true;
                    this.isDragging = true;
                }

                if (moved) {
                    container.x = nx;
                    container.y = Math.max(30, Math.min(CANVAS_H - 30, ny));

                    // 检测是否在删除区
                    if (container.x > CANVAS_W - DELETE_ZONE_W - 40) {
                        container.alpha = 0.4;
                        container.scale.set(0.85);
                    } else {
                        container.alpha = 0.8;
                        container.scale.set(1);
                    }
                }
            };

            const onDragEnd = () => {
                this.app.stage.off('pointermove', onDragMove);
                this.app.stage.off('pointerup', onDragEnd);
                this.app.stage.off('pointerupoutside', onDragEnd);

                if (!this.dragData) return;

                // 检测删除
                if (container.x > CANVAS_W - DELETE_ZONE_W - 40) {
                    this.removeLayer(layer);
                } else if (moved) {
                    // 先将所有正在动画中的容器吸附到终态，确保 Y 值准确
                    for (let i = this.tweens.length - 1; i >= 0; i--) {
                        const tw = this.tweens[i];
                        for (const key in tw.endProps) {
                            tw.obj[key] = tw.endProps[key];
                        }
                        this.tweens.splice(i, 1);
                    }
                    // 根据 Y 位置重新排序
                    this.layers.sort((a, b) => a.container.y - b.container.y);
                    this.updateStack(true);
                    // 通知外部：顺序已变，触发配方识别刷新
                    this._fireLayerCountChange();
                }

                container.alpha = 1;
                container.scale.set(1);
                container.cursor = 'grab';
                container.zIndex = 0;
                this.layerContainer.sortChildren();

                this.dragData = null;
                this.deleteZone.visible = false;

                setTimeout(() => { this.isDragging = false; }, 50);
            };

            container.on('pointerdown', onDragStart);
        }

        // =========================================================
        //  堆叠排列
        // =========================================================
        updateStack(animated) {
            if (this.layers.length === 0) return;

            // 计算总高度
            let totalH = 0;
            this.layers.forEach((l) => {
                totalH += l.meta.height + STACK_GAP;
            });
            totalH -= STACK_GAP;

            // 从盘子位置向上堆叠
            let currentY = PLATE_Y - 25; // 盘子上方

            // 从最后一个(底部)往上排
            for (let i = this.layers.length - 1; i >= 0; i--) {
                const layer = this.layers[i];
                currentY -= layer.meta.height / 2;
                const targetY = currentY;
                const targetX = STACK_CENTER_X;
                currentY -= layer.meta.height / 2 + STACK_GAP;

                if (animated) {
                    this._tween(layer.container, { x: targetX, y: targetY }, TWEEN_DURATION);
                } else {
                    layer.container.x = targetX;
                    layer.container.y = targetY;
                }

                // 记录最终位置，供连线使用
                layer._finalY = targetY;
                layer._finalX = targetX;
            }

            // 连线要等动画结束再画；这里无动画时立即画，有动画时延时画
            if (animated) {
                clearTimeout(this._edgesRedrawT);
                this._edgesRedrawT = setTimeout(() => this._drawEdges(), TWEEN_DURATION + 20);
            } else {
                this._drawEdges();
            }
        }

        /**
         * 🔗 根据当前 recipe 的 edges 画出 LangGraph 连线：
         *   - 普通边：纯色竖线
         *   - 条件边：紫色虚线 + 菱形节点（多分支）
         *   - 回环 (meat → cheese)：贝塞尔曲线绕左侧
         */
        setRecipe(recipe) {
            this.currentRecipe = recipe || null;
            this._drawEdges();
        }

        _drawEdges() {
            if (!this.edgesContainer) return;
            this.edgesContainer.removeChildren();
            if (!this.currentRecipe || this.layers.length < 2) return;

            const edges = this.currentRecipe.edges || [];
            if (!edges.length) return;

            // 建立 nodeId → layer 的映射（通过 alias）
            const aliasMap = {
                top_bread: 'top_bread',
                bottom_bread: 'bottom_bread',
                cheese: 'cheese',
                meat: 'meat_patty',
                vegetable: 'lettuce',
                pickle: 'pickle',
                onion: 'onion',
                chili: 'chili',
                tomato: 'tomato',
            };
            const nodeToLayer = {};
            for (const [id, ingType] of Object.entries(aliasMap)) {
                const layer = this.layers.find((l) => l.meta.type === ingType);
                if (layer) nodeToLayer[id] = layer;
            }

            const g = new PIXI.Graphics();

            // 普通 edges
            for (const e of edges) {
                const fromLayer = nodeToLayer[e.from];
                const toLayer = nodeToLayer[e.to];
                if (!fromLayer || !toLayer) continue;
                if (fromLayer === toLayer) continue;

                const x1 = fromLayer._finalX || STACK_CENTER_X;
                const y1 = fromLayer._finalY || 0;
                const x2 = toLayer._finalX || STACK_CENTER_X;
                const y2 = toLayer._finalY || 0;

                // 从 from 层的底部画到 to 层的顶部（自动适配上下位置）
                const fromBottom = y1 + fromLayer.meta.height / 2;
                const fromTop = y1 - fromLayer.meta.height / 2;
                const toBottom = y2 + toLayer.meta.height / 2;
                const toTop = y2 - toLayer.meta.height / 2;

                const goingUp = y2 < y1;
                const sy = goingUp ? fromTop : fromBottom;
                const ty = goingUp ? toBottom : toTop;

                // 判断是不是回环（meat → cheese 之类向上的边）
                if (goingUp) {
                    // 🌀 绕左侧画贝塞尔曲线
                    const offsetX = x1 - 120;
                    g.lineStyle({ width: 2, color: 0x6c5ce7, alpha: 0.7 });
                    g.moveTo(x1 - 40, sy);
                    g.bezierCurveTo(offsetX, sy, offsetX, ty, x2 - 40, ty);
                    g.lineStyle(0);
                    // 箭头
                    this._drawArrow(g, x2 - 40, ty, x2, ty, 0x6c5ce7);
                } else {
                    // 普通顺序边：竖直实线
                    g.lineStyle({ width: 2, color: 0x8a8ab5, alpha: 0.55 });
                    g.moveTo(x1, sy);
                    g.lineTo(x2, ty);
                    g.lineStyle(0);
                }
            }

            // 条件 edges：紫色虚线 + "⬢" 标签
            const condEdges = this.currentRecipe.conditional_edges || [];
            for (const ce of condEdges) {
                const fromLayer = nodeToLayer[ce.from];
                if (!fromLayer) continue;
                const x1 = fromLayer._finalX || STACK_CENTER_X;
                const y1 = (fromLayer._finalY || 0) + fromLayer.meta.height / 2;

                // 条件菱形
                const diamond = new PIXI.Graphics();
                diamond.beginFill(0xc084fc, 0.8);
                diamond.lineStyle(1.5, 0xffffff, 0.9);
                const dy = y1 + 8;
                diamond.moveTo(x1, dy - 6);
                diamond.lineTo(x1 + 8, dy);
                diamond.lineTo(x1, dy + 6);
                diamond.lineTo(x1 - 8, dy);
                diamond.closePath();
                diamond.endFill();
                this.edgesContainer.addChild(diamond);

                // 每个分支画虚线
                const mapping = ce.mapping || {};
                const branches = Object.entries(mapping);
                branches.forEach(([branchKey, target], idx) => {
                    const targetLayer = nodeToLayer[target];
                    if (!targetLayer) return;
                    const x2 = targetLayer._finalX || STACK_CENTER_X;
                    const y2 = (targetLayer._finalY || 0) - targetLayer.meta.height / 2;
                    const spreadX = x1 + (idx - (branches.length - 1) / 2) * 60;
                    this._drawDashedLine(g, x1, dy + 6, spreadX, (dy + y2) / 2, 0xc084fc);
                    this._drawDashedLine(g, spreadX, (dy + y2) / 2, x2, y2, 0xc084fc);

                    // 分支标签
                    const label = new PIXI.Text(branchKey, {
                        fontFamily: 'Noto Sans SC, sans-serif',
                        fontSize: 10,
                        fill: 0xc084fc,
                    });
                    label.anchor.set(0.5);
                    label.position.set(spreadX, (dy + y2) / 2 - 10);
                    this.edgesContainer.addChild(label);
                });
            }

            this.edgesContainer.addChild(g);
        }

        _drawDashedLine(g, x1, y1, x2, y2, color) {
            const dx = x2 - x1, dy = y2 - y1;
            const dist = Math.sqrt(dx * dx + dy * dy);
            const dash = 6, gap = 4;
            const steps = Math.floor(dist / (dash + gap));
            const ux = dx / dist, uy = dy / dist;
            g.lineStyle({ width: 1.5, color: color, alpha: 0.75 });
            for (let i = 0; i < steps; i++) {
                const sx = x1 + ux * (dash + gap) * i;
                const sy = y1 + uy * (dash + gap) * i;
                const ex = sx + ux * dash;
                const ey = sy + uy * dash;
                g.moveTo(sx, sy);
                g.lineTo(ex, ey);
            }
            g.lineStyle(0);
        }

        _drawArrow(g, x1, y1, x2, y2, color) {
            const angle = Math.atan2(y2 - y1, x2 - x1);
            const size = 6;
            g.beginFill(color, 0.9);
            g.moveTo(x2, y2);
            g.lineTo(x2 - size * Math.cos(angle - 0.4), y2 - size * Math.sin(angle - 0.4));
            g.lineTo(x2 - size * Math.cos(angle + 0.4), y2 - size * Math.sin(angle + 0.4));
            g.closePath();
            g.endFill();
        }

        // =========================================================
        //  移除食材
        // =========================================================
        removeLayer(layer) {
            const idx = this.layers.indexOf(layer);
            if (idx === -1) return;

            // 淡出 + 缩小动画
            this._tween(layer.container, {
                alpha: 0,
                x: CANVAS_W + 50,
            }, 200, () => {
                this.layerContainer.removeChild(layer.container);
                layer.container.destroy({ children: true });
            });

            this.layers.splice(idx, 1);

            if (this.selectedLayer === layer) {
                this.selectedLayer = null;
                if (this.onDeselectAll) this.onDeselectAll();
            }

            // 重排剩余食材
            setTimeout(() => {
                this.updateStack(true);
                if (this.layers.length === 0 && this.hintText) {
                    this.hintText.visible = true;
                }
            }, 220);

            this._fireLayerCountChange();
        }

        // =========================================================
        //  选中 / 取消选中
        // =========================================================
        selectLayer(layer) {
            this.deselectAll();
            this.selectedLayer = layer;
            if (this.onSelectIngredient) this.onSelectIngredient(layer);
        }

        deselectAll() {
            if (this.selectedLayer) {
                this.selectedLayer = null;
            }
            if (this.onDeselectAll) this.onDeselectAll();
        }

        // =========================================================
        //  清空所有食材
        // =========================================================
        clearAll() {
            // 给每个食材一个逐个飞走的动画
            this.layers.forEach((layer, i) => {
                this._tween(layer.container, {
                    alpha: 0,
                    y: layer.container.y - 80,
                }, 200 + i * 60, () => {
                    this.layerContainer.removeChild(layer.container);
                    layer.container.destroy({ children: true });
                });
            });

            this.layers = [];
            this.selectedLayer = null;
            if (this.onDeselectAll) this.onDeselectAll();

            setTimeout(() => {
                if (this.hintText) this.hintText.visible = true;
            }, 400);

            this._fireLayerCountChange();
        }

        // =========================================================
        //  上菜动画
        // =========================================================
        playServeAnimation(callback) {
            // 整体弹跳
            const bounce = (layer, delay) => {
                setTimeout(() => {
                    const origY = layer.container.y;
                    this._tween(layer.container, { y: origY - 15 }, 120, () => {
                        this._tween(layer.container, { y: origY }, 150);
                    });
                }, delay);
            };

            this.layers.forEach((l, i) => bounce(l, i * 50));

            // 光效 — Central flash
            const flash = new PIXI.Graphics();
            flash.beginFill(0xffd700, 0.15);
            flash.drawCircle(STACK_CENTER_X, PLATE_Y - 120, 10);
            flash.endFill();
            this.bgContainer.addChild(flash);
            this._tween(flash, { alpha: 0, width: 400, height: 400 }, 600, () => {
                this.bgContainer.removeChild(flash);
                flash.destroy();
                if (callback) callback();
            });
        }

        // =========================================================
        //  导出 JSON（含位置验证 + 配方识别）
        // =========================================================
        exportJSON() {
            // --- 1. 获取当前食材类型列表（从顶到底，即 layers[0] 是最上层）---
            const layerTypes = this.layers.map((l) => l.meta.id);

            // --- 2. 结构验证 ---
            const validation = BurgerGame.Recipes.validateStructure(layerTypes);
            if (!validation.valid) {
                return { valid: false, error: validation.error };
            }

            // --- 3. 配方匹配 ---
            const recipe = BurgerGame.Recipes.matchRecipe(layerTypes);
            const agentType = recipe ? recipe.name : 'unknown';
            const agentLabel = recipe ? recipe.label : '未知配方';

            // --- 4. 生成 burger_layers ---
            const burgerLayers = this.layers.map((l, i) => {
                const obj = { type: l.meta.id, order: i };
                if (l.config && Object.keys(l.config).length > 0) {
                    obj.config = JSON.parse(JSON.stringify(l.config));
                }
                return obj;
            });

            // --- 5. 提取兼容后端的字段 ---
            let cheesePrompt = '你是一个有用的智能助手';
            let meatModel = 'qwen-plus';
            let vegetables = [];

            this.layers.forEach((l) => {
                if (l.meta.id === 'cheese' && l.config.prompt) {
                    cheesePrompt = l.config.prompt;
                }
                if (l.meta.id === 'meat_patty' && l.config.model) {
                    meatModel = l.config.model;
                }
                if (l.meta.id === 'lettuce' && l.config.tools) {
                    vegetables = vegetables.concat(l.config.tools);
                }
            });

            return {
                valid: true,
                agent_type: agentType,
                agent_label: agentLabel,
                cheese_prompt: cheesePrompt,
                meat_model: meatModel,
                vegetables: [...new Set(vegetables)],
                burger_layers: burgerLayers,
            };
        }

        // =========================================================
        //  获取当前食材类型列表（供外部实时查阅）
        // =========================================================
        getLayerTypes() {
            return this.layers.map((l) => l.meta.id);
        }

        // =========================================================
        //  按配方批量铺层（recipe 模式）
        //    layerTypes : 从上到下的食材 id 数组
        // =========================================================
        loadRecipeLayers(layerTypes) {
            this.clearAll();
            (layerTypes || []).forEach((type, i) => {
                setTimeout(() => this.addIngredient(type), i * 80);
            });
        }

        // =========================================================
        //  节点高亮（SSE 流式执行时用）
        //    type   : 节点名（与食材 id 对应，bottom_bread/top_bread/...）
        //    status : 'start' | 'end'
        //  meat/vegetable 节点在后端的 id 分别是 'meat' / 'vegetable'
        //  我们通过 meta.id 匹配（meat_patty / lettuce）并做别名映射。
        // =========================================================
        highlightLayer(nodeName, status) {
            const aliasMap = {
                meat: 'meat_patty',
                vegetable: 'lettuce',
                pickle: 'pickle',          // 🥒 HITL 审批关卡：直接映射到 pickle 食材
                approval: 'pickle',        // 兼容旧名
            };
            const ingId = aliasMap[nodeName] || nodeName;
            const layer = this.layers.find((l) => l.meta.id === ingId);
            if (!layer || !layer.container) return;

            const c = layer.container;
            if (status === 'start') {
                c.alpha = 1;
                // 闪一下：alpha 轻微脉动
                this._tween(c, { alpha: 0.55 }, 180, () => {
                    this._tween(c, { alpha: 1 }, 220);
                });
                // 用 tint 叠加高亮（所有支持 tint 的子对象）
                c.children.forEach((child) => {
                    if (child.tint !== undefined) {
                        if (child._origTint === undefined) child._origTint = child.tint;
                        child.tint = 0xffd700;
                    }
                });
            } else {
                c.children.forEach((child) => {
                    if (child._origTint !== undefined) {
                        child.tint = child._origTint;
                    }
                });
            }
        }

        // =========================================================
        //  简易 Tween 系统
        // =========================================================
        _tween(obj, props, duration, onComplete) {
            // 取消同一对象上已有的 tween，避免位置冲突
            for (let i = this.tweens.length - 1; i >= 0; i--) {
                if (this.tweens[i].obj === obj) {
                    this.tweens.splice(i, 1);
                }
            }

            const tw = {
                obj: obj,
                startProps: {},
                endProps: props,
                duration: duration,
                elapsed: 0,
                onComplete: onComplete,
            };

            for (let key in props) {
                tw.startProps[key] = obj[key];
            }

            this.tweens.push(tw);
        }

        _updateTweens() {
            const dt = this.app.ticker.deltaMS;
            for (let i = this.tweens.length - 1; i >= 0; i--) {
                const tw = this.tweens[i];
                tw.elapsed += dt;
                let t = Math.min(tw.elapsed / tw.duration, 1);
                // Ease out cubic
                t = 1 - Math.pow(1 - t, 3);

                for (let key in tw.endProps) {
                    tw.obj[key] = tw.startProps[key] + (tw.endProps[key] - tw.startProps[key]) * t;
                }

                if (t >= 1) {
                    this.tweens.splice(i, 1);
                    if (tw.onComplete) tw.onComplete();
                }
            }
        }

        // =========================================================
        //  工具
        // =========================================================
        _fireLayerCountChange() {
            if (this.onLayerCountChange) {
                this.onLayerCountChange(this.layers.length);
            }
        }
    }

    BurgerGame.BurgerCanvas = BurgerCanvas;
})();
