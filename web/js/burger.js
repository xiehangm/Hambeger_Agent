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
            this.layerContainer = new PIXI.Container();
            this.app.stage.addChild(this.bgContainer);
            this.app.stage.addChild(this.layerContainer);

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
                    // 根据 Y 位置重新排序
                    this.layers.sort((a, b) => a.container.y - b.container.y);
                    this.updateStack(true);
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
            }
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
        //  简易 Tween 系统
        // =========================================================
        _tween(obj, props, duration, onComplete) {
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
